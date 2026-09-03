"""Import-job step composition (drawing-set import pipeline, brief W3-03).

``api/jobs.py`` is the async orchestrator; every step here is a small,
independently callable, picklable function so the CPU/subprocess-heavy ones
(:func:`copy_original_step`, :func:`run_acad_ts_fallback`,
:func:`build_working_dxf_step`) can run inside the brief's
``ProcessPoolExecutor(spawn, 2)`` via ``loop.run_in_executor`` without
dragging asyncio/FastAPI/WebSocket state across the process boundary. The
one step that cannot run in a worker process -- waiting for the desktop's
``convert.request`` -> ``converted`` round trip -- stays in ``api/jobs.py``,
which is why it has no counterpart here.

Nothing in this module imports ``halo_engine.api.*`` or touches a DB
session: every function takes plain, JSON/pickle-friendly arguments and
returns a small frozen dataclass, so it is independently unit-testable and
safe to hand to a spawned worker.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from halo_engine.bundle.layout import BundleLayout
from halo_engine.bundle.originals import copy_original
from halo_engine.ingest.working_dxf import build_working_dxf
from halo_engine.model.drawing import ConverterName, DrawingFormat

_DWG_EXTENSIONS = {".dwg"}
_DXF_EXTENSIONS = {".dxf"}

#: ADR-0002 2026-09-02 amendment, decision 4(c): relative entity-count tolerance.
ENTITY_COUNT_TOLERANCE = 0.005


def detect_format(path: Path) -> DrawingFormat:
    suffix = path.suffix.lower()
    if suffix in _DWG_EXTENSIONS:
        return DrawingFormat.DWG
    if suffix in _DXF_EXTENSIONS:
        return DrawingFormat.DXF
    raise ValueError(f"unsupported drawing format {path.suffix!r}: {path}")


# --- step 1: copy the original into the bundle (never write to the source) ----------------


@dataclass(frozen=True)
class CopyOriginalStepResult:
    sha256: str
    dest_path: str
    original_name: str
    format: DrawingFormat


def copy_original_step(source_path: str, bundle_root: str) -> CopyOriginalStepResult:
    """Runs in the process pool: hash + copy the source into ``<bundle_root>/originals/`` (0444)."""
    src = Path(source_path)
    layout = BundleLayout(Path(bundle_root))
    result = copy_original(src, layout)
    return CopyOriginalStepResult(
        sha256=result.sha256,
        dest_path=str(result.dest_path),
        original_name=src.name,
        format=detect_format(src),
    )


# --- step 2 (DWG only): acad-ts CLI fallback, when no desktop is connected ----------------


class ConverterFallbackError(RuntimeError):
    """The acad-ts CLI subprocess failed, or ``acad_bridge_bin`` was not found."""


@dataclass(frozen=True)
class ConverterFallbackResult:
    dxf_path: str
    entity_count: int
    converter: ConverterName
    dwg_version: str | None = None
    codepage_declared: str | None = None
    warnings: list[str] = field(default_factory=list)


def _run_acad_bridge(
    node_bin: str, acad_bridge_bin: str, args: list[str], *, timeout_s: float
) -> str:
    if not Path(acad_bridge_bin).is_file():
        raise ConverterFallbackError(f"acad-bridge CLI not found (not built?): {acad_bridge_bin}")
    try:
        proc = subprocess.run(
            [node_bin, acad_bridge_bin, *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except OSError as exc:
        raise ConverterFallbackError(f"could not run {node_bin} {acad_bridge_bin}: {exc}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ConverterFallbackError(
            f"acad-bridge {' '.join(args)} timed out after {timeout_s}s"
        ) from exc
    if proc.returncode != 0:
        raise ConverterFallbackError(
            f"acad-bridge {' '.join(args)} failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout


def run_acad_ts_fallback(
    dwg_path: str,
    out_dxf_path: str,
    acad_bridge_bin: str,
    *,
    node_bin: str = "node",
    timeout_s: float = 180.0,
) -> ConverterFallbackResult:
    """DWG -> DXF via ``node <acad_bridge_bin> dwg2dxf``, runs in the process pool.

    ``info`` (the same acad-ts DWG reader, run once more against the
    original) supplies the converter-reported entity count the crosscheck
    gate (ADR-0002 amendment 4c) needs -- ``dwg2dxf`` itself only prints a
    drop count, not an entity count.
    """
    info_json = _run_acad_bridge(node_bin, acad_bridge_bin, ["info", dwg_path], timeout_s=timeout_s)
    info: dict[str, Any] = json.loads(info_json)

    Path(out_dxf_path).parent.mkdir(parents=True, exist_ok=True)
    _run_acad_bridge(
        node_bin, acad_bridge_bin, ["dwg2dxf", dwg_path, out_dxf_path], timeout_s=timeout_s
    )

    return ConverterFallbackResult(
        dxf_path=out_dxf_path,
        entity_count=int(info.get("entity_count", 0)),
        converter="acad-ts",
        dwg_version=str(info["version"]) if info.get("version") else None,
        codepage_declared=str(info["code_page"]) if info.get("code_page") else None,
    )


# --- step 3: build the working-DXF canonical form (ADR-0002) ------------------------------


@dataclass(frozen=True)
class WorkingDxfStepResult:
    working_dxf_path: str
    stats_json_path: str
    stats: dict[str, Any]
    codepage_declared: str | None
    codepage_effective: str
    xref_count: int
    audit_error_count: int
    recovered: bool
    fingerprintguid: str | None = None


def build_working_dxf_step(
    input_dxf_path: str, cache_dxf_dir: str, search_paths: list[str]
) -> WorkingDxfStepResult:
    """Runs in the process pool: ``ingest/working_dxf.py``'s full working-DXF build.

    ``input_dxf_path`` is either the user's original DXF (contract step 5:
    DXF input skips conversion) or the DXF a converter just produced for a
    DWG source -- never the bundle's own ``originals/`` copy, so XREF
    resolution's "same folder as the host" tier keeps working off wherever
    the source (or its sibling XREFs) actually live.
    """
    result = build_working_dxf(
        Path(input_dxf_path), Path(cache_dxf_dir), search_paths=[Path(p) for p in search_paths]
    )
    stats = json.loads(result.stats_path.read_text(encoding="utf-8"))
    meta = json.loads(result.working_meta_path.read_text(encoding="utf-8"))
    return WorkingDxfStepResult(
        working_dxf_path=str(result.working_dxf_path),
        stats_json_path=str(result.stats_path),
        stats=stats,
        codepage_declared=result.codepage_declared,
        codepage_effective=result.codepage_effective,
        xref_count=result.xref_count,
        audit_error_count=result.audit_error_count,
        recovered=result.recovered,
        fingerprintguid=meta.get("fingerprintguid"),
    )


# --- step 4 (DWG only): the crosscheck gate (ADR-0002 2026-09-02 amendment, decision 4) ---


@dataclass(frozen=True)
class ConversionGateResult:
    passed: bool
    reasons: list[str]


def evaluate_conversion_gate(
    *,
    audit_error_count: int,
    engine_entity_count: int,
    converter_entity_count: int,
    tolerance: float = ENTITY_COUNT_TOLERANCE,
) -> ConversionGateResult:
    """ "변환 성공"은 stats 교차검증을 통과해야 성공이다(경고가 아니라 차단)" (ADR-0002).

    (a) the engine failing to open the converted DXF at all is handled by
    the caller catching :func:`build_working_dxf_step`'s exception before
    this is ever called; this covers (b) the auditor deleting entities on
    load and (c) a converter-reported entity count that disagrees with the
    engine's own count by more than ``tolerance``.
    """
    reasons: list[str] = []
    if audit_error_count > 0:
        reasons.append(
            f"auditor deleted {audit_error_count} entities while loading the converted DXF"
        )
    relative_delta = (
        0.0
        if engine_entity_count == 0
        else abs(converter_entity_count - engine_entity_count) / engine_entity_count
    )
    if relative_delta > tolerance:
        reasons.append(
            f"entity count mismatch: converter reported {converter_entity_count}, engine "
            f"counted {engine_entity_count} ({relative_delta * 100:.3f}% > {tolerance * 100:.3f}%)"
        )
    return ConversionGateResult(passed=not reasons, reasons=reasons)


__all__ = [
    "ENTITY_COUNT_TOLERANCE",
    "ConversionGateResult",
    "ConverterFallbackError",
    "ConverterFallbackResult",
    "CopyOriginalStepResult",
    "WorkingDxfStepResult",
    "build_working_dxf_step",
    "copy_original_step",
    "detect_format",
    "evaluate_conversion_gate",
    "run_acad_ts_fallback",
]
