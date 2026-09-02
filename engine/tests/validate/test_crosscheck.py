"""``halo_engine.validate.crosscheck`` — comparison, thresholds, whitelist.

The contract under test is ``docs/contracts/stats-definition.md`` "비교 임계";
each threshold gets a just-inside and a just-outside case rather than one
convenient number, because a comparer that is silently too loose is worse
than none at all.
"""

from __future__ import annotations

from typing import Any

import pytest
from helpers import stats_document

from halo_engine.model import CrosscheckReport, DiffField, Severity
from halo_engine.validate.crosscheck import (
    BBOX_TOLERANCE_MM,
    DEFAULT_WHITELIST,
    WhitelistError,
    compare,
    load_whitelist,
    render_markdown,
)

EZDXF = "engine.ezdxf"
MLIGHTCAD = "viewer.mlightcad"
ACAD = "acad-ts"


def one_bucket(producer: str, aggregate: dict[str, Any]) -> dict[str, Any]:
    return stats_document(producer=producer, buckets=[("MODEL", "A-WALL", aggregate)])


def test_identical_documents_are_green() -> None:
    aggregate = {"count_by_type": {"LINE": 3}, "length_sum_mm": 1000.0}
    report = compare(one_bucket(EZDXF, aggregate), one_bucket(MLIGHTCAD, aggregate))
    assert report.status is Severity.GREEN
    assert report.red_layers == []
    assert report.counts == {"GREEN": 1, "AMBER": 0, "RED": 0}
    assert report.totals.status is Severity.GREEN


def test_count_difference_is_red_with_the_briefs_detail_wording() -> None:
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"LINE": 24}}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 22}}),
    )
    assert report.status is Severity.RED
    assert report.red_layers == ["A-WALL"]
    details = [d.detail for d in report.layers[0].differences]
    assert "count_by_type.LINE 24→22" in details


def test_bucket_missing_on_one_side_is_red() -> None:
    reference = stats_document(
        producer=EZDXF,
        buckets=[("MODEL", "A-WALL", {"count_by_type": {"LINE": 1}})],
    )
    other = stats_document(
        producer=MLIGHTCAD,
        buckets=[("MODEL", "A-DOOR", {"count_by_type": {"LINE": 1}})],
    )
    report = compare(reference, other)
    assert report.status is Severity.RED
    assert sorted(report.red_layers) == ["A-DOOR", "A-WALL"]
    assert {d.field for layer in report.layers for d in layer.differences} == {DiffField.BUCKET}


@pytest.mark.parametrize(
    ("other_length", "expected"),
    [
        (1000.0, Severity.GREEN),  # identical
        (1000.9, Severity.GREEN),  # 0.09 % — inside ±0.1 %
        (1002.0, Severity.RED),  # 0.2 % — outside
    ],
)
def test_length_tolerance_is_one_tenth_percent(other_length: float, expected: Severity) -> None:
    report = compare(
        one_bucket(EZDXF, {"length_sum_mm": 1000.0}),
        one_bucket(MLIGHTCAD, {"length_sum_mm": other_length}),
    )
    assert report.layers[0].status is expected


@pytest.mark.parametrize(
    ("other_area", "expected"),
    [
        (10_000.0, Severity.GREEN),
        (10_040.0, Severity.GREEN),  # 0.4 % — inside ±0.5 %
        (10_100.0, Severity.RED),  # 1 % — outside
    ],
)
def test_hatch_area_tolerance_is_half_a_percent(other_area: float, expected: Severity) -> None:
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"HATCH": 1}, "hatch_area_sum_mm2": 10_000.0}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"HATCH": 1}, "hatch_area_sum_mm2": other_area}),
    )
    assert report.layers[0].status is expected


@pytest.mark.parametrize(
    ("shift", "expected"),
    [(0.0, Severity.GREEN), (0.9, Severity.GREEN), (1.5, Severity.RED)],
)
def test_bbox_tolerance_is_one_millimetre(shift: float, expected: Severity) -> None:
    box = {"min": [0.0, 0.0], "max": [100.0, 50.0]}
    shifted = {"min": [0.0, 0.0], "max": [100.0 + shift, 50.0]}
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"LINE": 1}, "bbox": box}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 1}, "bbox": shifted}),
    )
    assert report.layers[0].status is expected
    assert BBOX_TOLERANCE_MM == 1.0


def test_bbox_present_on_one_side_only_is_a_difference() -> None:
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"LINE": 1}, "bbox": {"min": [0, 0], "max": [1, 1]}}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 1}}),
    )
    assert report.status is Severity.RED
    assert report.layers[0].differences[0].field is DiffField.BBOX


def test_text_count_and_hash_are_exact() -> None:
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"TEXT": 2}, "text_count": 2, "text_hash": "aaaa"}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"TEXT": 2}, "text_count": 2, "text_hash": "bbbb"}),
    )
    fields = {d.field for d in report.layers[0].differences}
    assert fields == {DiffField.TEXT_HASH}
    assert report.status is Severity.RED


def test_insert_by_block_difference_is_reported_per_block_name() -> None:
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"INSERT": 1}, "insert_by_block": {"X-TITLE": 1}}),
        one_bucket(
            MLIGHTCAD, {"count_by_type": {"INSERT": 1}, "insert_by_block": {"<unresolved>": 1}}
        ),
    )
    details = sorted(d.detail for d in report.layers[0].differences)
    assert details == ["insert_by_block.<unresolved> 0→1", "insert_by_block.X-TITLE 1→0"]


# --------------------------------------------------------------------------- whitelist


def write_whitelist(tmp_path: Any, body: str) -> Any:
    path = tmp_path / "wl.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_whitelist_downgrades_red_to_amber_and_quotes_the_reason(tmp_path: Any) -> None:
    path = write_whitelist(
        tmp_path,
        """
entries:
  - id: WTEST
    producer_pair: [engine.ezdxf, viewer.mlightcad]
    field: length_sum_mm
    entity_type: [SPLINE]
    reason: mlightcad flattens splines more coarsely than the contract asks.
""",
    )
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"SPLINE": 1}, "length_sum_mm": 1000.0}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"SPLINE": 1}, "length_sum_mm": 1100.0}),
        whitelist=load_whitelist(path),
        whitelist_path=str(path),
    )
    assert report.status is Severity.AMBER
    assert report.red_layers == []
    assert report.amber_layers == ["A-WALL"]
    difference = report.layers[0].differences[0]
    assert difference.severity is Severity.AMBER
    assert difference.whitelist_id == "WTEST"
    assert "coarsely" in (difference.whitelist_reason or "")
    assert "WTEST" in render_markdown(report)
    assert "coarsely" in render_markdown(report)


def test_whitelist_entry_only_applies_to_its_producer_pair(tmp_path: Any) -> None:
    path = write_whitelist(
        tmp_path,
        """
entries:
  - producer_pair: [engine.ezdxf, acad-ts]
    field: length_sum_mm
    reason: acad-ts flattening precision.
""",
    )
    entries = load_whitelist(path)
    report = compare(
        one_bucket(EZDXF, {"length_sum_mm": 1000.0}),
        one_bucket(MLIGHTCAD, {"length_sum_mm": 1100.0}),
        whitelist=entries,
    )
    assert report.status is Severity.RED


def test_whitelist_wildcard_matches_any_pair_containing_the_named_producer(tmp_path: Any) -> None:
    path = write_whitelist(
        tmp_path,
        """
entries:
  - producer_pair: ["*", acad-ts]
    field: length_sum_mm
    reason: acad-ts flattening precision.
""",
    )
    entries = load_whitelist(path)
    for other in (EZDXF, MLIGHTCAD):
        report = compare(
            one_bucket(ACAD, {"length_sum_mm": 1000.0}),
            one_bucket(other, {"length_sum_mm": 1100.0}),
            whitelist=entries,
        )
        assert report.status is Severity.AMBER


def test_whitelist_entity_type_filter_scopes_the_downgrade(tmp_path: Any) -> None:
    path = write_whitelist(
        tmp_path,
        """
entries:
  - producer_pair: [engine.ezdxf, viewer.mlightcad]
    field: length_sum_mm
    entity_type: SPLINE
    reason: spline flattening.
""",
    )
    entries = load_whitelist(path)
    arc = compare(
        one_bucket(EZDXF, {"count_by_type": {"ARC": 1}, "length_sum_mm": 1000.0}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"ARC": 1}, "length_sum_mm": 1100.0}),
        whitelist=entries,
    )
    assert arc.status is Severity.RED, "an ARC length gap is not the whitelisted spline gap"


def test_attrib_is_inferred_as_a_bucket_entity_type(tmp_path: Any) -> None:
    """A bucket holding only ATTRIBs has an empty ``count_by_type`` by contract."""
    path = write_whitelist(
        tmp_path,
        """
entries:
  - producer_pair: [engine.ezdxf, viewer.mlightcad]
    field: bbox
    entity_type: [ATTRIB]
    reason: font-derived extents.
""",
    )
    report = compare(
        one_bucket(
            EZDXF,
            {"text_count": 2, "text_hash": "aaaa", "bbox": {"min": [0, 0], "max": [100, 10]}},
        ),
        one_bucket(
            MLIGHTCAD,
            {"text_count": 2, "text_hash": "aaaa", "bbox": {"min": [0, 0], "max": [180, 10]}},
        ),
        whitelist=load_whitelist(path),
    )
    assert report.status is Severity.AMBER


def test_count_gaps_can_never_be_whitelisted(tmp_path: Any) -> None:
    """Even a `producer_pair`-only entry that matches everything leaves counts RED."""
    path = write_whitelist(
        tmp_path,
        """
entries:
  - producer_pair: ["*", "*"]
    entity_type: [LINE]
    reason: deliberately over-broad entry, used to prove counts stay RED.
""",
    )
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"LINE": 24}}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 22}}),
        whitelist=load_whitelist(path),
    )
    assert report.status is Severity.RED
    assert report.red_layers == ["A-WALL"]


@pytest.mark.parametrize("field", ["count_by_type", "text_count", "bucket"])
def test_whitelisting_a_count_field_is_a_load_error(tmp_path: Any, field: str) -> None:
    path = write_whitelist(
        tmp_path,
        f"""
entries:
  - producer_pair: [engine.ezdxf, acad-ts]
    field: {field}
    reason: not allowed.
""",
    )
    with pytest.raises(WhitelistError, match="count measure"):
        load_whitelist(path)


def test_insert_by_block_is_whitelistable_only_when_the_insert_total_is_unchanged(
    tmp_path: Any,
) -> None:
    path = write_whitelist(
        tmp_path,
        """
entries:
  - producer_pair: ["*", acad-ts]
    field: insert_by_block
    reason: acad-ts leaves a block reference unresolved when a layer shares its name.
""",
    )
    entries = load_whitelist(path)

    renamed = compare(
        one_bucket(EZDXF, {"count_by_type": {"INSERT": 1}, "insert_by_block": {"X-TITLE": 1}}),
        one_bucket(ACAD, {"count_by_type": {"INSERT": 1}, "insert_by_block": {"<unresolved>": 1}}),
        whitelist=entries,
    )
    assert renamed.status is Severity.AMBER, "same INSERT total, only the block name is unresolved"

    dropped = compare(
        one_bucket(EZDXF, {"count_by_type": {"INSERT": 2}, "insert_by_block": {"X-TITLE": 2}}),
        one_bucket(ACAD, {"count_by_type": {"INSERT": 2}, "insert_by_block": {"X-TITLE": 1}}),
        whitelist=entries,
    )
    assert dropped.status is Severity.RED, "one INSERT went missing -- that is a count gap"


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("entries:\n  - producer_pair: [a, b]\n    field: bbox\n", "reason"),
        ("entries:\n  - producer_pair: [a, b]\n    field: bbox\n    reason: '  '\n", "reason"),
        ("entries:\n  - producer_pair: [a]\n    field: bbox\n    reason: x\n", "producer_pair"),
        ("entries:\n  - producer_pair: [a, b]\n    reason: x\n", "at least one"),
        ("entries:\n  - producer_pair: [a, b]\n    field: nope\n    reason: x\n", "unknown field"),
        ("entries:\n  - producer_pair: [a, b]\n    bogus: 1\n    reason: x\n", "unknown keys"),
        ("entries: {}\n", "must be a list"),
        ("- a\n- b\n", "top level"),
    ],
)
def test_malformed_whitelist_entries_fail_to_load(tmp_path: Any, body: str, match: str) -> None:
    with pytest.raises(WhitelistError, match=match):
        load_whitelist(write_whitelist(tmp_path, body))


def test_no_whitelist_means_no_downgrades() -> None:
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"SPLINE": 1}, "length_sum_mm": 1000.0}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"SPLINE": 1}, "length_sum_mm": 1100.0}),
        whitelist=load_whitelist(None),
    )
    assert report.status is Severity.RED


# --------------------------------------------------------------------- shipped whitelist


def test_shipped_whitelist_loads_and_every_entry_has_a_reason() -> None:
    entries = load_whitelist(DEFAULT_WHITELIST)
    assert entries, "the shipped whitelist should not be empty"
    assert all(entry.reason.strip() for entry in entries)
    assert len({entry.entry_id for entry in entries}) == len(entries), "entry ids must be unique"
    known = {"engine.ezdxf", "viewer.mlightcad", "acad-ts", "libredwg-web", "*"}
    for entry in entries:
        assert entry.producers <= known, f"{entry.entry_id} names an unknown producer"


# ------------------------------------------------------------------------ sha / report


def test_sha_mismatch_warns_but_still_compares() -> None:
    reference = one_bucket(EZDXF, {"count_by_type": {"LINE": 1}})
    other = one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 1}})
    other["file_sha256"] = "b" * 64
    report = compare(reference, other)
    assert report.file_sha256_mismatch is True
    assert report.file_sha256 is None
    assert report.warnings and "file_sha256" in report.warnings[0]
    assert report.status is Severity.GREEN, "a sha mismatch is never fatal on its own"


def test_report_round_trips_through_json() -> None:
    report = compare(
        one_bucket(EZDXF, {"count_by_type": {"LINE": 2}}),
        one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 1}}),
    )
    restored = CrosscheckReport.model_validate(report.model_dump(mode="json"))
    assert restored == report


def test_markdown_has_korean_headers_and_one_row_per_layer() -> None:
    report = compare(
        stats_document(
            producer=EZDXF,
            buckets=[
                ("MODEL", "A-WALL", {"count_by_type": {"LINE": 2}}),
                ("MODEL", "A-DOOR", {"count_by_type": {"INSERT": 1}}),
            ],
        ),
        stats_document(
            producer=MLIGHTCAD,
            buckets=[
                ("MODEL", "A-WALL", {"count_by_type": {"LINE": 1}}),
                ("MODEL", "A-DOOR", {"count_by_type": {"INSERT": 1}}),
            ],
        ),
    )
    markdown = render_markdown(report)
    assert "| 레이어 | 공간 | 상태 | 원인 |" in markdown
    assert markdown.count("| MODEL |") == 2, "one row per layer"
    assert "| (totals) | (all) |" in markdown
    assert "RED" in markdown
    assert "count_by_type.LINE 2→1" in markdown


def test_markdown_escapes_a_pipe_in_a_layer_name() -> None:
    report = compare(
        stats_document(producer=EZDXF, buckets=[("MODEL", "A|B", {"count_by_type": {"LINE": 2}})]),
        stats_document(
            producer=MLIGHTCAD, buckets=[("MODEL", "A|B", {"count_by_type": {"LINE": 1}})]
        ),
    )
    assert "| A\\|B |" in render_markdown(report)
