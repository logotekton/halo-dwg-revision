"""Hidden ZWCAD COM bridge for DWG<->DXF conversion (brief R1-02, contract §6.1).

The instance runs hidden (``Visible=False``) inside this process, launched
through ``comtypes`` (MIT) -- never ``pywin32`` (ADR-0007, licence
allow-list). ``comtypes`` itself is only ever imported lazily, inside
``ComtypesBackend`` methods: it is a Windows-only dependency added to
``engine/pyproject.toml`` by a parallel task (R1-00b) and is not installed
on the macOS machines this code is developed on, so importing it at module
scope would break every import of this module off Windows.

All COM interaction goes through the ``ComBackend`` protocol -- the only
seam tests replace with a fake (``engine/tests/compare/fake_com.py``). Real
automation ("does ZWCAD really open this file") is confirmed by the user on
a Windows install (``docs/dev/zwcad-bridge.md``); this module's own test
suite only proves the calling sequence, timeout/restart, and platform
gating are correct.

Threading note: the COM calls (``Documents.Open``/``SaveAs``/``Close``) run
on the *calling* thread -- ZWCAD's Application object is an STA COM object,
and STA objects may only be used from the apartment thread that created
them. A separate watchdog thread only *measures* elapsed time and, on
timeout, kills the OS process tree (it can never safely reach into the
calling thread's blocked COM call). The calling thread's own call then
either raises (the process died under it) or returns stale data; either way
``_convert`` raises ``ZwcadTimeout`` once the watchdog has flagged a
timeout, discarding whatever the blocked call produced.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from halo_engine.procutil import pid_alive

logger = logging.getLogger("halo_engine.compare.zwcad")

# ProgID candidates, oldest/most-generic first. Detection and instance
# creation both try them from the back (most version-specific first) so a
# machine with several ZWCAD releases registered prefers the newest.
_PROG_ID_CANDIDATES: tuple[str, ...] = ("ZWCAD.Application", "ZWCAD.Application.2026")

_VERSION_SUFFIX_RE = re.compile(r"\.(\d{4})$")

# SaveAs version constants (COM `SaveAs(path, AsType)`). ZWCAD's automation
# surface is AutoCAD-compatible, so this assumes its `ZcSaveAsType` enum
# mirrors AutoCAD's `AcSaveAsType` values 1:1 -- that assumption is
# *unconfirmed* until the Windows manual check (docs/dev/zwcad-bridge.md)
# runs against a real ZWCAD 2026 Professional install. If any value turns
# out to differ, fix it here; every caller goes through this one dict.
SAVE_AS_VERSIONS: dict[str, int] = {
    "ac2000_dxf": 13,
    "ac2007_dxf": 37,
    "ac2013_dwg": 60,
    "ac2013_dxf": 61,
    "ac2018_dwg": 64,
    "ac2018_dxf": 65,
}

_SUPPORTED_DXF_VERSIONS = {"2000", "2007", "2013", "2018"}
_SUPPORTED_DWG_VERSIONS = {"2013", "2018"}

# Sysvars that must succeed at startup -- a failure here can leave a hidden
# instance stuck behind a dialog box it can never dismiss.
_FATAL_SYSVARS: tuple[tuple[str, Any], ...] = (
    ("FILEDIA", 0),
    ("CMDDIA", 0),
    ("PROXYNOTICE", 0),
)
# Non-fatal: a missing Korean-capable substitute font degrades text
# rendering but never blocks automation.
_FONTALT_VALUE = "malgun.ttf"


@dataclass(frozen=True)
class ZwcadStatus:
    """Whether this process can convert via the ZWCAD COM bridge right now."""

    available: bool  # True only on Windows, with comtypes installed and a ProgID registered.
    installed: bool
    version: str | None  # e.g. "2026"
    prog_id: str | None  # "ZWCAD.Application" or a version-suffixed ProgID
    # Not Korean by design -- machine-readable reason code, i18n'd by the UI:
    # not_windows | comtypes_missing | not_registered | com_error.
    reason: str | None


@dataclass(frozen=True)
class ConvertResult:
    converter: Literal["zwcad-com"]
    zwcad_version: str
    elapsed_s: float
    warnings: list[str]


class ZwcadError(RuntimeError):
    """Base class for anything that goes wrong talking to ZWCAD."""


class ZwcadTimeout(ZwcadError):
    """A single file's conversion exceeded ``timeout_s``; the instance was restarted."""


class ZwcadUnavailable(ZwcadError):
    """No usable ZWCAD COM bridge in this process (wrong OS, missing comtypes, not installed)."""


class ComBackend(Protocol):
    """The only boundary tests replace with a fake -- everything else is real code."""

    def create_app(self, prog_id: str) -> Any: ...

    def kill_process_tree(self, pid: int) -> None: ...


# ---------------------------------------------------------------------------
# Registry / platform detection
# ---------------------------------------------------------------------------


def _find_registered_prog_id() -> str | None:
    """Return the newest registered ProgID, or ``None``. Windows-only; lazy ``winreg`` import.

    Only ever called after a ``sys.platform == "win32"`` check, so the
    ``winreg`` import here never runs off Windows -- tests replace this
    whole function (it is not part of ``ComBackend``: it is a plain registry
    read, not a COM call) rather than exercising a real registry.
    """
    # typeshed's winreg stub only declares these names under sys.platform ==
    # "win32", so mypy (running on macOS) sees a platform-less stub here.
    import winreg

    hkey_classes_root = winreg.HKEY_CLASSES_ROOT  # type: ignore[attr-defined]
    for prog_id in reversed(_PROG_ID_CANDIDATES):
        try:
            key = winreg.OpenKey(hkey_classes_root, f"{prog_id}\\CLSID")  # type: ignore[attr-defined]
        except OSError:
            continue
        else:
            winreg.CloseKey(key)  # type: ignore[attr-defined]
            return prog_id
    return None


def _version_from_prog_id(prog_id: str) -> str | None:
    """Best-effort version from a version-suffixed ProgID (e.g. "...2026" -> "2026").

    A bare ``ZWCAD.Application`` match carries no version in its name; the
    generated instance's own ``Application.Version`` (read once at
    ``ZwcadConverter`` startup) is the authoritative source in that case.
    """
    match = _VERSION_SUFFIX_RE.search(prog_id)
    return match.group(1) if match else None


def detect() -> ZwcadStatus:
    """Registry + comtypes-import check. Never launches a COM instance (fast, side-effect-free)."""
    if sys.platform != "win32":
        return ZwcadStatus(
            available=False, installed=False, version=None, prog_id=None, reason="not_windows"
        )

    try:
        prog_id = _find_registered_prog_id()
    except Exception as exc:  # pragma: no cover - defensive, winreg surprises
        return ZwcadStatus(
            available=False,
            installed=False,
            version=None,
            prog_id=None,
            reason=f"com_error: {str(exc)[:200]}",
        )

    if prog_id is None:
        return ZwcadStatus(
            available=False, installed=False, version=None, prog_id=None, reason="not_registered"
        )

    version = _version_from_prog_id(prog_id)

    try:
        import comtypes  # noqa: F401  -- presence check only, see module docstring
    except ImportError:
        return ZwcadStatus(
            available=False,
            installed=True,
            version=version,
            prog_id=prog_id,
            reason="comtypes_missing",
        )

    return ZwcadStatus(
        available=True, installed=True, version=version, prog_id=prog_id, reason=None
    )


# ---------------------------------------------------------------------------
# PID resolution (bare Win32 call, not a COM call -- see module docstring)
# ---------------------------------------------------------------------------

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    def _pid_from_hwnd(hwnd: int) -> int | None:
        # ctypes.WinDLL (not ctypes.windll) to match procutil.py's pattern --
        # a plain attribute a type checker running off-Windows still knows.
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
        return int(pid.value) or None

else:

    def _pid_from_hwnd(hwnd: int) -> int | None:  # pragma: no cover - never called off Windows
        return None


# ---------------------------------------------------------------------------
# comtypes.client.gen_dir -- must be writable from a PyInstaller install
# ---------------------------------------------------------------------------


def _resolve_gen_dir() -> Path:
    """``%LOCALAPPDATA%/halo/comtypes_gen``, falling back to a tempdir if unset."""
    import os

    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata) / "halo" / "comtypes_gen"
    return Path(tempfile.gettempdir()) / "halo_comtypes_gen"


def _configure_gen_dir(comtypes_client: Any) -> Path:
    """Create the gen_dir and point ``comtypes.client.gen_dir`` at it.

    Takes the ``comtypes.client`` module (or any stand-in exposing a
    ``gen_dir`` attribute) so this can be unit-tested without a real
    comtypes install.
    """
    gen_dir = _resolve_gen_dir()
    gen_dir.mkdir(parents=True, exist_ok=True)
    comtypes_client.gen_dir = str(gen_dir)
    return gen_dir


# ---------------------------------------------------------------------------
# Real COM backend
# ---------------------------------------------------------------------------


class ComtypesBackend:
    """The real ``ComBackend``. Windows-only; imports ``comtypes`` lazily per method."""

    def create_app(self, prog_id: str) -> Any:
        import comtypes.client

        _configure_gen_dir(comtypes.client)
        return comtypes.client.CreateObject(prog_id)

    def kill_process_tree(self, pid: int) -> None:
        if sys.platform != "win32":
            raise RuntimeError("ComtypesBackend.kill_process_tree is Windows-only")
        # No psutil in this project's dependency allow-list: `taskkill /T`
        # walks and kills the whole process tree without manual enumeration.
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )


# ---------------------------------------------------------------------------
# SaveAs version helpers
# ---------------------------------------------------------------------------


def _dxf_save_as_key(version: str) -> str:
    if version not in _SUPPORTED_DXF_VERSIONS:
        raise ZwcadError(
            f"unsupported dxf_version {version!r}; supported: {sorted(_SUPPORTED_DXF_VERSIONS)}"
        )
    return f"ac{version}_dxf"


def _dwg_save_as_key(version: str) -> str:
    if version not in _SUPPORTED_DWG_VERSIONS:
        raise ZwcadError(
            f"unsupported dwg_version {version!r}; supported: {sorted(_SUPPORTED_DWG_VERSIONS)}"
        )
    return f"ac{version}_dwg"


# ---------------------------------------------------------------------------
# ZwcadConverter
# ---------------------------------------------------------------------------


class ZwcadConverter:
    """One hidden ZWCAD instance. Convert files through it inside a ``with`` block."""

    def __init__(
        self,
        *,
        timeout_s: float = 120,
        dxf_version: str = "2013",
        com: ComBackend | None = None,
    ) -> None:
        if sys.platform != "win32":
            raise ZwcadUnavailable(
                "ZWCAD COM bridge is only available on Windows (reason=not_windows)"
            )
        self._timeout_s: float = timeout_s
        self._dxf_version: str = dxf_version
        self._com: ComBackend = com if com is not None else ComtypesBackend()
        self._app: Any = None
        self._pid: int | None = None
        self._version: str = "unknown"
        self._start()

    def __enter__(self) -> ZwcadConverter:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._shutdown()

    # -- lifecycle ----------------------------------------------------

    def _start(self) -> None:
        prog_id, app = self._create_app_with_fallback()
        self._app = app
        self._version = self._read_version(app, prog_id)
        self._apply_sysvars(app)
        self._pid = self._resolve_pid(app)

    def _create_app_with_fallback(self) -> tuple[str, Any]:
        last_exc: Exception | None = None
        for prog_id in reversed(_PROG_ID_CANDIDATES):
            try:
                return prog_id, self._com.create_app(prog_id)
            except Exception as exc:  # noqa: BLE001 - tried again with the next ProgID
                last_exc = exc
                continue
        raise ZwcadUnavailable(f"could not create a ZWCAD COM instance: {last_exc}") from last_exc

    @staticmethod
    def _read_version(app: Any, prog_id: str) -> str:
        try:
            return str(app.Version)
        except Exception:  # noqa: BLE001 - fall back to the ProgID's own version suffix
            return _version_from_prog_id(prog_id) or "unknown"

    @staticmethod
    def _apply_sysvars(app: Any) -> None:
        try:
            app.Visible = False
        except Exception as exc:
            raise ZwcadError(f"failed to hide ZWCAD instance: {exc}") from exc
        for name, value in _FATAL_SYSVARS:
            try:
                app.SetVariable(name, value)
            except Exception as exc:
                raise ZwcadError(f"failed to set sysvar {name}: {exc}") from exc
        try:
            app.SetVariable("FONTALT", _FONTALT_VALUE)
        except Exception as exc:  # noqa: BLE001 - non-fatal, degrades text rendering only
            logger.warning("failed to set FONTALT (non-fatal): %s", exc)

    @staticmethod
    def _resolve_pid(app: Any) -> int | None:
        hwnd = getattr(app, "HWND", None)
        if not hwnd:
            logger.warning(
                "could not read ZWCAD HWND; a timeout will Quit() only, without a tree-kill"
            )
            return None
        pid = _pid_from_hwnd(int(hwnd))
        if pid is None:
            logger.warning(
                "could not resolve a PID from HWND=%s; a timeout will Quit() only, "
                "without a tree-kill",
                hwnd,
            )
        return pid

    def restart(self) -> None:
        """Tear down the current instance (however possible) and start a fresh one."""
        logger.info("restarting the ZWCAD COM instance")
        self._force_close_current()
        self._start()

    def _force_close_current(self) -> None:
        if self._pid is not None:
            try:
                self._com.kill_process_tree(self._pid)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup before restart
                logger.warning("kill_process_tree failed during restart: %s", exc)
        elif self._app is not None:
            try:
                self._app.Quit()
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup before restart
                logger.warning("Quit() failed during restart: %s", exc)
        self._app = None
        self._pid = None

    def _shutdown(self) -> None:
        try:
            if self._app is not None:
                self._app.Quit()
        except Exception as exc:  # noqa: BLE001 - still check/force-kill below
            logger.warning("Quit() failed on shutdown: %s", exc)
        if self._pid is not None and pid_alive(self._pid):
            logger.warning("ZWCAD process %s survived Quit(); force-killing", self._pid)
            try:
                self._com.kill_process_tree(self._pid)
            except Exception as exc:  # noqa: BLE001 - nothing further we can do
                logger.warning("kill_process_tree failed on shutdown: %s", exc)
        self._app = None
        self._pid = None

    # -- conversion -----------------------------------------------------

    def convert_dwg_to_dxf(self, dwg_path: Path, out_dxf: Path) -> ConvertResult:
        version_key = _dxf_save_as_key(self._dxf_version)
        return self._convert(dwg_path, out_dxf, version_key)

    def convert_dxf_to_dwg(
        self, dxf_path: Path, out_dwg: Path, *, dwg_version: str = "2013"
    ) -> ConvertResult:
        version_key = _dwg_save_as_key(dwg_version)
        return self._convert(dxf_path, out_dwg, version_key)

    def _convert(self, in_path: Path, out_path: Path, version_key: str) -> ConvertResult:
        if not in_path.exists():
            raise ZwcadError(f"input file not found: {in_path}")

        started = time.monotonic()
        done = threading.Event()
        timed_out = threading.Event()

        def _watchdog() -> None:
            if done.wait(self._timeout_s):
                return
            timed_out.set()
            logger.warning(
                "ZWCAD conversion of %s exceeded %.1fs; killing and restarting",
                in_path,
                self._timeout_s,
            )
            pid = self._pid
            if pid is not None:
                try:
                    self._com.kill_process_tree(pid)
                except Exception as exc:  # noqa: BLE001 - still try to restart below
                    logger.warning("kill_process_tree failed after timeout: %s", exc)
            else:
                try:
                    if self._app is not None:
                        self._app.Quit()
                except Exception as exc:  # noqa: BLE001 - still try to restart below
                    logger.warning("Quit() after timeout failed: %s", exc)
            self._app = None
            self._pid = None
            try:
                self._start()
            except Exception:
                logger.exception("failed to restart ZWCAD after a timeout")

        watchdog = threading.Thread(target=_watchdog, daemon=True)
        watchdog.start()

        call_error: BaseException | None = None
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            documents = self._app.Documents
            doc = documents.Open(str(in_path), True)
            try:
                doc.SaveAs(str(out_path), SAVE_AS_VERSIONS[version_key])
            finally:
                doc.Close(False)
        except BaseException as exc:  # noqa: BLE001 - classified into Zwcad* below
            call_error = exc
        finally:
            done.set()
        watchdog.join()

        if timed_out.is_set():
            raise ZwcadTimeout(
                f"conversion of {in_path} exceeded {self._timeout_s:.0f}s"
            ) from call_error
        if call_error is not None:
            raise ZwcadError(f"ZWCAD conversion failed: {call_error}") from call_error
        if not out_path.exists() or out_path.stat().st_size == 0:
            raise ZwcadError(f"empty output: {out_path}")

        elapsed = time.monotonic() - started
        return ConvertResult(
            converter="zwcad-com", zwcad_version=self._version, elapsed_s=elapsed, warnings=[]
        )
