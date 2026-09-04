"""Set-level ingest orchestration for a ``compare_set`` (brief R1-03, contract §6).

``POST /compare/sets`` (``api/routers/compare_sets.py``) opens the bundle and
creates the ``drawing_set``/``drawing_file``/``compare_set`` rows; this module
is the ``compare.ingest`` job body that turns those rows into working DXFs:

1. **plan** each side's folder (:func:`plan_set_files` -- one level deep,
   ``.dwg``/``.dxf`` only, sorted case-insensitively, ``ignore_patterns``
   applied);
2. **convert** every non-excluded file, before side first then after side
   (contract: "파일 순서: 전 세트 → 후 세트"), reusing
   ``ingest/pipeline.py``'s ``copy_original_step``/``build_working_dxf_step``
   for the parts that are unchanged from the plain drawing-set import, and
   :mod:`halo_engine.compare.zwcad` for the new ZWCAD-first path
   (:func:`pick_converter` decides which, per file);
3. **enforce the same-converter rule** (:func:`enforce_same_converter`)
   across the two sides by file name, so a builtin-converted file's
   same-named counterpart is never left on ZWCAD;
4. **sample-crosscheck** a handful of ZWCAD-converted files against the
   builtin converter when both are actually usable on this machine;
5. close the ``compare_set`` out as ``ingested`` (or ``failed`` if every
   file failed) with a ``stats`` summary.

Two things are deliberately unlike the plain import path
(``api/jobs.py::run_drawing_set_import``): ZWCAD conversion runs on one
dedicated single-thread ``ThreadPoolExecutor`` per side (COM's STA
requirement, module docstring of ``compare/zwcad.py``) rather than the
shared ``ProcessPoolExecutor``, and this job is wrapped in the generic
``api/jobs.py::run_job``/``ProgressReporter`` envelope instead of writing its
own status/broadcast bookkeeping inline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from collections.abc import Sequence
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import ezdxf
from fastapi import FastAPI

from halo_engine.api.jobs import (
    CONVERT_TIMEOUT_S,
    JobCancelled,
    JobRecord,
    ProgressReporter,
    get_job_manager,
    run_job,
)
from halo_engine.api.ws import ConnectionManager, get_connection_manager
from halo_engine.bundle.create import BundleHandle
from halo_engine.compare import zwcad
from halo_engine.compare.config import IngestSettings, load_compare_config
from halo_engine.config import Settings
from halo_engine.db import repos
from halo_engine.db.models import DrawingFileRow
from halo_engine.ingest import pipeline
from halo_engine.ingest.xref import is_ignored_name
from halo_engine.model.drawing import DrawingFormat, ImportStatus
from halo_engine.validate import crosscheck as crosscheck_module

logger = logging.getLogger("halo_engine.compare.ingest_set")

Role = Literal["before", "after"]
ConverterChoice = Literal["zwcad-com", "builtin"]

#: One level of a set folder, ``.dwg``/``.dxf`` only (Defaults for ambiguity:
#: "폴더 안 하위 폴더는 재귀하지 않는다").
_DRAWING_EXTENSIONS = {".dwg", ".dxf"}
#: STYLE table font fields we treat as a "font name" for ``fonts_missing``.
_FONT_EXTENSIONS = {".shx", ".ttf"}

#: ``engine/src/halo_engine/compare/ingest_set.py`` -> compare -> halo_engine
#: -> src -> engine -> repo root (same depth as ``api/jobs.py``).
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_ACAD_BRIDGE_BIN = _REPO_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"


def _now_iso() -> str:
    return datetime.now(UTC).replace(tzinfo=None).isoformat()


def _resolve_acad_bridge_bin(settings: Settings) -> Path | None:
    candidate = settings.acad_bridge_bin or _DEFAULT_ACAD_BRIDGE_BIN
    return candidate if candidate.is_file() else None


# ---------------------------------------------------------------------------
# plan_set_files
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedFile:
    """One file :func:`plan_set_files` found, before any row exists for it."""

    path: Path
    name: str
    format: DrawingFormat
    excluded: bool
    excluded_reason: str | None


def _xref_search_paths(set_dir: Path) -> list[str]:
    """``[set_dir, set_dir/XR, set_dir/../XR]`` -- existing directories only, in that order.

    Matching is case-insensitive on the folder name (``XR`` / ``xr`` / ``Xr``)
    because the sets come from Windows file systems.
    """
    paths: list[str] = [str(set_dir)]
    for parent in (set_dir, set_dir.parent):
        try:
            children = sorted(parent.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            continue
        for child in children:
            if child.is_dir() and child.name.lower() == "xr":
                candidate = str(child)
                if candidate not in paths:
                    paths.append(candidate)
                break
    return paths


def plan_set_files(source_dir: Path | str, ignore_patterns: Sequence[str]) -> list[PlannedFile]:
    """List ``source_dir`` non-recursively, ``.dwg``/``.dxf`` only, sorted case-insensitively.

    A file matching ``ignore_patterns`` (``compare.yaml`` ``ingest.ignore_patterns``,
    the R1 source of truth per contract §5 -- this function never reads the
    older ``project.ignore_patterns``) is still returned, marked ``excluded``,
    so the caller can still create its ``drawing_file`` row with
    ``excluded_reason="ignore_pattern"`` (contract Goal 1) instead of silently
    dropping it from the file list.
    """
    directory = Path(source_dir)
    candidates = [
        p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _DRAWING_EXTENSIONS
    ]
    candidates.sort(key=lambda p: p.name.casefold())
    planned: list[PlannedFile] = []
    for p in candidates:
        excluded = is_ignored_name(p.name, ignore_patterns)
        planned.append(
            PlannedFile(
                path=p,
                name=p.name,
                format=pipeline.detect_format(p),
                excluded=excluded,
                excluded_reason="ignore_pattern" if excluded else None,
            )
        )
    return planned


def norm_key(name: str) -> str:
    """Case/extension-insensitive file identity (Defaults for ambiguity: "같은 파일
    이름이 대소문자만 다르면 같은 파일로 본다"), used by :func:`enforce_same_converter`.
    """
    return Path(name).stem.strip().casefold()


# ---------------------------------------------------------------------------
# pick_converter / enforce_same_converter
# ---------------------------------------------------------------------------


def pick_converter(zwcad_status: zwcad.ZwcadStatus, option: str) -> ConverterChoice:
    """Which converter a DWG file should try first (contract §6, Goal 2).

    ``option`` is ``compare.yaml`` ``ingest.converter`` (or a per-run
    ``options.converter`` override): ``builtin`` never touches ZWCAD;
    ``zwcad`` always targets it (the caller decides what "없으면 실패" means
    when :attr:`~halo_engine.compare.zwcad.ZwcadStatus.available` is
    ``False`` -- see ``run_compare_set_ingest``'s docstring); ``auto`` picks
    ZWCAD only when it is actually usable right now.
    """
    if option == "builtin":
        return "builtin"
    if option == "zwcad":
        return "zwcad-com"
    return "zwcad-com" if zwcad_status.available else "builtin"


@dataclass(frozen=True)
class ConvertedFileInfo:
    """One converted (non-excluded) file's identity, for the same-converter rule."""

    role: Role
    row_id: str
    norm_key: str
    converter: str | None


def enforce_same_converter(files: Sequence[ConvertedFileInfo]) -> frozenset[str]:
    """``drawing_file.id`` values that must be (re-)converted with ``builtin``.

    Contract Goal 2, "같은 변환기 규칙(1차)": once *any* file on either side
    used ``builtin``, its same-named (:func:`norm_key`) counterpart on the
    other side must end up on ``builtin`` too, even if it already finished
    on ZWCAD -- final pair-level enforcement is R1-04's job (frame/pair
    matching does not exist yet here); this is only the file-name heuristic
    R1-03 owns. A file whose converter is ``None`` (a DXF input, or a sha256
    cache hit that skipped conversion entirely) never triggers or receives
    this -- there is no second converter to disagree with.
    """
    builtin_keys = {f.norm_key for f in files if f.converter == "builtin"}
    return frozenset(
        f.row_id for f in files if f.norm_key in builtin_keys and f.converter == "zwcad-com"
    )


# ---------------------------------------------------------------------------
# font names / fonts_missing
# ---------------------------------------------------------------------------


def read_font_names(working_dxf_path: str) -> list[str]:
    """STYLE table font/bigfont names of a working DXF, deduped and sorted.

    Picklable (module-level, plain ``str`` argument) so it can run in the
    shared ``ProcessPoolExecutor`` alongside the other per-file steps.
    """
    doc = ezdxf.readfile(working_dxf_path)
    names: set[str] = set()
    for style in doc.styles:
        font = str(style.dxf.get("font", "") or "").strip()
        bigfont = str(style.dxf.get("bigfont", "") or "").strip()
        if font:
            names.add(font)
        if bigfont:
            names.add(bigfont)
    return sorted(names)


def _font_stem(name: str) -> str:
    return Path(name).stem.casefold()


def _dir_font_stems(directory: Path) -> set[str]:
    if not directory.is_dir():
        return set()
    try:
        return {
            _font_stem(p.name)
            for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in _FONT_EXTENSIONS
        }
    except OSError:  # pragma: no cover - defensive, e.g. a permissions surprise
        return set()


def _installed_font_dirs() -> list[Path]:
    """Every system font folder named in contract Goal 6, checked regardless of
    the host OS -- the ones for the *other* OS simply do not exist and cost
    one harmless ``is_dir()`` each."""
    dirs = [
        Path("C:/Windows/Fonts"),
        Path("/Library/Fonts"),
        Path("/System/Library/Fonts"),
        Path.home() / "Library" / "Fonts",
    ]
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        dirs.append(Path(local_appdata) / "Microsoft" / "Windows" / "Fonts")
    return dirs


def compute_fonts_missing(
    font_names: Sequence[str], *, project_dir: Path, bundle_root: Path
) -> list[str]:
    """Names in ``font_names`` with no matching file anywhere fonts are looked for.

    Contract Goal 6: system font folders (Windows and macOS, both checked
    unconditionally) plus ``<project_dir>/fonts`` and ``<bundle>/fonts``,
    matched case-insensitively and ignoring the ``.shx``/``.ttf`` extension.
    """
    installed: set[str] = set()
    for directory in [*_installed_font_dirs(), project_dir / "fonts", bundle_root / "fonts"]:
        installed |= _dir_font_stems(directory)
    return sorted({name for name in font_names if _font_stem(name) not in installed})


# ---------------------------------------------------------------------------
# log file
# ---------------------------------------------------------------------------


class SetLog:
    """``.halo/log/<compare_set_id>.log`` writer (contract Constraints: UTF-8,
    ``<ISO 시각>\\t<level>\\t<file>\\t<message>`` per line)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, level: str, file: str, message: str) -> None:
        line = f"{_now_iso()}\t{level}\t{file}\t{message}\n"
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(line)


# ---------------------------------------------------------------------------
# builtin (desktop WS / acad-ts) conversion -- same priority as
# api/jobs.py::_import_one_file's DWG branch, kept independent (that
# function is private and tied to the plain import job's own status/gate
# bookkeeping).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _BuiltinConvertResult:
    dxf_path: str
    entity_count: int
    converter: str


async def _convert_builtin(
    *,
    loop: Any,
    executor: Executor,
    connections: ConnectionManager,
    converter_fallback: str | None,
    file_id: str,
    source_path: Path,
    out_path: Path,
    acad_bridge_bin: Path | None,
) -> _BuiltinConvertResult:
    reasons: list[str] = []
    if connections.has_clients():
        try:
            payload = await connections.request_conversion(
                file_id=file_id,
                dwg_path=str(source_path),
                out_path=str(out_path),
                timeout_s=CONVERT_TIMEOUT_S,
            )
            return _BuiltinConvertResult(
                dxf_path=str(payload["dxf_path"]),
                entity_count=int(payload["entity_count"]),
                converter=str(payload["converter"]),
            )
        except Exception as exc:  # noqa: BLE001 - falls through to acad-ts below
            reasons.append(f"desktop: {exc}")

    if converter_fallback == "acad-ts" and acad_bridge_bin is not None:
        try:
            result = await loop.run_in_executor(
                executor,
                pipeline.run_acad_ts_fallback,
                str(source_path),
                str(out_path),
                str(acad_bridge_bin),
            )
            return _BuiltinConvertResult(
                dxf_path=result.dxf_path,
                entity_count=result.entity_count,
                converter=result.converter,
            )
        except Exception as exc:  # noqa: BLE001 - reported below with the desktop attempt
            reasons.append(f"acad-ts: {exc}")

    raise RuntimeError(
        "no builtin converter available"
        if not reasons
        else "builtin conversion failed: " + " | ".join(reasons)
    )


# ---------------------------------------------------------------------------
# per-file processing
# ---------------------------------------------------------------------------


@dataclass
class _FileTask:
    row_id: str
    role: Role
    source_path: Path
    name: str
    format: DrawingFormat


def _update_file(bundle: BundleHandle, file_id: str, **fields: Any) -> None:
    with bundle.session_factory() as session:
        repos.update_drawing_file(session, file_id, **fields)


def _mirror_working_dxf_to_original_sha(
    working: pipeline.WorkingDxfStepResult, working_dxf_path: Path, stats_path: Path
) -> None:
    """Copy the just-built working DXF/stats under *our* original-file-sha256 key.

    ``ingest/working_dxf.py``'s own ``<sha>.working.dxf`` naming keys off
    *its own input's* sha256 -- the original file for a DXF source, but
    whichever DXF a converter just produced for a DWG source
    (``build_working_dxf_step``'s docstring: "input_dxf_path is either the
    user's original DXF... or the DXF a converter just produced"). The
    sha256 cache this module promises (contract Goal 2, "같은 sha256의
    cache/dxf/<sha>.working.dxf") is keyed by the *original* file
    (``copy_original_step``'s sha256, computed before any conversion), so a
    DWG source needs this second, original-sha-keyed copy for a later file
    with the same original bytes to find without re-running the converter.
    A DXF source's own key already matches (no conversion happened), so the
    comparison below makes this a no-op then.
    """
    if Path(working.working_dxf_path) == working_dxf_path:
        return
    shutil.copyfile(working.working_dxf_path, working_dxf_path)
    shutil.copyfile(working.stats_json_path, stats_path)


async def _process_file(
    *,
    loop: Any,
    executor: Executor,
    zwcad_executor: Executor,
    connections: ConnectionManager,
    settings: Settings,
    bundle: BundleHandle,
    log: SetLog,
    task: _FileTask,
    converter_option: str,
    zwcad_status: zwcad.ZwcadStatus,
    zwcad_conv: zwcad.ZwcadConverter | None,
    zwcad_com: zwcad.ComBackend | None,
    ingest_settings: IngestSettings,
    converter_fallback: str | None,
    acad_bridge_bin: Path | None,
) -> tuple[ConvertedFileInfo, zwcad.ZwcadConverter | None]:
    """Copy + (convert) + build the working DXF for one file, updating its row.

    Returns the file's :class:`ConvertedFileInfo` (for the same-converter
    pass) and the possibly-just-created :class:`~halo_engine.compare.zwcad.ZwcadConverter`
    for this side, so the caller keeps reusing the one hidden instance
    across every DWG in the set (contract Goal 2: "세트당 숨은 인스턴스 하나").
    """
    cache_dxf_dir = bundle.layout.cache_dxf_dir

    _update_file(bundle, task.row_id, import_status=ImportStatus.COPYING.value)
    copy_result = await loop.run_in_executor(
        executor, pipeline.copy_original_step, str(task.source_path), str(bundle.layout.root)
    )
    _update_file(
        bundle,
        task.row_id,
        sha256=copy_result.sha256,
        format=copy_result.format.value,
        original_originals_path=copy_result.dest_path,
    )

    working_dxf_path = cache_dxf_dir / f"{copy_result.sha256}.working.dxf"
    stats_path = cache_dxf_dir / f"{copy_result.sha256}.stats.json"

    if working_dxf_path.is_file() and stats_path.is_file():
        # sha256 cache hit (contract Goal 2): another file with the same
        # original bytes -- possibly this very file, before_dir == after_dir
        # (Defaults for ambiguity) -- already produced this working DXF.
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        font_names = await loop.run_in_executor(executor, read_font_names, str(working_dxf_path))
        _update_file(
            bundle,
            task.row_id,
            import_status=ImportStatus.DONE.value,
            error_message=None,
            working_dxf_path=str(working_dxf_path),
            stats_json_path=str(stats_path),
            entity_count=int(stats.get("totals", {}).get("entity_count", 0)),
            converter=None,
            converter_meta={"cache_hit": True},
            font_names=font_names,
        )
        return (
            ConvertedFileInfo(
                role=task.role, row_id=task.row_id, norm_key=norm_key(task.name), converter=None
            ),
            zwcad_conv,
        )

    # XREF search paths for the working-DXF build: the file's own folder plus the
    # conventional `XR` folders next to / above the set folder (brief R1-03
    # "Defaults for ambiguity"; the real set references `..\XR\*.dwg`, see
    # docs/spikes/real-dwg-measurement.md). Only folders that exist are added,
    # so synthetic sets without XREFs are unaffected.
    search_paths = _xref_search_paths(task.source_path.parent)
    converter_used: str | None = None
    converter_meta: dict[str, Any] | None = None

    if task.format is DrawingFormat.DXF:
        input_dxf_path: Path = task.source_path
    else:
        target = pick_converter(zwcad_status, converter_option)
        if target == "zwcad-com" and not zwcad_status.available:
            # contract Goal 2 / compare.yaml `ingest.converter: zwcad`: this
            # machine has no usable ZWCAD at all, so a request that pinned
            # `zwcad` fails outright rather than silently using builtin --
            # unlike a *runtime* ZwcadError below, which does fall back.
            reason = zwcad_status.reason or "unavailable"
            _update_file(
                bundle,
                task.row_id,
                import_status=ImportStatus.FAILED.value,
                error_message=f"zwcad requested but not available: {reason}",
            )
            log.write("ERROR", task.name, f"zwcad requested but not available: {reason}")
            return (
                ConvertedFileInfo(
                    role=task.role, row_id=task.row_id, norm_key=norm_key(task.name), converter=None
                ),
                zwcad_conv,
            )

        if target == "zwcad-com":
            _update_file(bundle, task.row_id, import_status=ImportStatus.CONVERTING.value)
            if zwcad_conv is None:
                zwcad_conv = await loop.run_in_executor(
                    zwcad_executor,
                    lambda: zwcad.ZwcadConverter(
                        timeout_s=ingest_settings.zwcad_timeout_s,
                        dxf_version=ingest_settings.zwcad_dxf_version,
                        com=zwcad_com,
                    ),
                )
            zwcad_out = cache_dxf_dir / f"{copy_result.sha256}.zwcad.dxf"
            try:
                result = await loop.run_in_executor(
                    zwcad_executor,
                    zwcad_conv.convert_dwg_to_dxf,
                    Path(copy_result.dest_path),
                    zwcad_out,
                )
                input_dxf_path = zwcad_out
                converter_used = "zwcad-com"
                converter_meta = {
                    "zwcad_version": result.zwcad_version,
                    "elapsed_s": result.elapsed_s,
                    "warnings": result.warnings,
                }
            except zwcad.ZwcadError as exc:
                # Runtime ZWCAD failure (timeout, COM error, ...): falls back
                # to builtin regardless of `option` (contract Goal 2: "실패
                # (ZwcadError)하면 그 파일은 builtin으로 재시도") -- distinct
                # from the machine-wide "not available" case above, which
                # `option == "zwcad"` refuses to paper over.
                log.write("WARN", task.name, f"zwcad failed, falling back to builtin: {exc}")
                fallback_reason = str(exc)
                try:
                    builtin_out = cache_dxf_dir / f"{copy_result.sha256}.builtin.dxf"
                    builtin = await _convert_builtin(
                        loop=loop,
                        executor=executor,
                        connections=connections,
                        converter_fallback=converter_fallback,
                        file_id=task.row_id,
                        source_path=task.source_path,
                        out_path=builtin_out,
                        acad_bridge_bin=acad_bridge_bin,
                    )
                except Exception as exc2:  # noqa: BLE001 - both attempts failed; report both
                    _update_file(
                        bundle,
                        task.row_id,
                        import_status=ImportStatus.FAILED.value,
                        error_message=f"zwcad: {exc}; builtin: {exc2}",
                    )
                    log.write("ERROR", task.name, f"zwcad and builtin both failed: {exc2}")
                    return (
                        ConvertedFileInfo(
                            role=task.role,
                            row_id=task.row_id,
                            norm_key=norm_key(task.name),
                            converter=None,
                        ),
                        zwcad_conv,
                    )
                input_dxf_path = Path(builtin.dxf_path)
                converter_used = "builtin"
                converter_meta = {"fallback_reason": fallback_reason}
        else:
            _update_file(bundle, task.row_id, import_status=ImportStatus.CONVERTING.value)
            builtin_out = cache_dxf_dir / f"{copy_result.sha256}.builtin.dxf"
            try:
                builtin = await _convert_builtin(
                    loop=loop,
                    executor=executor,
                    connections=connections,
                    converter_fallback=converter_fallback,
                    file_id=task.row_id,
                    source_path=task.source_path,
                    out_path=builtin_out,
                    acad_bridge_bin=acad_bridge_bin,
                )
            except Exception as exc:
                status = (
                    ImportStatus.NEEDS_MANUAL_CONVERSION.value
                    if not connections.has_clients() and converter_fallback != "acad-ts"
                    else ImportStatus.FAILED.value
                )
                _update_file(bundle, task.row_id, import_status=status, error_message=str(exc))
                log.write("ERROR", task.name, f"builtin conversion failed: {exc}")
                return (
                    ConvertedFileInfo(
                        role=task.role,
                        row_id=task.row_id,
                        norm_key=norm_key(task.name),
                        converter=None,
                    ),
                    zwcad_conv,
                )
            input_dxf_path = Path(builtin.dxf_path)
            converter_used = "builtin"

    _update_file(bundle, task.row_id, import_status=ImportStatus.BUILDING_WORKING_DXF.value)
    try:
        working = await loop.run_in_executor(
            executor,
            pipeline.build_working_dxf_step,
            str(input_dxf_path),
            str(cache_dxf_dir),
            search_paths,
            str(acad_bridge_bin) if acad_bridge_bin else None,
            list(ingest_settings.ignore_patterns),
        )
    except Exception as exc:
        _update_file(
            bundle, task.row_id, import_status=ImportStatus.FAILED.value, error_message=str(exc)
        )
        log.write("ERROR", task.name, f"working dxf build failed: {exc}")
        return (
            ConvertedFileInfo(
                role=task.role,
                row_id=task.row_id,
                norm_key=norm_key(task.name),
                converter=converter_used,
            ),
            zwcad_conv,
        )

    await loop.run_in_executor(
        executor, _mirror_working_dxf_to_original_sha, working, working_dxf_path, stats_path
    )
    font_names = await loop.run_in_executor(executor, read_font_names, working.working_dxf_path)
    totals = working.stats.get("totals", {})
    _update_file(
        bundle,
        task.row_id,
        import_status=ImportStatus.DONE.value,
        error_message=None,
        # Always the original-file-sha256-keyed path (mirrored above when
        # `build_working_dxf_step` itself keyed off a converted DXF's own
        # sha256 instead) -- the row's canonical location, and the path a
        # later sha256 cache hit for the same original bytes checks.
        working_dxf_path=str(working_dxf_path),
        stats_json_path=str(stats_path),
        codepage_declared=working.codepage_declared,
        codepage_effective=working.codepage_effective,
        entity_count=int(totals.get("entity_count", 0)),
        converter=converter_used,
        converter_meta=converter_meta,
        font_names=font_names,
    )
    return (
        ConvertedFileInfo(
            role=task.role,
            row_id=task.row_id,
            norm_key=norm_key(task.name),
            converter=converter_used,
        ),
        zwcad_conv,
    )


# ---------------------------------------------------------------------------
# same-converter enforcement: re-convert a file that must switch off ZWCAD
# ---------------------------------------------------------------------------


async def _reconvert_as_builtin(
    *,
    loop: Any,
    executor: Executor,
    connections: ConnectionManager,
    bundle: BundleHandle,
    log: SetLog,
    row: DrawingFileRow,
    ingest_settings: IngestSettings,
    converter_fallback: str | None,
    acad_bridge_bin: Path | None,
) -> str | None:
    """Re-runs the builtin converter for a file :func:`enforce_same_converter` flagged.

    Returns ``"builtin"`` on success, or ``None`` if the reconversion itself
    failed -- the row is left exactly as it was (still ``DONE`` on
    ``zwcad-com``) rather than turning a previously-successful file into
    ``FAILED`` over a same-converter *preference*; the mismatch is logged
    instead (contract does not specify a stronger response for this case).
    """
    source_path = Path(row.original_path)
    cache_dxf_dir = bundle.layout.cache_dxf_dir
    out_path = cache_dxf_dir / f"{row.sha256}.builtin.dxf"
    try:
        builtin = await _convert_builtin(
            loop=loop,
            executor=executor,
            connections=connections,
            converter_fallback=converter_fallback,
            file_id=row.id,
            source_path=source_path,
            out_path=out_path,
            acad_bridge_bin=acad_bridge_bin,
        )
        working = await loop.run_in_executor(
            executor,
            pipeline.build_working_dxf_step,
            builtin.dxf_path,
            str(cache_dxf_dir),
            [str(source_path.parent)],
            str(acad_bridge_bin) if acad_bridge_bin else None,
            list(ingest_settings.ignore_patterns),
        )
    except Exception as exc:  # noqa: BLE001 - keep the file on its previous converter
        log.write(
            "WARN",
            row.original_name,
            f"same-converter enforcement failed, keeping {row.converter}: {exc}",
        )
        return None

    working_dxf_path = cache_dxf_dir / f"{row.sha256}.working.dxf"
    stats_path = cache_dxf_dir / f"{row.sha256}.stats.json"
    await loop.run_in_executor(
        executor, _mirror_working_dxf_to_original_sha, working, working_dxf_path, stats_path
    )
    font_names = await loop.run_in_executor(executor, read_font_names, working.working_dxf_path)
    totals = working.stats.get("totals", {})
    _update_file(
        bundle,
        row.id,
        working_dxf_path=str(working_dxf_path),
        stats_json_path=str(stats_path),
        codepage_declared=working.codepage_declared,
        codepage_effective=working.codepage_effective,
        entity_count=int(totals.get("entity_count", 0)),
        converter="builtin",
        converter_meta={"same_converter_forced": True},
        font_names=font_names,
        import_status=ImportStatus.DONE.value,
        error_message=None,
    )
    log.write("INFO", row.original_name, "re-converted with builtin to match the other side")
    return "builtin"


# ---------------------------------------------------------------------------
# one side (before or after) of the set
# ---------------------------------------------------------------------------


async def _ingest_side(
    *,
    role: Role,
    rows: list[DrawingFileRow],
    loop: Any,
    executor: Executor,
    zwcad_executor: Executor,
    connections: ConnectionManager,
    settings: Settings,
    bundle: BundleHandle,
    log: SetLog,
    converter_option: str,
    zwcad_status: zwcad.ZwcadStatus,
    zwcad_com: zwcad.ComBackend | None,
    ingest_settings: IngestSettings,
    converter_fallback: str | None,
    acad_bridge_bin: Path | None,
    reporter: ProgressReporter,
    jobs: Any,
    job: JobRecord,
    progress_state: list[int],
) -> list[ConvertedFileInfo]:
    """Converts every non-excluded row of one side, one hidden ZWCAD instance for
    the whole side (contract Goal 2: "세트당 숨은 인스턴스 하나"), closed once this
    side is done or on cancel/error."""
    infos: list[ConvertedFileInfo] = []
    non_excluded_total = sum(1 for r in rows if r.import_status != ImportStatus.EXCLUDED.value)
    zwcad_conv: zwcad.ZwcadConverter | None = None
    side_index = 0
    try:
        for row in rows:
            current = jobs.get(job.id)
            if current is not None and current.cancel_requested:
                raise JobCancelled

            if row.import_status == ImportStatus.EXCLUDED.value:
                progress_state[0] += 1
                await reporter(
                    progress_state[0] / progress_state[1] if progress_state[1] else 1.0,
                    f"skip {role} {row.original_name}",
                    stage="convert",
                    extra={
                        "role": role,
                        "index": side_index,
                        "total": non_excluded_total,
                        "file": row.original_name,
                        "converter": None,
                    },
                )
                continue

            side_index += 1
            task = _FileTask(
                row_id=row.id,
                role=role,
                source_path=Path(row.original_path),
                name=row.original_name,
                format=DrawingFormat(row.format),
            )
            info, zwcad_conv = await _process_file(
                loop=loop,
                executor=executor,
                zwcad_executor=zwcad_executor,
                connections=connections,
                settings=settings,
                bundle=bundle,
                log=log,
                task=task,
                converter_option=converter_option,
                zwcad_status=zwcad_status,
                zwcad_conv=zwcad_conv,
                zwcad_com=zwcad_com,
                ingest_settings=ingest_settings,
                converter_fallback=converter_fallback,
                acad_bridge_bin=acad_bridge_bin,
            )
            infos.append(info)
            progress_state[0] += 1
            await reporter(
                progress_state[0] / progress_state[1] if progress_state[1] else 1.0,
                f"convert {side_index}/{non_excluded_total} {role} {row.original_name}",
                stage="convert",
                extra={
                    "role": role,
                    "index": side_index,
                    "total": non_excluded_total,
                    "file": row.original_name,
                    "converter": info.converter,
                },
            )
    finally:
        if zwcad_conv is not None:
            await loop.run_in_executor(zwcad_executor, zwcad_conv.__exit__, None, None, None)
    return infos


# ---------------------------------------------------------------------------
# sample crosscheck (contract Goal 3)
# ---------------------------------------------------------------------------


async def _run_sample_crosscheck(
    *,
    loop: Any,
    executor: Executor,
    connections: ConnectionManager,
    bundle: BundleHandle,
    log: SetLog,
    before_rows: list[DrawingFileRow],
    after_rows: list[DrawingFileRow],
    crosscheck_sample: int,
    converter_fallback: str | None,
    acad_bridge_bin: Path | None,
) -> dict[str, Any]:
    """Converts up to ``crosscheck_sample`` ZWCAD-converted files per side with the
    builtin converter too, and diffs their stats (contract Goal 3).

    Only meaningful on a machine that can actually run *both* converters --
    otherwise there is nothing to compare a ZWCAD result against, so this
    returns a ``skipped`` reason instead of pretending to have checked
    anything (``CompareSetSummary.crosscheck`` stays a plain ``{sampled,
    mismatched}`` pair -- ``skipped`` is bookkeeping kept only in
    ``compare_set.stats``, the internal column, not the public schema).
    """
    status = zwcad.detect()
    builtin_reachable = connections.has_clients() or (
        converter_fallback == "acad-ts" and acad_bridge_bin is not None
    )
    if not status.available:
        return {"sampled": 0, "mismatched": 0, "skipped": "zwcad_unavailable"}
    if not builtin_reachable:
        return {"sampled": 0, "mismatched": 0, "skipped": "no_builtin_converter"}
    if crosscheck_sample <= 0:
        return {"sampled": 0, "mismatched": 0, "skipped": "crosscheck_sample_zero"}

    candidates: list[DrawingFileRow] = []
    for rows in (before_rows, after_rows):
        count = 0
        for row in rows:
            if count >= crosscheck_sample:
                break
            if row.converter == "zwcad-com" and row.import_status == ImportStatus.DONE.value:
                candidates.append(row)
                count += 1

    if not candidates:
        return {"sampled": 0, "mismatched": 0, "skipped": "no_zwcad_converted_files"}

    sampled = 0
    mismatched = 0
    for row in candidates:
        sampled += 1
        out_path = bundle.layout.cache_dxf_dir / f"{row.sha256}.crosscheck.dxf"
        try:
            builtin = await _convert_builtin(
                loop=loop,
                executor=executor,
                connections=connections,
                converter_fallback=converter_fallback,
                file_id=row.id,
                source_path=Path(row.original_path),
                out_path=out_path,
                acad_bridge_bin=acad_bridge_bin,
            )
            working = await loop.run_in_executor(
                executor,
                pipeline.build_working_dxf_step,
                builtin.dxf_path,
                str(bundle.layout.cache_dxf_dir),
                [str(Path(row.original_path).parent)],
                str(acad_bridge_bin) if acad_bridge_bin else None,
                None,
            )
            if row.stats_json_path is None:  # defensive: DONE rows always have one
                raise RuntimeError("DONE row has no stats_json_path")
            reference_stats = json.loads(Path(row.stats_json_path).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - one sample's conversion failing skips it
            log.write("WARN", row.original_name, f"crosscheck conversion failed: {exc}")
            continue

        report = crosscheck_module.compare(reference_stats, working.stats)
        if report.status.value != "GREEN":
            mismatched += 1
            for layer_result in [*report.layers, report.totals]:
                for diff in layer_result.differences:
                    log.write(
                        "WARN",
                        row.original_name,
                        f"{diff.field.value} {diff.reference_value}→{diff.other_value}",
                    )
    return {"sampled": sampled, "mismatched": mismatched}


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------


def _tally(rows: list[DrawingFileRow]) -> tuple[int, int, int]:
    """(converted, failed, excluded) counts of one side's final rows."""
    converted = sum(1 for r in rows if r.import_status == ImportStatus.DONE.value)
    failed = sum(
        1
        for r in rows
        if r.import_status
        in (ImportStatus.FAILED.value, ImportStatus.NEEDS_MANUAL_CONVERSION.value)
    )
    excluded = sum(1 for r in rows if r.import_status == ImportStatus.EXCLUDED.value)
    return converted, failed, excluded


def _dominant_converter(rows: list[DrawingFileRow]) -> str | None:
    """The most-used non-null converter on one side, alphabetically first on a tie."""
    counts: dict[str, int] = {}
    for row in rows:
        if row.converter:
            counts[row.converter] = counts.get(row.converter, 0) + 1
    if not counts:
        return None
    return max(sorted(counts), key=lambda key: counts[key])


async def run_compare_set_ingest(
    app: FastAPI,
    *,
    job: JobRecord,
    bundle: BundleHandle,
    compare_set_id: str,
    zwcad_com: zwcad.ComBackend | None = None,
) -> None:
    """The ``compare.ingest`` job body (contract §6, §6.2).

    ``zwcad_com`` is a test-only injection point (default ``None`` uses the
    real COM backend) -- a production caller (``api/routers/compare_sets.py``)
    never passes it; tests provide ``fake_com.FakeComBackend`` to exercise
    the ZWCAD path without real COM, the same seam ``compare/zwcad.py``'s
    own suite uses.
    """
    jobs = get_job_manager(app)
    connections = get_connection_manager(app)
    settings: Settings = app.state.settings

    async def _work(reporter: ProgressReporter) -> None:
        await _do_ingest(
            jobs=jobs,
            connections=connections,
            settings=settings,
            bundle=bundle,
            compare_set_id=compare_set_id,
            job=job,
            reporter=reporter,
            zwcad_com=zwcad_com,
        )

    await run_job(app, job, _work)


async def _do_ingest(
    *,
    jobs: Any,
    connections: ConnectionManager,
    settings: Settings,
    bundle: BundleHandle,
    compare_set_id: str,
    job: JobRecord,
    reporter: ProgressReporter,
    zwcad_com: zwcad.ComBackend | None,
) -> None:
    loop = asyncio.get_running_loop()
    executor = jobs.executor

    with bundle.session_factory() as session:
        compare_set = repos.get_compare_set(session, compare_set_id)
        if compare_set is None:
            raise KeyError(f"compare_set {compare_set_id!r} not found")
        before_set_id = compare_set.before_set_id
        after_set_id = compare_set.after_set_id
        options = dict(compare_set.options or {})
        before_rows = repos.list_files_for_set(session, before_set_id)
        after_rows = repos.list_files_for_set(session, after_set_id)

    project_dir = bundle.layout.root.parent
    config = load_compare_config(bundle)
    converter_option = str(options.get("converter") or config.ingest.converter)
    crosscheck_sample = int(options.get("crosscheck_sample", config.ingest.crosscheck_sample))
    converter_fallback = options.get("converter_fallback") or settings.converter_fallback

    zwcad_status = zwcad.detect()
    log = SetLog(bundle.layout.log_dir / f"{compare_set_id}.log")
    acad_bridge_bin = _resolve_acad_bridge_bin(settings)

    total = len(before_rows) + len(after_rows)
    progress_state = [0, total]

    zwcad_executor = ThreadPoolExecutor(max_workers=1)
    try:
        before_infos = await _ingest_side(
            role="before",
            rows=before_rows,
            loop=loop,
            executor=executor,
            zwcad_executor=zwcad_executor,
            connections=connections,
            settings=settings,
            bundle=bundle,
            log=log,
            converter_option=converter_option,
            zwcad_status=zwcad_status,
            zwcad_com=zwcad_com,
            ingest_settings=config.ingest,
            converter_fallback=converter_fallback,
            acad_bridge_bin=acad_bridge_bin,
            reporter=reporter,
            jobs=jobs,
            job=job,
            progress_state=progress_state,
        )
        after_infos = await _ingest_side(
            role="after",
            rows=after_rows,
            loop=loop,
            executor=executor,
            zwcad_executor=zwcad_executor,
            connections=connections,
            settings=settings,
            bundle=bundle,
            log=log,
            converter_option=converter_option,
            zwcad_status=zwcad_status,
            zwcad_com=zwcad_com,
            ingest_settings=config.ingest,
            converter_fallback=converter_fallback,
            acad_bridge_bin=acad_bridge_bin,
            reporter=reporter,
            jobs=jobs,
            job=job,
            progress_state=progress_state,
        )
    finally:
        zwcad_executor.shutdown(wait=True)

    # Same-converter enforcement (contract Goal 2): re-convert whichever side
    # still disagrees with its same-named counterpart, by row id.
    forced_ids = enforce_same_converter([*before_infos, *after_infos])
    if forced_ids:
        with bundle.session_factory() as session:
            forced_rows = [
                row
                for row in [
                    *repos.list_files_for_set(session, before_set_id),
                    *repos.list_files_for_set(session, after_set_id),
                ]
                if row.id in forced_ids
            ]
        for row in forced_rows:
            current = jobs.get(job.id)
            if current is not None and current.cancel_requested:
                raise JobCancelled
            await _reconvert_as_builtin(
                loop=loop,
                executor=executor,
                connections=connections,
                bundle=bundle,
                log=log,
                row=row,
                ingest_settings=config.ingest,
                converter_fallback=converter_fallback,
                acad_bridge_bin=acad_bridge_bin,
            )

    with bundle.session_factory() as session:
        final_before_rows = repos.list_files_for_set(session, before_set_id)
        final_after_rows = repos.list_files_for_set(session, after_set_id)

    crosscheck_result = await _run_sample_crosscheck(
        loop=loop,
        executor=executor,
        connections=connections,
        bundle=bundle,
        log=log,
        before_rows=final_before_rows,
        after_rows=final_after_rows,
        crosscheck_sample=crosscheck_sample,
        converter_fallback=converter_fallback,
        acad_bridge_bin=acad_bridge_bin,
    )

    before_converted, before_failed, before_excluded = _tally(final_before_rows)
    after_converted, after_failed, after_excluded = _tally(final_after_rows)

    before_dominant = _dominant_converter(final_before_rows)
    after_dominant = _dominant_converter(final_after_rows)

    def _mismatch_count(rows: list[DrawingFileRow], dominant: str | None) -> int:
        if dominant is None:
            return 0
        return sum(1 for r in rows if r.converter and r.converter != dominant)

    mismatch_files = _mismatch_count(final_before_rows, before_dominant) + _mismatch_count(
        final_after_rows, after_dominant
    )

    all_font_names: set[str] = set()
    for row in [*final_before_rows, *final_after_rows]:
        if row.font_names:
            all_font_names.update(row.font_names)
    fonts_missing = compute_fonts_missing(
        sorted(all_font_names), project_dir=project_dir, bundle_root=bundle.layout.root
    )

    converter_counts: dict[str, int] = {}
    for row in [*final_before_rows, *final_after_rows]:
        key = row.converter or "none"
        converter_counts[key] = converter_counts.get(key, 0) + 1

    total_converted = before_converted + after_converted
    total_failed = before_failed + after_failed
    new_status = "failed" if (total_failed > 0 and total_converted == 0) else "ingested"

    stats: dict[str, Any] = {
        "last_job_id": job.id,
        "files": {
            "before": len(final_before_rows),
            "after": len(final_after_rows),
            "total": len(final_before_rows) + len(final_after_rows),
        },
        "converted": {"before": before_converted, "after": after_converted},
        "failed": {"before": before_failed, "after": after_failed},
        "excluded": {"before": before_excluded, "after": after_excluded},
        "converter_counts": converter_counts,
        "converter": {
            "before": before_dominant,
            "after": after_dominant,
            "mismatch_files": mismatch_files,
        },
        "fonts_missing": fonts_missing,
        "crosscheck": crosscheck_result,
    }
    with bundle.session_factory() as session:
        repos.update_compare_set(session, compare_set_id, status=new_status, stats=stats)


__all__ = [
    "ConvertedFileInfo",
    "PlannedFile",
    "SetLog",
    "compute_fonts_missing",
    "enforce_same_converter",
    "norm_key",
    "pick_converter",
    "plan_set_files",
    "read_font_names",
    "run_compare_set_ingest",
]
