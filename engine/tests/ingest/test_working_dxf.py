from __future__ import annotations

import json
from pathlib import Path

import ezdxf

from halo_engine.ingest.working_dxf import (
    WORKING_DXF_VERSION,
    build_working_dxf,
)


def test_build_working_dxf_on_f10_host(generated_dir: Path, tmp_path: Path) -> None:
    result = build_working_dxf(generated_dir / "F10_host.dxf", tmp_path)

    assert result.working_dxf_path.exists()
    assert result.working_meta_path.exists()
    assert result.stats_path.exists()
    assert result.handle_map_path.exists()
    assert result.recovered is False
    assert result.xref_count > 0

    doc = ezdxf.readfile(str(result.working_dxf_path))
    assert doc.dxfversion == WORKING_DXF_VERSION
    # XREF is embedded: the F10_GRID block is no longer flagged as an xref
    # and now holds the grid file's content.
    block = doc.blocks["F10_GRID"]
    assert block.block.is_xref is False
    assert len(list(block)) > 0

    meta = json.loads(result.working_meta_path.read_text(encoding="utf-8"))
    assert meta["original_sha256"] == result.original_sha256
    assert meta["stats_path"] == result.stats_path.name
    assert meta["handle_map_path"] == result.handle_map_path.name
    assert meta["xref_count"] == result.xref_count

    stats = json.loads(result.stats_path.read_text(encoding="utf-8"))
    assert stats["file_sha256"] == result.working_sha256
    assert stats["totals"]["count_by_type"] == {"INSERT": 1, "LWPOLYLINE": 6, "TEXT": 6}

    handle_map = json.loads(result.handle_map_path.read_text(encoding="utf-8"))
    assert len(handle_map) == result.xref_count
    assert {e["xref_file"] for e in handle_map} == {"F10_grid.dxf"}


def test_build_working_dxf_is_deterministic_for_the_same_input(
    generated_dir: Path, tmp_path: Path
) -> None:
    """Same input -> same measured content (CLAUDE.md rule 7).

    The working DXF's *bytes* legitimately differ run to run: ezdxf assigns
    a fresh ``$FINGERPRINTGUID``/``$VERSIONGUID`` and save-timestamp comment
    on every ``saveas()``, by AutoCAD convention (a save fingerprint is
    supposed to be unique per save, not reproducible) -- that's not the
    "random seed" determinism rule 7 is about. What must be reproducible is
    everything the engine actually measures: entities, handles and stats.
    """
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"
    result_a = build_working_dxf(generated_dir / "F06.dxf", out_a)
    result_b = build_working_dxf(generated_dir / "F06.dxf", out_b)

    stats_a = json.loads(result_a.stats_path.read_text(encoding="utf-8"))
    stats_b = json.loads(result_b.stats_path.read_text(encoding="utf-8"))
    assert stats_a["buckets"] == stats_b["buckets"]
    assert stats_a["totals"] == stats_b["totals"]

    doc_a = ezdxf.readfile(str(result_a.working_dxf_path))
    doc_b = ezdxf.readfile(str(result_b.working_dxf_path))
    handles_a = [e.dxf.handle for e in doc_a.modelspace()]
    handles_b = [e.dxf.handle for e in doc_b.modelspace()]
    assert handles_a == handles_b


def test_build_working_dxf_r2000_cp949_gets_upgraded_and_correctly_decoded(
    generated_dir: Path, tmp_path: Path
) -> None:
    result = build_working_dxf(generated_dir / "F03_r2000_cp949.dxf", tmp_path)
    doc = ezdxf.readfile(str(result.working_dxf_path))
    assert doc.dxfversion == WORKING_DXF_VERSION
    text = next(iter(doc.modelspace().query("TEXT"))).dxf.text
    assert "�" not in text

    meta = json.loads(result.working_meta_path.read_text(encoding="utf-8"))
    assert meta["codepage_declared"] == "ANSI_949"
    assert meta["codepage_effective"] == "cp949"
