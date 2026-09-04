"""``compare/match.py``: the four pairing stages and what they refuse to guess
(brief R1-04, contract §6, §3 for the statuses).

Frames are built by hand here rather than extracted from a drawing. Matching
reads eight fields off a :class:`~halo_engine.compare.frames.FrameRecord` and
nothing else, so a real DXF would only make it harder to see which field a case
is actually about.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from halo_engine.compare.config import (
    DEFAULT_COMPARE_YAML,
    DEFAULT_FRAMES_YAML,
    CompareConfig,
    FramesConfig,
)
from halo_engine.compare.frames import KIND_TITLEBLOCK, KIND_UNRECOGNIZED, FrameRecord
from halo_engine.compare.match import (
    METHOD_NUMBER,
    METHOD_POSITION,
    METHOD_TITLE,
    STATUS_ADDED,
    STATUS_CONVERTER_MISMATCH,
    STATUS_PENDING,
    STATUS_REMOVED,
    STATUS_SAME,
    STATUS_UNPAIRED,
    STATUS_UNRECOGNIZED,
    PairRecord,
    manual_pair,
    match_frames,
    match_frames_with_stats,
    natural_sort_key,
    pair_rows,
)

SHEET_W = 84100.0
SHEET_H = 59400.0


def compare_config(**match: Any) -> CompareConfig:
    data = yaml.safe_load(DEFAULT_COMPARE_YAML.read_text("utf-8"))
    data["match"].update(match)
    return CompareConfig.model_validate(data)


def frames_config() -> FramesConfig:
    return FramesConfig.model_validate(yaml.safe_load(DEFAULT_FRAMES_YAML.read_text("utf-8")))


def frame(
    *,
    role: str,
    sheet_no: str | None = None,
    sheet_title: str | None = None,
    file_name: str = "plan.dxf",
    file_id: str = "F",
    sha: str = "",
    converter: str | None = None,
    sort_index: int = 0,
    width: float = SHEET_W,
    height: float = SHEET_H,
    kind: str = KIND_TITLEBLOCK,
    norm_key: str | None = None,
) -> FrameRecord:
    return FrameRecord(
        file_id=file_id,
        kind=kind,
        titleblock_handle="A1",
        block_name="TITLEBLOCK",
        bbox=[0.0, 0.0, width, height],
        sheet_no=sheet_no,
        sheet_title=sheet_title,
        norm_key=norm_key if norm_key is not None else (sheet_no or "").upper(),
        sort_index=sort_index,
        role=role,
        file_name=file_name,
        file_sha256=sha,
        converter=converter,
    )


def summary(pairs: list[PairRecord]) -> list[tuple[int | None, int | None, str, str | None]]:
    return [(p.before_index, p.after_index, p.status, p.match_method) for p in pairs]


def run(before: list[FrameRecord], after: list[FrameRecord], **match: Any) -> list[PairRecord]:
    return match_frames(before, after, compare_config(**match), frames_config())


# --------------------------------------------------------------------------- stage 1


def test_stage_1_pairs_equal_drawing_numbers() -> None:
    before = [frame(role="before", sheet_no="A-101"), frame(role="before", sheet_no="A-102")]
    after = [frame(role="after", sheet_no="A-102"), frame(role="after", sheet_no="A-101")]
    pairs = run(before, after)
    assert summary(pairs) == [
        (0, 1, STATUS_PENDING, METHOD_NUMBER),
        (1, 0, STATUS_PENDING, METHOD_NUMBER),
    ]
    assert all(p.score == 1.0 for p in pairs)


def test_stage_1_normalisation_is_the_matchers_own() -> None:
    """`A-101`, `ａ－１０１` and `a 101` are one drawing number."""
    before = [frame(role="before", sheet_no="A-101", norm_key="A-101")]
    after = [frame(role="after", sheet_no="ａ－１０１", norm_key="A-101")]
    assert summary(run(before, after)) == [(0, 0, STATUS_PENDING, METHOD_NUMBER)]


def test_a_number_repeated_on_both_sides_is_left_to_the_user() -> None:
    before = [
        frame(role="before", sheet_no="A-101", sort_index=0),
        frame(role="before", sheet_no="A-101", sort_index=1),
    ]
    after = [frame(role="after", sheet_no="A-101", file_name="other.dxf")]
    pairs, stats = match_frames_with_stats(before, after, compare_config(), frames_config())
    assert {p.status for p in pairs} == {STATUS_UNPAIRED}
    assert len(pairs) == 3
    assert stats.duplicate_sheet_no == 2


def test_a_number_repeated_on_one_side_only_is_still_removed() -> None:
    """No candidate at all is a removal, not an ambiguity."""
    before = [
        frame(role="before", sheet_no="A-101", sort_index=0),
        frame(role="before", sheet_no="A-101", sort_index=1),
    ]
    pairs = run(before, [])
    assert {p.status for p in pairs} == {STATUS_REMOVED}


# --------------------------------------------------------------------------- stage 2


def test_stage_2_pairs_by_title_when_the_number_could_not_be_read() -> None:
    """The case `title_jaccard_min` is documented for: no drawing number."""
    before = [frame(role="before", sheet_title="지하1층 주차장 평면도", file_name="b.dxf")]
    after = [frame(role="after", sheet_title="지하1층 주차장 평면도 (수정)", file_name="a.dxf")]
    pairs = run(before, after)
    assert summary(pairs) == [(0, 0, STATUS_PENDING, METHOD_TITLE)]
    assert pairs[0].score is not None and 0.6 <= pairs[0].score < 1.0


def test_two_different_numbers_are_never_paired_by_their_titles() -> None:
    """Sheets in one set share their names; the numbers are the evidence.

    R1-07's S14 is exactly this: A-101 leaves the set and A-103 joins it, both
    called 1층 평면도. Pairing them would hand R1-06 two unrelated drawings.
    """
    before = [frame(role="before", sheet_no="A-101", sheet_title="1층 평면도", file_name="b.dxf")]
    after = [frame(role="after", sheet_no="A-103", sheet_title="1층 평면도", file_name="a.dxf")]
    assert {p.status for p in run(before, after)} == {STATUS_REMOVED, STATUS_ADDED}


def test_stage_2_refuses_a_tie() -> None:
    """Two after sheets equally close: the user decides, not the matcher.

    Different file names on the two sides, so stage 3 cannot step in and
    rescue the pairing by position -- this case is about stage 2 alone.
    """
    before = [frame(role="before", sheet_title="1층 평면도", file_name="b.dxf")]
    after = [
        frame(role="after", sheet_title="1층 평면도", file_name="a.dxf"),
        frame(role="after", sheet_title="평면도 1층", file_name="a.dxf", sort_index=1),
    ]
    pairs = run(before, after, title_jaccard_min=0.6)
    assert {p.status for p in pairs} == {STATUS_UNPAIRED}


def test_stage_2_obeys_the_threshold() -> None:
    before = [frame(role="before", sheet_title="1층 평면도", file_name="b.dxf")]
    after = [frame(role="after", sheet_title="2층 천장도", file_name="a.dxf")]
    pairs = run(before, after)
    assert summary(pairs) == [
        (None, 0, STATUS_ADDED, None),
        (0, None, STATUS_REMOVED, None),
    ] or summary(pairs) == [
        (0, None, STATUS_REMOVED, None),
        (None, 0, STATUS_ADDED, None),
    ]


# --------------------------------------------------------------------------- stage 3


def test_stage_3_pairs_by_position_inside_the_same_file() -> None:
    before = [frame(role="before", sort_index=2, file_name="plan.dxf")]
    after = [frame(role="after", sort_index=2, file_name="PLAN.DXF")]
    pairs = run(before, after)
    assert summary(pairs) == [(0, 0, STATUS_PENDING, METHOD_POSITION)]
    assert pairs[0].score == 0.5


def test_stage_3_rejects_a_frame_of_a_different_size() -> None:
    before = [frame(role="before", sort_index=0, width=SHEET_W)]
    after = [frame(role="after", sort_index=0, width=SHEET_W * 1.05)]
    assert {p.status for p in run(before, after)} == {STATUS_REMOVED, STATUS_ADDED}


def test_stage_3_accepts_a_frame_within_one_percent() -> None:
    before = [frame(role="before", sort_index=0, width=SHEET_W)]
    after = [frame(role="after", sort_index=0, width=SHEET_W * 1.005)]
    assert summary(run(before, after)) == [(0, 0, STATUS_PENDING, METHOD_POSITION)]


def test_stage_3_does_not_cross_files() -> None:
    before = [frame(role="before", sort_index=0, file_name="a.dxf")]
    after = [frame(role="after", sort_index=0, file_name="b.dxf")]
    assert {p.status for p in run(before, after)} == {STATUS_REMOVED, STATUS_ADDED}


# --------------------------------------------------------------------------- stage 4


def test_stage_4_reports_added_and_removed_sheets() -> None:
    before = [
        frame(role="before", sheet_no="A-101", file_name="a.dxf"),
        frame(role="before", sheet_no="A-102", file_name="a.dxf", sort_index=1),
    ]
    after = [
        frame(role="after", sheet_no="A-102", file_name="b.dxf"),
        frame(role="after", sheet_no="A-103", file_name="b.dxf", sort_index=1),
    ]
    pairs = run(before, after)
    by_status = {p.status: p for p in pairs}
    assert set(by_status) == {STATUS_PENDING, STATUS_REMOVED, STATUS_ADDED}
    assert by_status[STATUS_REMOVED].before_index == 0
    assert by_status[STATUS_ADDED].after_index == 1


# --------------------------------------------------------------------------- statuses


def test_identical_files_are_same_before_any_comparison() -> None:
    before = [frame(role="before", sheet_no="A-101", sha="deadbeef")]
    after = [frame(role="after", sheet_no="A-101", sha="deadbeef")]
    assert run(before, after)[0].status == STATUS_SAME


def test_different_bytes_stay_pending() -> None:
    before = [frame(role="before", sheet_no="A-101", sha="aaaa")]
    after = [frame(role="after", sheet_no="A-101", sha="bbbb")]
    assert run(before, after)[0].status == STATUS_PENDING


def test_two_converters_mean_the_sheet_must_not_be_compared() -> None:
    before = [frame(role="before", sheet_no="A-101", converter="zwcad-com")]
    after = [frame(role="after", sheet_no="A-101", converter="acad-ts")]
    pair = run(before, after)[0]
    assert pair.status == STATUS_CONVERTER_MISMATCH
    assert pair.match_method == METHOD_NUMBER
    assert any(w.startswith("converter:") for w in pair.warnings)


def test_one_side_without_a_converter_is_not_a_mismatch() -> None:
    """A DXF input never ran a converter; that is not a disagreement."""
    before = [frame(role="before", sheet_no="A-101", converter=None)]
    after = [frame(role="after", sheet_no="A-101", converter="zwcad-com")]
    assert run(before, after)[0].status == STATUS_PENDING


def test_a_frame_size_difference_is_warned_about_not_refused() -> None:
    before = [frame(role="before", sheet_no="A-101", width=SHEET_W)]
    after = [frame(role="after", sheet_no="A-101", width=SHEET_W / 2)]
    pair = run(before, after)[0]
    assert pair.status == STATUS_PENDING
    assert "frame_size_differs" in pair.warnings


# --------------------------------------------------------------------------- unrecognised


def test_unrecognised_files_pair_by_file_name() -> None:
    before = [frame(role="before", kind=KIND_UNRECOGNIZED, norm_key="file:DETAIL.DXF")]
    after = [
        frame(role="after", kind=KIND_UNRECOGNIZED, norm_key="file:DETAIL.DXF"),
        frame(role="after", kind=KIND_UNRECOGNIZED, norm_key="file:SKETCH.DXF"),
    ]
    pairs = run(before, after)
    assert summary(pairs) == [
        (0, 0, STATUS_UNRECOGNIZED, None),
        (None, 1, STATUS_UNRECOGNIZED, None),
    ]


def test_an_unrecognised_file_never_pairs_with_a_sheet() -> None:
    before = [frame(role="before", sheet_no="A-101")]
    after = [frame(role="after", kind=KIND_UNRECOGNIZED, norm_key="file:A-101.DXF")]
    statuses = {p.status for p in run(before, after)}
    assert statuses == {STATUS_REMOVED, STATUS_UNRECOGNIZED}


# --------------------------------------------------------------------------- manual


def test_manual_pair_keeps_the_status_rules_but_drops_the_score() -> None:
    before = frame(role="before", sheet_no="OLD", sha="x")
    after = frame(role="after", sheet_no="NEW", sha="x")
    pair = manual_pair(0, 0, before, after)
    assert pair.match_method == "manual"
    assert pair.score is None
    assert pair.status == STATUS_SAME


# --------------------------------------------------------------------------- ordering


def test_natural_sort_key_orders_numbers_as_numbers() -> None:
    keys = sorted(natural_sort_key(value) for value in ("A-101", "A-99", "A-1000", "B-1"))
    assert keys == [
        natural_sort_key("A-99"),
        natural_sort_key("A-101"),
        natural_sort_key("A-1000"),
        natural_sort_key("B-1"),
    ]


def test_pairs_come_back_in_sheet_number_order() -> None:
    before = [
        frame(role="before", sheet_no="A-1000", sort_index=0),
        frame(role="before", sheet_no="A-99", sort_index=1),
        frame(role="before", sheet_no="A-101", sort_index=2),
    ]
    after = [
        frame(role="after", sheet_no="A-101", sort_index=0),
        frame(role="after", sheet_no="A-1000", sort_index=1),
        frame(role="after", sheet_no="A-99", sort_index=2),
    ]
    pairs = run(before, after)
    numbers = [after[p.after_index].sheet_no for p in pairs if p.after_index is not None]
    assert numbers == ["A-99", "A-101", "A-1000"]


def test_sort_key_falls_back_to_title_then_to_file_and_position() -> None:
    before = [
        frame(role="before", sheet_title="평면도", sort_index=0, file_name="a.dxf"),
        frame(role="before", sort_index=1, file_name="a.dxf"),
    ]
    pairs = run(before, [])
    assert pairs[0].sort_key
    assert pairs[1].sort_key
    assert pairs[0].sort_key != pairs[1].sort_key


def test_matching_is_deterministic() -> None:
    before = [frame(role="before", sheet_no=f"A-{100 + i}", sort_index=i) for i in range(8)]
    after = [frame(role="after", sheet_no=f"A-{102 + i}", sort_index=i) for i in range(8)]
    first = summary(run(before, after))
    second = summary(run(before, after))
    assert first == second


# --------------------------------------------------------------------------- rows


def test_pair_rows_map_indices_to_row_ids() -> None:
    before = [frame(role="before", sheet_no="A-101")]
    after = [frame(role="after", sheet_no="A-101")]
    pairs = run(before, after)
    rows = pair_rows(pairs, ["B0"], ["A0"])
    assert rows == [
        {
            "before_frame_id": "B0",
            "after_frame_id": "A0",
            "status": STATUS_PENDING,
            "match_method": METHOD_NUMBER,
            "score": 1.0,
            "sort_key": natural_sort_key("A-101"),
            "warnings": None,
        }
    ]


def test_pair_rows_leave_a_missing_side_null() -> None:
    pairs = run([frame(role="before", sheet_no="A-101")], [])
    rows = pair_rows(pairs, ["B0"], [])
    assert rows[0]["after_frame_id"] is None
    assert rows[0]["status"] == STATUS_REMOVED


def test_match_frames_works_without_an_explicit_frames_config() -> None:
    """The contract's three-argument call (contract §6) still resolves."""
    before = [frame(role="before", sheet_no="A-101")]
    after = [frame(role="after", sheet_no="A-101")]
    pairs = match_frames(before, after, compare_config())
    assert summary(pairs) == [(0, 0, STATUS_PENDING, METHOD_NUMBER)]


def test_empty_sets_produce_no_pairs() -> None:
    assert match_frames([], [], compare_config()) == []


@pytest.mark.parametrize("side", ["before", "after"])
def test_one_empty_side_reports_every_sheet(side: str) -> None:
    sheets = [frame(role=side, sheet_no="A-101"), frame(role=side, sheet_no="A-102")]
    pairs = run(sheets, []) if side == "before" else run([], sheets)
    expected = STATUS_REMOVED if side == "before" else STATUS_ADDED
    assert [p.status for p in pairs] == [expected, expected]
