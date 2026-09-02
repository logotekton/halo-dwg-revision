"""Independent verification: re-reading each committed DXF with ezdxf and
recomputing statistics (fixtures_gen.stats.compute_stats) must reproduce
exactly what's committed in fixtures/truth/F*.json (ADR-0002 Section 6).
"""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf
import pytest
from conftest import COMMITTED_FIXTURE_IDS, GENERATED_DIR, TRUTH_DIR

from fixtures_gen.stats import compute_stats

STATS_KEYS = [
    "count_by_type",
    "length_sum",
    "hatch_area_sum",
    "text_count",
    "text_hash",
    "insert_by_block",
    "bbox",
]


def _recompute(path: Path) -> dict:
    doc = ezdxf.readfile(str(path))
    return compute_stats(doc)


def _assert_totals_match(recomputed_totals: dict, truth_totals: dict, label: str) -> None:
    for key in STATS_KEYS:
        assert recomputed_totals[key] == truth_totals[key], f"{label}: totals.{key} mismatch"


@pytest.mark.parametrize("fixture_id", [f for f in COMMITTED_FIXTURE_IDS if f != "F10"])
def test_simple_fixture_reread_matches_truth(fixture_id: str, generated_dir, truth_dir) -> None:
    truth_path = truth_dir / f"{fixture_id}.json"
    if not truth_path.exists():
        pytest.skip(f"{truth_path} not generated yet")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))

    primary_path = generated_dir / truth["primary"]["file"]
    recomputed = _recompute(primary_path)
    _assert_totals_match(recomputed["totals"], truth["totals"], f"{fixture_id} primary")
    assert recomputed["totals"] == truth["primary"]["stats"]["totals"]

    variant = truth.get("variants", {}).get("r2000_cp949")
    if variant:
        variant_path = generated_dir / variant["file"]
        recomputed_variant = _recompute(variant_path)
        assert recomputed_variant["totals"] == variant["stats"]["totals"], (
            f"{fixture_id} r2000_cp949 variant totals mismatch"
        )


def test_f10_reread_matches_truth(generated_dir, truth_dir) -> None:
    truth_path = truth_dir / "F10.json"
    if not truth_path.exists():
        pytest.skip(f"{truth_path} not generated yet")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))

    for part in ("grid", "host"):
        primary_path = generated_dir / truth["primary"][part]["file"]
        recomputed = _recompute(primary_path)
        _assert_totals_match(recomputed["totals"], truth["totals"][part], f"F10 {part}")

        variant_path = generated_dir / truth["variants"]["r2000_cp949"][part]["file"]
        recomputed_variant = _recompute(variant_path)
        assert (
            recomputed_variant["totals"]
            == truth["variants"]["r2000_cp949"][part]["stats"]["totals"]
        )


def test_f11_reread_matches_truth_if_generated() -> None:
    truth_path = TRUTH_DIR / "F11.json"
    dxf_path = GENERATED_DIR / "F11.dxf"
    if not (truth_path.exists() and dxf_path.exists()):
        pytest.skip("F11 not generated (gitignored DXF; run the generator to produce it)")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    recomputed = _recompute(dxf_path)
    _assert_totals_match(recomputed["totals"], truth["totals"], "F11")
    assert recomputed["totals"]["count_by_type"] == truth["totals"]["count_by_type"]
