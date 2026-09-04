"""``compare/frames.py``: candidates, confirmation, the three boundary rules,
entity assignment, reading order (brief R1-04, contract §6).

Two kinds of input on purpose. Most cases are built here with ezdxf, because a
rule like "a title block two blocks deep, with its transform accumulated" needs
a drawing shaped exactly around it. The R1-07 fixtures
(``fixtures/compare/S*``) then check the same code against the drawings the
comparison engine will actually be graded on, which is where a rule that only
works on its own test drawing shows up.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ezdxf
import pytest
import yaml
from ezdxf.document import Drawing

from halo_engine.compare.config import DEFAULT_FRAMES_YAML, FramesConfig
from halo_engine.compare.frames import (
    A1_HEIGHT_MM,
    A1_WIDTH_MM,
    BOUNDARY_A1,
    BOUNDARY_EXTENTS,
    BOUNDARY_MODAL,
    BOUNDARY_RECT,
    KIND_TITLEBLOCK,
    KIND_UNRECOGNIZED,
    assign_entities,
    extract_file_frames,
    extract_frames,
    file_norm_key,
    normalize_key,
    parse_scale,
)

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "compare"

#: A1 at 1:100, the size every synthetic sheet here uses.
SHEET_W = A1_WIDTH_MM * 100
SHEET_H = A1_HEIGHT_MM * 100
#: The title block's own box, bottom-right of the sheet.
TB_W = 15000.0
TB_H = 4000.0

DEFAULT_ATTRIBS = (
    ("DWG_NO", "A-101"),
    ("TITLE", "1층 평면도"),
    ("SCALE", "1:100"),
    ("DATE", "2026-09-04"),
)


def config(**titleblock: Any) -> FramesConfig:
    """The packaged ``frames.yaml`` with a few ``titleblock`` keys overridden."""
    data = yaml.safe_load(DEFAULT_FRAMES_YAML.read_text("utf-8"))
    data["titleblock"].update(titleblock)
    return FramesConfig.model_validate(data)


def _define_titleblock(doc: Drawing, name: str, tags: tuple[str, ...]) -> None:
    block = doc.blocks.new(name)
    block.add_lwpolyline([(0, 0), (TB_W, 0), (TB_W, TB_H), (0, TB_H)], close=True)
    for index, tag in enumerate(tags):
        # Kept well inside the stamp: a text's bounding box dips below its
        # insertion point by a descender, and a stamp whose box pokes out of
        # the frame outline would make this fixture test the wrong rule.
        block.add_attdef(tag, (100.0, 400.0 + 700.0 * index), height=200.0)


def _add_titleblock(
    layout: Any,
    name: str,
    insert: tuple[float, float],
    attribs: tuple[tuple[str, str], ...],
) -> Any:
    reference = layout.add_blockref(name, insert)
    reference.add_auto_attribs(dict(attribs))
    return reference


def make_doc(
    *,
    sheets: int = 1,
    attribs: tuple[tuple[str, str], ...] = DEFAULT_ATTRIBS,
    block_name: str = "TITLEBLOCK",
    draw_frame: bool = True,
    gap: float = 6000.0,
) -> Drawing:
    """``sheets`` A1 frames in a row, each with a title block bottom-right."""
    doc = ezdxf.new(setup=False)
    _define_titleblock(doc, block_name, tuple(tag for tag, _ in attribs))
    msp = doc.modelspace()
    for index in range(sheets):
        x0 = index * (SHEET_W + gap)
        if draw_frame:
            msp.add_lwpolyline(
                [(x0, 0), (x0 + SHEET_W, 0), (x0 + SHEET_W, SHEET_H), (x0, SHEET_H)], close=True
            )
        sheet_attribs = tuple(
            (tag, f"A-{101 + index}" if tag == "DWG_NO" else value) for tag, value in attribs
        )
        _add_titleblock(msp, block_name, (x0 + SHEET_W - TB_W, 0.0), sheet_attribs)
    return doc


# --------------------------------------------------------------------------- text rules


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1:100", 100),
        ("1/100", 100),
        ("A3 1:100", 100),
        ("SCALE 1:50", 50),
        ("1 : 200", 200),
        ("NTS", None),
        ("", None),
    ],
)
def test_parse_scale_reads_the_denominator_or_nothing(text: str, expected: int | None) -> None:
    assert parse_scale(text) == expected


def test_parse_scale_ignores_a_date_that_looks_like_a_ratio() -> None:
    # `2026-09-04` has no `1:` in it; `S=1/300` does, buried in a prefix.
    assert parse_scale("2026-09-04") is None
    assert parse_scale("S=1/300") == 300
    assert parse_scale(None) is None


def test_normalize_key_folds_spaces_case_width_and_hyphens() -> None:
    cfg = config()
    assert normalize_key("a - 101", cfg) == "A-101"
    assert normalize_key("Ａ－１０１", cfg) == "A-101"  # full width
    assert normalize_key("A–101", cfg) == "A-101"  # en dash
    assert normalize_key("A_101", cfg) == "A-101"
    assert normalize_key(None, cfg) == ""


def test_normalize_key_obeys_the_settings_file() -> None:
    data = yaml.safe_load(DEFAULT_FRAMES_YAML.read_text("utf-8"))
    data["normalize"] = {
        "strip_spaces": False,
        "fullwidth_to_ascii": False,
        "upper": False,
        "unify_hyphen": False,
    }
    cfg = FramesConfig.model_validate(data)
    assert normalize_key(" a - 101 ", cfg) == "a - 101"


def test_file_norm_key_is_prefixed() -> None:
    assert file_norm_key("detail.dxf", config()) == "file:DETAIL.DXF"


# --------------------------------------------------------------------------- candidates


def test_a_matching_number_tag_confirms_the_title_block() -> None:
    frames = extract_frames(make_doc(), file_id="F1", config=config())
    assert len(frames) == 1
    frame = frames[0]
    assert frame.kind == KIND_TITLEBLOCK
    assert frame.block_name == "TITLEBLOCK"
    assert frame.sheet_no == "A-101"
    assert frame.sheet_title == "1층 평면도"
    assert frame.scale_text == "1:100"
    assert frame.scale_denominator == 100
    assert frame.date_text == "2026-09-04"
    assert frame.norm_key == "A-101"
    assert set(frame.attributes) == {"DWG_NO", "TITLE", "SCALE", "DATE"}


def test_a_title_tag_alone_is_enough() -> None:
    attribs = (("SHEETNAME", "1층 평면도"), ("TITLE", "1층 평면도"), ("REV", "0"))
    frames = extract_frames(make_doc(attribs=attribs), file_id="F1", config=config())
    assert frames[0].kind == KIND_TITLEBLOCK
    assert frames[0].sheet_no is None
    assert frames[0].norm_key == ""


def test_tags_are_matched_ignoring_case_spaces_and_separators() -> None:
    attribs = (("dwg no", "A-101"), ("Dwg_Name", "1층 평면도"), ("scl", "1:50"))
    cfg = config(number_tags=["DWG_NO"], title_tags=["DWG_NAME"], scale_tags=["SCL"])
    frame = extract_frames(make_doc(attribs=attribs), file_id="F1", config=cfg)[0]
    assert frame.sheet_no == "A-101"
    assert frame.sheet_title == "1층 평면도"
    assert frame.scale_denominator == 50


def test_no_tag_matches_falls_back_to_the_most_repeated_block() -> None:
    """Three anonymous stamps and one one-off: the repeated block wins."""
    doc = ezdxf.new(setup=False)
    _define_titleblock(doc, "STAMP", ("AAA", "BBB", "CCC"))
    _define_titleblock(doc, "ONEOFF", ("XXX", "YYY", "ZZZ"))
    msp = doc.modelspace()
    for index in range(3):
        x0 = index * (SHEET_W + 6000.0)
        msp.add_lwpolyline(
            [(x0, 0), (x0 + SHEET_W, 0), (x0 + SHEET_W, SHEET_H), (x0, SHEET_H)], close=True
        )
        _add_titleblock(
            msp,
            "STAMP",
            (x0 + SHEET_W - TB_W, 0.0),
            (("AAA", f"{index}"), ("BBB", "b"), ("CCC", "c")),
        )
    _add_titleblock(msp, "ONEOFF", (0.0, 30000.0), (("XXX", "1"), ("YYY", "2"), ("ZZZ", "3")))

    frames = extract_frames(doc, file_id="F1", config=config())
    assert len(frames) == 3
    assert {f.block_name for f in frames} == {"STAMP"}
    assert all(f.sheet_no is None for f in frames)


def test_the_fallback_can_be_switched_off() -> None:
    doc = make_doc(attribs=(("AAA", "1"), ("BBB", "2"), ("CCC", "3")))
    frames = extract_frames(doc, file_id="F1", config=config(fallback_most_common_block=False))
    assert [f.kind for f in frames] == [KIND_UNRECOGNIZED]


def test_min_attribs_rejects_a_two_attribute_block() -> None:
    doc = make_doc(attribs=(("AAA", "1"), ("BBB", "2")))
    frames = extract_frames(doc, file_id="F1", config=config())
    assert [f.kind for f in frames] == [KIND_UNRECOGNIZED]


def test_block_name_patterns_restrict_the_candidates_and_waive_min_attribs() -> None:
    """A block named in `frames.yaml` is the title block by declaration.

    Which matters on the real set: a converted XREF sometimes arrives with its
    ATTRIBs stripped (spike §3.2), and naming the block is then the only way
    left to find the sheets.
    """
    doc = ezdxf.new(setup=False)
    _define_titleblock(doc, "TITLE BLOCK-V", ("ONLYONE",))
    _define_titleblock(doc, "GRID_BUBBLE", ("A", "B", "C"))
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (SHEET_W, 0), (SHEET_W, SHEET_H), (0, SHEET_H)], close=True)
    _add_titleblock(msp, "TITLE BLOCK-V", (SHEET_W - TB_W, 0.0), (("ONLYONE", "A-101"),))
    _add_titleblock(msp, "GRID_BUBBLE", (1000.0, 30000.0), (("A", "1"), ("B", "2"), ("C", "3")))

    frames = extract_frames(doc, file_id="F1", config=config(block_name_patterns=["TITLE BLOCK*"]))
    assert [f.block_name for f in frames] == ["TITLE BLOCK-V"]


# --------------------------------------------------------------------------- nesting


def _nested_doc(depth: int, offset: tuple[float, float]) -> Drawing:
    """A title block ``depth`` blocks inside a model-space INSERT.

    Depth 1 is what an embedded XREF looks like after ``ingest/xref.py`` turns
    the XREF block into an ordinary block holding the referenced drawing.
    """
    doc = ezdxf.new(setup=False)
    _define_titleblock(doc, "TITLEBLOCK", tuple(tag for tag, _ in DEFAULT_ATTRIBS))
    inner = doc.blocks.new("XR_TITLE")
    _add_titleblock(inner, "TITLEBLOCK", (0.0, 0.0), DEFAULT_ATTRIBS)
    host_name = "XR_TITLE"
    if depth == 2:
        outer = doc.blocks.new("XR_OUTER")
        outer.add_blockref("XR_TITLE", (0.0, 0.0))
        host_name = "XR_OUTER"
    if depth == 3:
        outer = doc.blocks.new("XR_OUTER")
        outer.add_blockref("XR_TITLE", (0.0, 0.0))
        outermost = doc.blocks.new("XR_OUTERMOST")
        outermost.add_blockref("XR_OUTER", (0.0, 0.0))
        host_name = "XR_OUTERMOST"

    msp = doc.modelspace()
    msp.add_lwpolyline(
        [
            (offset[0] - SHEET_W + TB_W, offset[1]),
            (offset[0] + TB_W, offset[1]),
            (offset[0] + TB_W, offset[1] + SHEET_H),
            (offset[0] - SHEET_W + TB_W, offset[1] + SHEET_H),
        ],
        close=True,
    )
    msp.add_blockref(host_name, offset)
    return doc


@pytest.mark.parametrize("depth", [1, 2])
def test_a_title_block_inside_an_embedded_xref_is_found_with_its_transform(depth: int) -> None:
    offset = (40000.0, 12000.0)
    frames = extract_frames(_nested_doc(depth, offset), file_id="F1", config=config())
    assert len(frames) == 1
    frame = frames[0]
    assert frame.sheet_no == "A-101"
    # The frame is placed in world coordinates, not in the block's own.
    assert frame.bbox == pytest.approx(
        [offset[0] - SHEET_W + TB_W, offset[1], offset[0] + TB_W, offset[1] + SHEET_H]
    )
    # provenance.path is the INSERT chain from model space down to the stamp.
    assert len(frame.provenance["path"]) == depth
    assert frame.provenance["space"] == "MODEL"
    assert frame.provenance["handle"] == frame.titleblock_handle


def test_a_title_block_three_blocks_deep_is_ignored_with_a_warning() -> None:
    frames = extract_frames(_nested_doc(3, (0.0, 0.0)), file_id="F1", config=config())
    assert [f.kind for f in frames] == [KIND_UNRECOGNIZED]
    assert any(w.startswith("titleblock_search_depth_exceeded") for w in frames[0].warnings)


# --------------------------------------------------------------------------- boundary


def test_boundary_a_takes_the_smallest_enclosing_rectangle() -> None:
    frame = extract_frames(make_doc(), file_id="F1", config=config())[0]
    assert frame.boundary_source == BOUNDARY_RECT
    assert frame.bbox == [0.0, 0.0, SHEET_W, SHEET_H]


def test_boundary_a_ignores_a_rectangle_that_only_wraps_the_stamp() -> None:
    """A box drawn tightly around the title block is not the sheet outline."""
    doc = make_doc()
    doc.modelspace().add_lwpolyline(
        [
            (SHEET_W - TB_W, 0.0),
            (SHEET_W, 0.0),
            (SHEET_W, TB_H),
            (SHEET_W - TB_W, TB_H),
        ],
        close=True,
    )
    frame = extract_frames(doc, file_id="F1", config=config())[0]
    assert frame.bbox == [0.0, 0.0, SHEET_W, SHEET_H]


def test_boundary_b_uses_the_files_modal_frame_size() -> None:
    """One sheet has no outline; it borrows the size the other two showed."""
    doc = make_doc(sheets=3)
    lonely = list(doc.modelspace().query("LWPOLYLINE"))[2]
    doc.modelspace().delete_entity(lonely)

    frames = extract_frames(doc, file_id="F1", config=config())
    sources = {f.sheet_no: f.boundary_source for f in frames}
    assert sources == {
        "A-101": BOUNDARY_RECT,
        "A-102": BOUNDARY_RECT,
        "A-103": BOUNDARY_MODAL,
    }
    borrowed = next(f for f in frames if f.sheet_no == "A-103")
    assert borrowed.width == pytest.approx(SHEET_W)
    assert borrowed.height == pytest.approx(SHEET_H)
    # Anchored at the title block's bottom-right corner.
    assert borrowed.bbox[2] == pytest.approx(2 * (SHEET_W + 6000.0) + SHEET_W)
    assert borrowed.bbox[1] == pytest.approx(0.0)


def test_boundary_c_falls_back_to_a1_times_the_scale() -> None:
    doc = make_doc(draw_frame=False, attribs=(*DEFAULT_ATTRIBS[:2], ("SCALE", "1:50")))
    frame = extract_frames(doc, file_id="F1", config=config())[0]
    assert frame.boundary_source == BOUNDARY_A1
    assert frame.width == pytest.approx(A1_WIDTH_MM * 50)
    assert frame.height == pytest.approx(A1_HEIGHT_MM * 50)


def test_boundary_c_assumes_1_to_100_when_the_scale_is_unreadable() -> None:
    doc = make_doc(draw_frame=False, attribs=(*DEFAULT_ATTRIBS[:2], ("SCALE", "NTS")))
    frame = extract_frames(doc, file_id="F1", config=config())[0]
    assert frame.scale_denominator is None
    assert frame.width == pytest.approx(A1_WIDTH_MM * 100)


def test_a_stamp_outside_its_frame_widens_the_frame() -> None:
    """Defaults for ambiguity: never lose the title block off the sheet."""
    doc = ezdxf.new(setup=False)
    _define_titleblock(doc, "TITLEBLOCK", tuple(tag for tag, _ in DEFAULT_ATTRIBS))
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (SHEET_W, 0), (SHEET_W, SHEET_H), (0, SHEET_H)], close=True)
    # Sitting to the right of the drawn frame: no rectangle contains it.
    _add_titleblock(msp, "TITLEBLOCK", (SHEET_W + 1000.0, 0.0), DEFAULT_ATTRIBS)

    frame = extract_frames(doc, file_id="F1", config=config())[0]
    assert frame.boundary_source == BOUNDARY_A1
    assert frame.bbox[2] == pytest.approx(SHEET_W + 1000.0 + TB_W)
    assert "frame_widened_for_titleblock" not in frame.warnings  # A1 already covers it


# --------------------------------------------------------------------------- assignment


def test_entities_are_assigned_by_bounding_box_centre() -> None:
    doc = make_doc(sheets=2)
    msp = doc.modelspace()
    left = msp.add_line((1000, 1000), (2000, 2000))
    right = msp.add_line((SHEET_W + 7000, 1000), (SHEET_W + 8000, 2000))
    # Straddles the gap between the two sheets; its centre is in neither.
    outside = msp.add_line((SHEET_W + 1000, 1000), (SHEET_W + 5000, 1000))

    frames = extract_frames(doc, file_id="F1", config=config())
    assign_entities(doc, frames)

    assert left.dxf.handle in frames[0].entity_handles
    assert right.dxf.handle in frames[1].entity_handles
    assert all(outside.dxf.handle not in f.entity_handles for f in frames)
    assert frames[0].entity_handles == sorted(frames[0].entity_handles)
    # The stamps themselves belong to their own sheets.
    for frame in frames:
        assert frame.titleblock_handle in frame.entity_handles


def test_insert_centres_match_the_full_bounding_box() -> None:
    """The per-block shortcut in ``_CentreFinder`` must be exact, not close.

    A rotated, scaled INSERT is the case that would expose a wrong matrix
    order; an affine map takes a box's centre to the mapped box's centre, so
    the two ways of computing it have to agree to floating point.
    """
    import ezdxf.bbox

    from halo_engine.compare.frames import _CentreFinder

    doc = ezdxf.new(setup=False)
    block = doc.blocks.new("B", base_point=(5, 7))
    block.add_lwpolyline([(10, 10), (30, 10), (30, 20), (10, 20)], close=True)
    reference = doc.modelspace().add_blockref(
        "B", (100, 200), dxfattribs={"rotation": 30, "xscale": 2, "yscale": 2}
    )

    box = ezdxf.bbox.extents([reference], fast=True)
    expected = (
        (float(box.extmin.x) + float(box.extmax.x)) / 2.0,
        (float(box.extmin.y) + float(box.extmax.y)) / 2.0,
    )
    assert _CentreFinder(doc).centre(reference) == pytest.approx(expected)


def test_assignment_is_stable_across_two_runs() -> None:
    doc = make_doc(sheets=2)
    first = extract_frames(doc, file_id="F1", config=config())
    assign_entities(doc, first)
    second = extract_frames(doc, file_id="F1", config=config())
    assign_entities(doc, second)
    assert [f.to_row() for f in first] == [f.to_row() for f in second]


# --------------------------------------------------------------------------- reading order


def test_sort_index_reads_top_row_first_then_left_to_right() -> None:
    doc = ezdxf.new(setup=False)
    _define_titleblock(doc, "TITLEBLOCK", tuple(tag for tag, _ in DEFAULT_ATTRIBS))
    msp = doc.modelspace()
    # Two rows of two, added in a deliberately jumbled order.
    positions = {
        "A-104": (SHEET_W + 6000.0, 0.0),
        "A-101": (0.0, SHEET_H + 6000.0),
        "A-103": (0.0, 0.0),
        "A-102": (SHEET_W + 6000.0, SHEET_H + 6000.0),
    }
    for number, (x0, y0) in positions.items():
        msp.add_lwpolyline(
            [(x0, y0), (x0 + SHEET_W, y0), (x0 + SHEET_W, y0 + SHEET_H), (x0, y0 + SHEET_H)],
            close=True,
        )
        _add_titleblock(
            msp,
            "TITLEBLOCK",
            (x0 + SHEET_W - TB_W, y0),
            tuple((tag, number if tag == "DWG_NO" else value) for tag, value in DEFAULT_ATTRIBS),
        )

    frames = extract_frames(doc, file_id="F1", config=config())
    assert [f.sheet_no for f in frames] == ["A-101", "A-102", "A-103", "A-104"]
    assert [f.sort_index for f in frames] == [0, 1, 2, 3]


# --------------------------------------------------------------------------- unrecognised


def test_a_file_without_a_title_block_produces_one_unrecognised_frame() -> None:
    doc = ezdxf.new(setup=False)
    doc.modelspace().add_line((0, 0), (5000, 3350))
    frames = extract_frames(doc, file_id="F1", config=config())
    assert len(frames) == 1
    frame = frames[0]
    assert frame.kind == KIND_UNRECOGNIZED
    assert frame.boundary_source == BOUNDARY_EXTENTS
    assert frame.titleblock_handle is None
    assert frame.bbox == [0.0, 0.0, 5000.0, 3350.0]
    assign_entities(doc, frames)
    assert len(frame.entity_handles) == 1


def test_an_empty_file_still_produces_a_frame() -> None:
    frames = extract_frames(ezdxf.new(setup=False), file_id="F1", config=config())
    assert [f.kind for f in frames] == [KIND_UNRECOGNIZED]
    assert frames[0].bbox == [0.0, 0.0, 0.0, 0.0]
    assert frames[0].provenance["handle"] == "0"


# --------------------------------------------------------------------------- R1-07 fixtures


def _fixture(scenario: str, side: str, name: str) -> Path:
    path = FIXTURES / scenario / side / name
    if not path.is_file():
        pytest.skip(f"{path} missing -- run `cd fixtures/compare/gen && uv run python -m ...`")
    return path


def test_fixture_s13_has_two_sheets_in_one_file() -> None:
    doc = ezdxf.readfile(_fixture("S13_multi_sheet", "before", "plan.dxf"))
    frames = extract_frames(doc, file_id="F1", config=config())
    assign_entities(doc, frames)
    assert [f.sheet_no for f in frames] == ["A-101", "A-102"]
    assert [f.boundary_source for f in frames] == [BOUNDARY_RECT, BOUNDARY_RECT]
    assert frames[0].bbox == [0.0, 0.0, 84100.0, 59400.0]
    assert all(f.entity_handles for f in frames)
    # Every sheet's entities are its own.
    assert not set(frames[0].entity_handles) & set(frames[1].entity_handles)


def test_fixture_s17_reads_a_1_to_50_sheet() -> None:
    doc = ezdxf.readfile(_fixture("S17_scale_50", "before", "A-101.dxf"))
    frame = extract_frames(doc, file_id="F1", config=config())[0]
    assert frame.scale_denominator == 50
    assert frame.bbox == [0.0, 0.0, A1_WIDTH_MM * 50, A1_HEIGHT_MM * 50]


def test_fixture_s16_detail_is_unrecognised() -> None:
    doc = ezdxf.readfile(_fixture("S16_unrecognized", "after", "detail.dxf"))
    frames = extract_frames(doc, file_id="F1", config=config())
    assert [f.kind for f in frames] == [KIND_UNRECOGNIZED]


def test_fixture_s15_frame_follows_the_shifted_drawing() -> None:
    doc = ezdxf.readfile(_fixture("S15_frame_shift", "after", "A-101.dxf"))
    frame = extract_frames(doc, file_id="F1", config=config())[0]
    assert frame.bbox == [50000.0, 20000.0, 50000.0 + 84100.0, 20000.0 + 59400.0]


# --------------------------------------------------------------------------- worker entry


def test_extract_file_frames_reports_a_bad_file_instead_of_raising(tmp_path: Path) -> None:
    broken = tmp_path / "broken.dxf"
    broken.write_text("not a dxf at all", encoding="utf-8")
    result = extract_file_frames(str(broken), "F1", config())
    assert result.error
    assert result.frames == []
    assert result.file_id == "F1"


def test_extract_file_frames_returns_picklable_records(tmp_path: Path) -> None:
    import pickle

    path = tmp_path / "plan.dxf"
    make_doc(sheets=2).saveas(path)
    result = extract_file_frames(str(path), "F1", config())
    assert result.error is None
    assert [f.sheet_no for f in result.frames] == ["A-101", "A-102"]
    assert result.entity_count > 0
    restored = pickle.loads(pickle.dumps(result))
    assert [f.to_row() for f in restored.frames] == [f.to_row() for f in result.frames]
