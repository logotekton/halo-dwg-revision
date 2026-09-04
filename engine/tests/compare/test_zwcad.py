"""Contract tests for ``halo_engine.compare.zwcad`` (brief R1-02).

All COM interaction is faked via ``ComBackend`` (``fake_com.py``); the
Windows branch is exercised by monkeypatching ``sys.platform`` to
``"win32"`` (this suite never touches real COM, the real registry, or real
Win32 APIs). Real ZWCAD automation is verified separately, by the user, on
a Windows install (``docs/dev/zwcad-bridge.md``).
"""

from __future__ import annotations

import os
import sys
import time
import types
from pathlib import Path

import pytest

from halo_engine.compare import zwcad
from halo_engine.compare.zwcad import ZwcadStatus

from .fake_com import FakeApp, FakeComBackend, FakeDocument

# ---------------------------------------------------------------------------
# detect()
# ---------------------------------------------------------------------------


def test_detect_not_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    assert zwcad.detect() == ZwcadStatus(
        available=False, installed=False, version=None, prog_id=None, reason="not_windows"
    )


def test_detect_available_with_fake_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(zwcad, "_find_registered_prog_id", lambda: "ZWCAD.Application.2026")
    monkeypatch.setitem(sys.modules, "comtypes", types.ModuleType("comtypes"))

    status = zwcad.detect()

    assert status == ZwcadStatus(
        available=True,
        installed=True,
        version="2026",
        prog_id="ZWCAD.Application.2026",
        reason=None,
    )


def test_detect_not_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(zwcad, "_find_registered_prog_id", lambda: None)

    status = zwcad.detect()

    assert status.available is False
    assert status.installed is False
    assert status.reason == "not_registered"


def test_detect_comtypes_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(zwcad, "_find_registered_prog_id", lambda: "ZWCAD.Application")
    monkeypatch.delitem(sys.modules, "comtypes", raising=False)
    real_import = __import__

    def _fail_comtypes_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "comtypes":
            raise ImportError("no comtypes on this machine")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _fail_comtypes_import)

    status = zwcad.detect()

    assert status.installed is True
    assert status.available is False
    assert status.reason == "comtypes_missing"


# ---------------------------------------------------------------------------
# ZwcadConverter -- platform gating
# ---------------------------------------------------------------------------


def test_unavailable_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    with pytest.raises(zwcad.ZwcadUnavailable):
        zwcad.ZwcadConverter()


# ---------------------------------------------------------------------------
# ZwcadConverter -- startup sequence
# ---------------------------------------------------------------------------


def test_sysvars_set_on_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    fake = FakeComBackend()

    with zwcad.ZwcadConverter(com=fake):
        app = fake.apps[0]
        assert app.Visible is False
        assert app.sysvars["FILEDIA"] == 0
        assert app.sysvars["CMDDIA"] == 0
        assert app.sysvars["PROXYNOTICE"] == 0
        assert app.sysvars["FONTALT"] == "malgun.ttf"


def test_fatal_sysvar_failure_raises_zwcad_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    fake = FakeComBackend(
        app_factory=lambda prog_id: FakeApp(failing_sysvars=frozenset({"FILEDIA"}))
    )

    with pytest.raises(zwcad.ZwcadError):
        zwcad.ZwcadConverter(com=fake)


def test_fontalt_failure_is_non_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    fake = FakeComBackend(
        app_factory=lambda prog_id: FakeApp(failing_sysvars=frozenset({"FONTALT"}))
    )

    with zwcad.ZwcadConverter(com=fake) as converter:
        assert converter is not None


def test_create_app_fallback_tries_older_prog_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    fake = FakeComBackend(fail_prog_ids=frozenset({"ZWCAD.Application.2026"}))

    with zwcad.ZwcadConverter(com=fake):
        pass

    assert fake.create_app_calls == ["ZWCAD.Application.2026", "ZWCAD.Application"]


def test_all_prog_ids_failing_raises_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    fake = FakeComBackend(fail_prog_ids=frozenset(zwcad._PROG_ID_CANDIDATES))

    with pytest.raises(zwcad.ZwcadUnavailable):
        zwcad.ZwcadConverter(com=fake)


# ---------------------------------------------------------------------------
# convert_dwg_to_dxf / convert_dxf_to_dwg
# ---------------------------------------------------------------------------


def test_convert_calls_open_readonly_saveas_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    fake = FakeComBackend()
    dwg = tmp_path / "a.dwg"
    dwg.write_bytes(b"fake dwg bytes")
    out = tmp_path / "out" / "a.dxf"

    with zwcad.ZwcadConverter(com=fake, dxf_version="2013") as converter:
        result = converter.convert_dwg_to_dxf(dwg, out)

    app = fake.apps[0]
    assert app.Documents.open_calls == [(str(dwg), True)]
    doc = app.Documents.documents[0]
    assert doc.saveas_calls == [(str(out), zwcad.SAVE_AS_VERSIONS["ac2013_dxf"])]
    assert doc.close_calls == [False]
    assert out.exists()
    assert out.stat().st_size > 0

    assert result.converter == "zwcad-com"
    assert result.zwcad_version == "2026"
    assert result.elapsed_s >= 0
    assert result.warnings == []


def test_convert_dxf_to_dwg_uses_dwg_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    fake = FakeComBackend()
    dxf = tmp_path / "a.dxf"
    dxf.write_bytes(b"fake dxf bytes")
    out = tmp_path / "a.dwg"

    with zwcad.ZwcadConverter(com=fake) as converter:
        converter.convert_dxf_to_dwg(dxf, out)

    doc = fake.apps[0].Documents.documents[0]
    assert doc.saveas_calls == [(str(out), zwcad.SAVE_AS_VERSIONS["ac2013_dwg"])]


def test_convert_dxf_to_dwg_rejects_unsupported_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    fake = FakeComBackend()
    dxf = tmp_path / "a.dxf"
    dxf.write_bytes(b"x")

    with zwcad.ZwcadConverter(com=fake) as converter:
        with pytest.raises(zwcad.ZwcadError):
            converter.convert_dxf_to_dwg(dxf, tmp_path / "a.dwg", dwg_version="1999")


def test_empty_output_raises_zwcad_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")

    def _saveas_writes_nothing(_doc: FakeDocument, path: str, _version: int) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.touch()

    def _app_factory(_prog_id: str) -> FakeApp:
        app = FakeApp()
        app.Documents.open_hook = lambda path, read_only: FakeDocument(
            path=path, read_only=read_only, saveas_hook=_saveas_writes_nothing
        )
        return app

    fake = FakeComBackend(app_factory=_app_factory)
    dwg = tmp_path / "a.dwg"
    dwg.write_bytes(b"x")

    with zwcad.ZwcadConverter(com=fake) as converter:
        with pytest.raises(zwcad.ZwcadError):
            converter.convert_dwg_to_dxf(dwg, tmp_path / "a.dxf")


# ---------------------------------------------------------------------------
# Timeout + restart
# ---------------------------------------------------------------------------


def test_timeout_kills_tree_and_restarts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(zwcad, "_pid_from_hwnd", lambda hwnd: 4321)
    # Shutdown is not under test here; avoid it touching the real (platform-
    # gated) procutil.pid_alive with a monkeypatched sys.platform.
    monkeypatch.setattr(zwcad, "pid_alive", lambda pid: False)

    def _hang_then_die(_doc: FakeDocument, _path: str, _version: int) -> None:
        # Simulates a stuck SaveAs call whose process gets killed out from
        # under it: the call eventually errors, well after the watchdog's
        # short timeout has already fired.
        time.sleep(0.2)
        raise RuntimeError("connection to ZWCAD lost (simulated kill)")

    def _app_factory(_prog_id: str) -> FakeApp:
        app = FakeApp()
        app.Documents.open_hook = lambda path, read_only: FakeDocument(
            path=path, read_only=read_only, saveas_hook=_hang_then_die
        )
        return app

    fake = FakeComBackend(app_factory=_app_factory)
    dwg = tmp_path / "a.dwg"
    dwg.write_bytes(b"x")

    with zwcad.ZwcadConverter(com=fake, timeout_s=0.05) as converter:
        with pytest.raises(zwcad.ZwcadTimeout):
            converter.convert_dwg_to_dxf(dwg, tmp_path / "a.dxf")

        assert fake.kill_process_tree_calls == [4321]
        # One instance at startup, one more from the timeout's restart().
        assert fake.create_app_calls == ["ZWCAD.Application.2026", "ZWCAD.Application.2026"]
        assert len(fake.apps) == 2


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------


def test_exit_quits_and_kills_if_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(zwcad, "_pid_from_hwnd", lambda hwnd: 4321)
    monkeypatch.setattr(zwcad, "pid_alive", lambda pid: True)
    fake = FakeComBackend()

    converter = zwcad.ZwcadConverter(com=fake)
    converter.__exit__(None, None, None)

    app = fake.apps[0]
    assert app.quit_calls == 1
    assert fake.kill_process_tree_calls == [4321]


def test_exit_quits_without_kill_if_already_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(zwcad, "_pid_from_hwnd", lambda hwnd: 4321)
    monkeypatch.setattr(zwcad, "pid_alive", lambda pid: False)
    fake = FakeComBackend()

    converter = zwcad.ZwcadConverter(com=fake)
    converter.__exit__(None, None, None)

    app = fake.apps[0]
    assert app.quit_calls == 1
    assert fake.kill_process_tree_calls == []


# ---------------------------------------------------------------------------
# comtypes.client.gen_dir
# ---------------------------------------------------------------------------


def test_gen_dir_is_writable_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.setattr(zwcad.tempfile, "gettempdir", lambda: str(tmp_path))
    fake_comtypes_client = types.SimpleNamespace(gen_dir=None)

    gen_dir = zwcad._configure_gen_dir(fake_comtypes_client)

    assert gen_dir == tmp_path / "halo_comtypes_gen"
    assert gen_dir.is_dir()
    assert os.access(gen_dir, os.W_OK)
    assert fake_comtypes_client.gen_dir == str(gen_dir)


def test_gen_dir_prefers_local_appdata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    fake_comtypes_client = types.SimpleNamespace(gen_dir=None)

    gen_dir = zwcad._configure_gen_dir(fake_comtypes_client)

    assert gen_dir == tmp_path / "halo" / "comtypes_gen"
    assert gen_dir.is_dir()
    assert fake_comtypes_client.gen_dir == str(gen_dir)
