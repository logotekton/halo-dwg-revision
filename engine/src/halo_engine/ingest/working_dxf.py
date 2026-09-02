"""Working-DXF canonicalisation (ADR-0002): load + encoding correction + XREF
embedding, upgraded to R2018 (AC1032) UTF-8 and written as
``<sha256>.working.dxf`` next to its ``<sha256>.working.json`` metadata.

``sha256`` in both filenames is the **original** input file's hash (stable
across re-ingests of the same source, matching ADR-0002's
``originals/<sha256>`` naming) -- not the working DXF's own bytes, which are
recorded inside the metadata as ``working_sha256`` instead (and is what
``file_sha256`` in the stats document refers to, since that is the file both
the viewer and the engine actually parse).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from halo_engine.ingest.encoding import load_with_corrected_encoding
from halo_engine.ingest.stats import compute_layer_stats
from halo_engine.ingest.xref import HandleMapEntry, embed_all_xrefs

#: DXF version and encoding every working DXF is normalised to (ADR-0002).
WORKING_DXF_VERSION = "AC1032"
WORKING_ENCODING = "utf-8"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class WorkingDxfResult:
    original_sha256: str
    working_sha256: str
    working_dxf_path: Path
    working_meta_path: Path
    stats_path: Path
    handle_map_path: Path
    recovered: bool
    audit_error_count: int
    codepage_declared: str | None
    codepage_effective: str
    xref_count: int


def build_working_dxf(
    input_path: str | Path,
    out_dir: str | Path,
    *,
    search_paths: list[Path] | None = None,
) -> WorkingDxfResult:
    """Build the working-DXF canonical form of ``input_path`` under ``out_dir``.

    Steps (ADR-0002): load with recovery fallback, correct the encoding,
    embed every XREF, upgrade to R2018/UTF-8, save, then compute
    ``LayerStatsDocument`` stats and write the handle map -- all keyed off
    the *original* file's sha256.
    """
    input_path = Path(input_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    original_sha256 = _sha256_file(input_path)

    load_result, codepage_resolution = load_with_corrected_encoding(str(input_path))
    doc = load_result.doc

    handle_map: list[HandleMapEntry] = embed_all_xrefs(
        doc, host_dir=input_path.resolve().parent, search_paths=search_paths
    )

    doc.dxfversion = WORKING_DXF_VERSION
    # ezdxf writes R2007+ (>= AC1021) documents as UTF-8 unconditionally
    # (Drawing.output_encoding), so this assignment only keeps `doc.encoding`
    # itself from reporting a stale pre-upgrade codepage; it does not change
    # what gets written.
    doc.encoding = WORKING_ENCODING

    working_dxf_path = out_dir / f"{original_sha256}.working.dxf"
    doc.saveas(str(working_dxf_path))
    working_sha256 = _sha256_file(working_dxf_path)

    stats_doc = compute_layer_stats(doc, file_sha256=working_sha256)
    stats_path = out_dir / f"{original_sha256}.stats.json"
    stats_path.write_text(
        json.dumps(stats_doc, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    handle_map_path = out_dir / f"{original_sha256}.xref-handles.json"
    handle_map_path.write_text(
        json.dumps([e.to_dict() for e in handle_map], sort_keys=True, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    meta: dict[str, Any] = {
        "original_sha256": original_sha256,
        "working_sha256": working_sha256,
        "recovered": load_result.recovered,
        "audit_error_count": load_result.audit_error_count,
        "audit_errors": [e.to_dict() for e in load_result.audit_errors],
        "codepage_declared": codepage_resolution.codepage_declared,
        "codepage_effective": codepage_resolution.codepage_effective,
        "acadver_original": load_result.acadver,
        "insunits": load_result.insunits,
        "fingerprintguid": load_result.fingerprintguid,
        "xref_count": len(handle_map),
        "handle_map_path": handle_map_path.name,
        "stats_path": stats_path.name,
    }
    working_meta_path = out_dir / f"{original_sha256}.working.json"
    working_meta_path.write_text(
        json.dumps(meta, sort_keys=True, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return WorkingDxfResult(
        original_sha256=original_sha256,
        working_sha256=working_sha256,
        working_dxf_path=working_dxf_path,
        working_meta_path=working_meta_path,
        stats_path=stats_path,
        handle_map_path=handle_map_path,
        recovered=load_result.recovered,
        audit_error_count=load_result.audit_error_count,
        codepage_declared=codepage_resolution.codepage_declared,
        codepage_effective=codepage_resolution.codepage_effective,
        xref_count=len(handle_map),
    )


__all__ = ["WORKING_DXF_VERSION", "WORKING_ENCODING", "WorkingDxfResult", "build_working_dxf"]
