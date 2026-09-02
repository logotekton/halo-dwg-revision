"""Truth JSON field-name contract (brief: "packages/schema의 stats/layer-stats.schema.json과
필드 이름을 맞춘다") and ADR-0003 height-field discipline for F08.
"""

from __future__ import annotations

import json

import pytest

REQUIRED_STATS_KEYS = {
    "count_by_type",
    "length_sum",
    "hatch_area_sum",
    "text_count",
    "text_hash",
    "insert_by_block",
    "bbox",
}

SIMPLE_IDS = [f"F{i:02d}" for i in range(1, 10)]  # F01..F09 (F10 has its own shape)


@pytest.mark.parametrize("fixture_id", SIMPLE_IDS)
def test_totals_has_required_stat_keys(fixture_id: str, truth_dir) -> None:
    path = truth_dir / f"{fixture_id}.json"
    if not path.exists():
        pytest.skip(f"{path} not generated yet")
    truth = json.loads(path.read_text(encoding="utf-8"))
    assert REQUIRED_STATS_KEYS <= truth["totals"].keys()
    assert "extra" in truth


def test_f10_totals_has_required_stat_keys(truth_dir) -> None:
    path = truth_dir / "F10.json"
    if not path.exists():
        pytest.skip(f"{path} not generated yet")
    truth = json.loads(path.read_text(encoding="utf-8"))
    for part in ("grid", "host"):
        assert REQUIRED_STATS_KEYS <= truth["totals"][part].keys()
    assert truth["extra"]["host"]["xref"]["path_kind"] == "relative"


def test_f04_gradient_omitted_only_on_r2000(truth_dir) -> None:
    path = truth_dir / "F04.json"
    if not path.exists():
        pytest.skip(f"{path} not generated yet")
    truth = json.loads(path.read_text(encoding="utf-8"))
    omitted = truth["variants"]["r2000_cp949"]["omitted"]
    assert any("GRADIENT_HATCH" in note for note in omitted)
    primary_hatch = truth["primary"]["stats"]["totals"]["count_by_type"]["HATCH"]
    variant_hatch = truth["variants"]["r2000_cp949"]["stats"]["totals"]["count_by_type"]["HATCH"]
    assert variant_hatch == primary_hatch - 1


def test_f05_multileader_omitted_only_on_r2000(truth_dir) -> None:
    path = truth_dir / "F05.json"
    if not path.exists():
        pytest.skip(f"{path} not generated yet")
    truth = json.loads(path.read_text(encoding="utf-8"))
    omitted = truth["variants"]["r2000_cp949"]["omitted"]
    assert any("MULTILEADER" in note for note in omitted)
    primary_types = truth["primary"]["stats"]["totals"]["count_by_type"]
    variant_types = truth["variants"]["r2000_cp949"]["stats"]["totals"]["count_by_type"]
    assert "MULTILEADER" in primary_types
    assert "MULTILEADER" not in variant_types


def test_f08_adr0003_inequality_and_no_forbidden_equality(truth_dir) -> None:
    """CH + slab + floor_finish < FLOOR_HEIGHT for every row (ADR-0003), and
    CH must never equal SL/FL/FLOOR_HEIGHT for any row (that would make the
    fixture useless for exercising the "CH != SL/FL/FLOOR_HEIGHT" validator).
    """
    path = truth_dir / "F08.json"
    if not path.exists():
        pytest.skip(f"{path} not generated yet")
    truth = json.loads(path.read_text(encoding="utf-8"))
    slab = truth["extra"]["slab_thickness_mm"]
    finish = truth["extra"]["floor_finish_mm"]
    levels = truth["extra"]["levels"]
    assert len(levels) == 5  # B1..4F
    for row in levels:
        assert row["CH"] + slab + finish < row["FLOOR_HEIGHT"], row
        assert row["CH"] != row["SL"]
        assert row["CH"] != row["FL"]
        assert row["CH"] != row["FLOOR_HEIGHT"]
