"""Independent verification: re-reading each committed DXF with ezdxf and
recomputing statistics (fixtures_gen.stats.compute_layer_stats) must
reproduce exactly what's committed in fixtures/truth/F##.json (primary) and
F##.extra.json (r2000_cp949 variant) -- docs/contracts/stats-definition.md.
"""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf
import pytest
from conftest import COMMITTED_FIXTURE_IDS, GENERATED_DIR, TRUTH_DIR

from fixtures_gen.stats import compute_layer_stats


def _recompute_stats(path: Path, file_sha256: str) -> dict:
    doc = ezdxf.readfile(str(path))
    return compute_layer_stats(doc, file_sha256=file_sha256)


@pytest.mark.parametrize("fixture_id", [f for f in COMMITTED_FIXTURE_IDS if f not in ("F10",)])
def test_simple_fixture_reread_matches_truth(fixture_id: str, generated_dir, truth_dir) -> None:
    stats_path = truth_dir / f"{fixture_id}.json"
    extra_path = truth_dir / f"{fixture_id}.extra.json"
    if not stats_path.exists():
        pytest.skip(f"{stats_path} not generated yet")
    truth_stats = json.loads(stats_path.read_text(encoding="utf-8"))
    extra = json.loads(extra_path.read_text(encoding="utf-8"))

    primary_path = generated_dir / extra["primary"]["file"]
    recomputed = _recompute_stats(primary_path, truth_stats["file_sha256"])
    assert recomputed == truth_stats

    variant = extra.get("variants", {}).get("r2000_cp949")
    if variant:
        variant_path = generated_dir / variant["file"]
        recomputed_variant = _recompute_stats(variant_path, variant["stats"]["file_sha256"])
        assert recomputed_variant == variant["stats"], f"{fixture_id} r2000_cp949 variant mismatch"


def test_f10_reread_matches_truth(generated_dir, truth_dir) -> None:
    grid_stats_path = truth_dir / "F10_grid.json"
    host_stats_path = truth_dir / "F10_host.json"
    extra_path = truth_dir / "F10.extra.json"
    if not grid_stats_path.exists():
        pytest.skip(f"{grid_stats_path} not generated yet")
    extra = json.loads(extra_path.read_text(encoding="utf-8"))

    for part, stats_path in (("grid", grid_stats_path), ("host", host_stats_path)):
        truth_stats = json.loads(stats_path.read_text(encoding="utf-8"))
        primary_path = generated_dir / extra["primary"][part]["file"]
        recomputed = _recompute_stats(primary_path, truth_stats["file_sha256"])
        assert recomputed == truth_stats, f"F10 {part}"

        variant = extra["variants"]["r2000_cp949"][part]
        variant_path = generated_dir / variant["file"]
        recomputed_variant = _recompute_stats(variant_path, variant["stats"]["file_sha256"])
        assert recomputed_variant == variant["stats"], f"F10 {part} r2000_cp949 variant"


def test_f11_reread_matches_truth_if_generated() -> None:
    stats_path = TRUTH_DIR / "F11.json"
    dxf_path = GENERATED_DIR / "F11.dxf"
    if not (stats_path.exists() and dxf_path.exists()):
        pytest.skip("F11 not generated (gitignored DXF; run the generator to produce it)")
    truth_stats = json.loads(stats_path.read_text(encoding="utf-8"))
    recomputed = _recompute_stats(dxf_path, truth_stats["file_sha256"])
    assert recomputed["totals"] == truth_stats["totals"]
    assert recomputed["totals"]["count_by_type"] == truth_stats["totals"]["count_by_type"]
