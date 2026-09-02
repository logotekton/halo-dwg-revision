"""Truth JSON shape (brief W2-03: F##.json is a bare LayerStatsDocument,
F##.extra.json holds everything else) and ADR-0003 height-field discipline
for F08.

Full JSON Schema validation against ``packages/schema/src/stats/layer-stats.schema.json``
lives in ``engine/tests/ingest/test_truth_schema.py`` (jsonschema +
referencing is an engine-only dependency; fixtures/gen depends on ezdxf
alone, per fixtures/README.md).
"""

from __future__ import annotations

import json

import pytest

REQUIRED_STATS_DOC_KEYS = {"schema_version", "file_sha256", "producer", "buckets", "totals"}
REQUIRED_AGGREGATE_KEYS = {
    "entity_count",
    "count_by_type",
    "length_sum_mm",
    "hatch_area_sum_mm2",
    "text_count",
    "text_hash",
    "insert_by_block",
}

SIMPLE_IDS = [f"F{i:02d}" for i in range(1, 10)]  # F01..F09 (F10 is a file pair)


@pytest.mark.parametrize("fixture_id", SIMPLE_IDS)
def test_stats_doc_has_required_keys(fixture_id: str, truth_dir) -> None:
    stats_path = truth_dir / f"{fixture_id}.json"
    extra_path = truth_dir / f"{fixture_id}.extra.json"
    if not stats_path.exists():
        pytest.skip(f"{stats_path} not generated yet")
    stats = json.loads(stats_path.read_text(encoding="utf-8"))
    assert stats.keys() == REQUIRED_STATS_DOC_KEYS
    assert REQUIRED_AGGREGATE_KEYS <= stats["totals"].keys()
    assert extra_path.exists(), f"{extra_path} missing"
    extra = json.loads(extra_path.read_text(encoding="utf-8"))
    assert "extra" in extra
    assert "primary" in extra


def test_f10_stats_docs_have_required_keys(truth_dir) -> None:
    for part in ("grid", "host"):
        path = truth_dir / f"F10_{part}.json"
        if not path.exists():
            pytest.skip(f"{path} not generated yet")
        stats = json.loads(path.read_text(encoding="utf-8"))
        assert stats.keys() == REQUIRED_STATS_DOC_KEYS
        assert REQUIRED_AGGREGATE_KEYS <= stats["totals"].keys()
    extra = json.loads((truth_dir / "F10.extra.json").read_text(encoding="utf-8"))
    assert extra["extra"]["host"]["xref"]["path_kind"] == "relative"


def test_f04_gradient_omitted_only_on_r2000(truth_dir) -> None:
    stats_path = truth_dir / "F04.json"
    extra_path = truth_dir / "F04.extra.json"
    if not stats_path.exists():
        pytest.skip(f"{stats_path} not generated yet")
    primary_stats = json.loads(stats_path.read_text(encoding="utf-8"))
    extra = json.loads(extra_path.read_text(encoding="utf-8"))
    variant = extra["variants"]["r2000_cp949"]
    assert any("GRADIENT_HATCH" in note for note in variant["omitted"])
    primary_hatch = primary_stats["totals"]["count_by_type"]["HATCH"]
    variant_hatch = variant["stats"]["totals"]["count_by_type"]["HATCH"]
    assert variant_hatch == primary_hatch - 1


def test_f05_multileader_omitted_only_on_r2000(truth_dir) -> None:
    stats_path = truth_dir / "F05.json"
    extra_path = truth_dir / "F05.extra.json"
    if not stats_path.exists():
        pytest.skip(f"{stats_path} not generated yet")
    primary_stats = json.loads(stats_path.read_text(encoding="utf-8"))
    extra = json.loads(extra_path.read_text(encoding="utf-8"))
    variant = extra["variants"]["r2000_cp949"]
    assert any("MULTILEADER" in note for note in variant["omitted"])
    primary_types = primary_stats["totals"]["count_by_type"]
    variant_types = variant["stats"]["totals"]["count_by_type"]
    assert "MULTILEADER" in primary_types
    assert "MULTILEADER" not in variant_types


def test_f08_adr0003_inequality_and_no_forbidden_equality(truth_dir) -> None:
    """CH + slab + floor_finish < FLOOR_HEIGHT for every row (ADR-0003), and
    CH must never equal SL/FL/FLOOR_HEIGHT for any row (that would make the
    fixture useless for exercising the "CH != SL/FL/FLOOR_HEIGHT" validator).
    """
    extra_path = truth_dir / "F08.extra.json"
    if not extra_path.exists():
        pytest.skip(f"{extra_path} not generated yet")
    extra = json.loads(extra_path.read_text(encoding="utf-8"))["extra"]
    slab = extra["slab_thickness_mm"]
    finish = extra["floor_finish_mm"]
    levels = extra["levels"]
    assert len(levels) == 5  # B1..4F
    for row in levels:
        assert row["CH"] + slab + finish < row["FLOOR_HEIGHT"], row
        assert row["CH"] != row["SL"]
        assert row["CH"] != row["FL"]
        assert row["CH"] != row["FLOOR_HEIGHT"]
