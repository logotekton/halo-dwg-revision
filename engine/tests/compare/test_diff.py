"""``compare/diff.py``: the matching stages and the fold rules, one rule at a time.

The scenario suite proves the engine answers the seventeen planted revisions
correctly; these tests pin down *why* it does, on drawings small enough that a
failure names the rule that broke. Every threshold is read from the packaged
``compare.yaml`` rather than written out here, so a settings change that should
have moved a boundary fails the test that asserts the boundary moved.
"""

from __future__ import annotations

import ezdxf
import pytest
from ezdxf.document import Drawing
from .scenario_helpers import packaged_compare_config

from halo_engine.compare.diff import (
    KIND_ADDED,
    KIND_BLOCKDEF,
    KIND_DIMENSION,
    KIND_MODIFIED,
    KIND_MOVED,
    KIND_REMOVED,
    KIND_TEXT,
    WARN_FRAME_SIZE_DIFFERS,
    diff_pair,
    match_entities,
)
from halo_engine.compare.frames import FrameRecord
from halo_engine.compare.signatures import BoxCache, frame_signatures

CONFIG = packaged_compare_config()
FRAME = [0.0, 0.0, 84100.0, 59400.0]


def new_doc() -> Drawing:
    doc = ezdxf.new("R2018", setup=False)
    for name in ("A-WALL", "A-WALL2", "A-TEXT", "A-DIM"):
        doc.layers.add(name)
    return doc


def frame_of(doc: Drawing, *, bbox: list[float] | None = None, file_id: str = "f") -> FrameRecord:
    """A ``FrameRecord`` covering every model-space entity of ``doc``."""
    return FrameRecord(
        file_id=file_id,
        bbox=list(bbox or FRAME),
        entity_handles=sorted(str(entity.dxf.handle) for entity in doc.modelspace()),
        norm_key="A-101",
        sheet_no="A-101",
    )


def compare(before: Drawing, after: Drawing, **kwargs: object) -> list:
    before_frame = kwargs.pop("before_frame", None) or frame_of(before)
    after_frame = kwargs.pop("after_frame", None) or frame_of(after)
    return diff_pair(before, after, before_frame, after_frame, CONFIG).changes


# --------------------------------------------------------------------------- identity


def test_two_identical_sheets_produce_no_changes() -> None:
    before, after = new_doc(), new_doc()
    for doc in (before, after):
        doc.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL"})
        doc.modelspace().add_circle((500, 500), 250, dxfattribs={"layer": "A-WALL"})
    assert compare(before, after) == []


def test_entities_outside_the_frame_are_not_compared() -> None:
    """Brief §1: "도곽 밖 엔티티는 비교하지 않는다"."""
    before, after = new_doc(), new_doc()
    before.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL"})
    stray = after.modelspace().add_line((5, 5), (9, 9), dxfattribs={"layer": "A-WALL"})

    after_frame = frame_of(after)
    after_frame.entity_handles = [
        handle for handle in after_frame.entity_handles if handle != str(stray.dxf.handle)
    ]
    assert compare(before, after, after_frame=after_frame) == []

    with_stray = compare(before, after)
    assert [change.kind for change in with_stray] == [KIND_ADDED]


def test_a_sheet_drawn_50m_away_compares_clean() -> None:
    """Frame-local coordinates, the ``S15_frame_shift`` rule in miniature."""
    before, after = new_doc(), new_doc()
    before.modelspace().add_line((100, 100), (1100, 100), dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_line((50100, 20100), (51100, 20100), dxfattribs={"layer": "A-WALL"})

    result = diff_pair(
        before,
        after,
        frame_of(before),
        frame_of(after, bbox=[50000.0, 20000.0, 134100.0, 79400.0]),
        CONFIG,
    )
    assert result.changes == []
    assert result.offset == (50000.0, 20000.0)


def test_frames_of_different_size_warn_and_keep_going() -> None:
    before, after = new_doc(), new_doc()
    before.modelspace().add_line((0, 0), (1000, 0))
    after.modelspace().add_line((0, 0), (1000, 0))
    result = diff_pair(
        before,
        after,
        frame_of(before),
        frame_of(after, bbox=[0.0, 0.0, 42050.0, 29700.0]),
        CONFIG,
    )
    assert result.warnings == [WARN_FRAME_SIZE_DIFFERS]
    assert result.changes == []


# --------------------------------------------------------------------------- stages


def test_a_move_across_a_grid_cell_boundary_is_still_the_same_entity() -> None:
    """Stage 2 gathers candidates from the ±1 neighbouring cells (brief §1).

    The fingerprint grid is 1mm. An entity at x=1000.4 that moved to x=1000.6
    lands in the next cell, and without the neighbour search it would be
    reported as a removal plus an addition instead of one small move. (0.2mm is
    still well past ``minor.move_tolerance``, so the move itself is real -- what
    is being tested is that the two are recognised as one entity at all.)
    """
    tolerance = CONFIG.match.fingerprint_tolerance
    before, after = new_doc(), new_doc()
    before.modelspace().add_circle((1000.4, 500), 30, dxfattribs={"layer": "A-WALL"})
    circle = after.modelspace().add_circle((1000.6, 500), 30, dxfattribs={"layer": "A-WALL"})
    circle.dxf.handle = "AAAA"  # the handle stage must not be what saves this

    changes = compare(before, after)
    assert [change.kind for change in changes] == [KIND_MOVED]
    assert changes[0].delta is not None
    assert changes[0].delta["distance"] == pytest.approx(0.2)
    assert changes[0].delta["distance"] <= tolerance


def test_the_handle_stage_recognises_an_entity_that_was_edited_in_place() -> None:
    before, after = new_doc(), new_doc()
    before.modelspace().add_text("거실", dxfattribs={"layer": "A-TEXT", "height": 350}).set_placement(
        (1000, 1000)
    )
    after.modelspace().add_text("리빙룸", dxfattribs={"layer": "A-TEXT", "height": 350}).set_placement(
        (1000, 1000)
    )
    changes = compare(before, after)
    assert [change.kind for change in changes] == [KIND_TEXT]
    assert changes[0].before_handle == changes[0].after_handle
    assert changes[0].delta == {"before": "거실", "after": "리빙룸"}


def test_the_shape_stage_finds_a_move_after_every_handle_was_renumbered() -> None:
    """Stage 4: what makes ``S12_whole_redraw`` report one move, not two entities."""
    before, after = new_doc(), new_doc()
    before.modelspace().add_lwpolyline(
        [(0, 0), (900, 0), (900, 40), (0, 40)], close=True, dxfattribs={"layer": "A-WALL"}
    )
    # A different handle *and* a different position: only the shape connects them.
    moved = after.modelspace().add_lwpolyline(
        [(1250, 0), (2150, 0), (2150, 40), (1250, 40)], close=True, dxfattribs={"layer": "A-WALL"}
    )
    moved.dxf.handle = "7F1"

    changes = compare(before, after)
    assert [change.kind for change in changes] == [KIND_MOVED]
    assert changes[0].delta is not None
    assert changes[0].delta["move"] == [1250.0, 0.0]
    assert changes[0].delta["distance"] == 1250.0


def test_handle_matching_does_not_pair_unrelated_entities_that_inherited_a_number() -> None:
    """The guard that keeps a redrawn sheet from reporting a change per entity.

    Both drawings have a wall at handle ``100``, but they are different walls
    metres apart, and each has its real counterpart elsewhere in the other
    drawing. The position stages take those pairs first, and the handle stage
    then has nothing plausible left to pair.
    """
    before, after = new_doc(), new_doc()
    before.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL"})
    before.modelspace().add_line((0, 9000), (1000, 9000), dxfattribs={"layer": "A-WALL"})
    # Same two walls, drawn in the opposite order, so the handles swap.
    after.modelspace().add_line((0, 9000), (1000, 9000), dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL"})

    assert compare(before, after) == []


def test_added_and_removed_are_what_is_left_over() -> None:
    before, after = new_doc(), new_doc()
    before.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_circle((40000, 40000), 500, dxfattribs={"layer": "A-WALL"})
    kinds = sorted(change.kind for change in compare(before, after))
    assert kinds == [KIND_ADDED, KIND_REMOVED]


# --------------------------------------------------------------------------- folding


@pytest.mark.parametrize(
    ("attribute", "before_value", "after_value", "reason"),
    [
        ("layer", "A-WALL", "A-WALL2", "layer_only"),
        ("color", 1, 3, "color_only"),
        ("linetype", "BYLAYER", "ByBlock", "linetype_only"),
        ("lineweight", 13, 30, "lineweight_only"),
    ],
)
def test_a_property_only_difference_is_folded(
    attribute: str, before_value: object, after_value: object, reason: str
) -> None:
    before, after = new_doc(), new_doc()
    before.modelspace().add_line((0, 0), (1000, 0), dxfattribs={attribute: before_value})
    after.modelspace().add_line((0, 0), (1000, 0), dxfattribs={attribute: after_value})

    changes = compare(before, after)
    assert len(changes) == 1, changes
    assert changes[0].kind == KIND_MODIFIED
    assert changes[0].minor is True
    assert changes[0].minor_reason == reason


def test_several_fold_reasons_are_joined_with_a_plus_in_schema_order() -> None:
    before, after = new_doc(), new_doc()
    before.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL", "color": 1})
    after.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL2", "color": 3})

    changes = compare(before, after)
    assert changes[0].minor_reason == "layer_only+color_only"


@pytest.mark.parametrize("distance", [0.0, 0.005, 0.01])
def test_a_move_within_the_tolerance_is_minor(distance: float) -> None:
    tolerance = CONFIG.minor.move_tolerance
    assert distance <= tolerance
    before, after = new_doc(), new_doc()
    before.modelspace().add_circle((1000, 500), 30, dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_circle((1000 + distance, 500), 30, dxfattribs={"layer": "A-WALL"})

    changes = compare(before, after)
    if distance == 0.0:
        assert changes == []
        return
    assert changes[0].kind == KIND_MOVED
    assert changes[0].minor is True
    assert changes[0].minor_reason == "move_le_0_01"


def test_a_move_past_the_tolerance_is_a_real_change() -> None:
    before, after = new_doc(), new_doc()
    before.modelspace().add_circle((1000, 500), 30, dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_circle((1000.02, 500), 30, dxfattribs={"layer": "A-WALL"})

    changes = compare(before, after)
    assert changes[0].kind == KIND_MOVED
    assert changes[0].minor is False
    assert changes[0].minor_reason is None


def test_a_geometry_change_is_never_folded_however_many_properties_moved_too() -> None:
    before, after = new_doc(), new_doc()
    before.modelspace().add_circle((1000, 500), 30, dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_circle((1000, 500), 60, dxfattribs={"layer": "A-WALL2"})

    changes = compare(before, after)
    assert changes[0].kind == KIND_MODIFIED
    assert changes[0].minor is False
    assert changes[0].minor_reason is None


def test_mtext_that_only_changed_formatting_is_folded() -> None:
    before, after = new_doc(), new_doc()
    before.modelspace().add_mtext("범례\\P벽체", dxfattribs={"layer": "A-TEXT", "char_height": 300})
    after.modelspace().add_mtext(
        "{\\fArial|b1;범례}\\P벽체", dxfattribs={"layer": "A-TEXT", "char_height": 300}
    )
    changes = compare(before, after)
    assert len(changes) == 1, changes
    assert changes[0].minor is True
    assert changes[0].minor_reason == "mtext_format_only"


def test_a_rotation_is_modified_rather_than_moved_in_r1() -> None:
    """Brief Defaults for ambiguity: rotation and mirroring wait for R2-03."""
    before, after = new_doc(), new_doc()
    before.modelspace().add_line((0, 0), (1000, 0), dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_line((0, 0), (0, 1000), dxfattribs={"layer": "A-WALL"})

    changes = compare(before, after)
    assert [change.kind for change in changes] == [KIND_MODIFIED]


# --------------------------------------------------------------------------- kinds


def test_a_dimension_whose_measurement_changed_is_a_dimension_change() -> None:
    before, after = new_doc(), new_doc()
    for doc, width in ((before, 12000), (after, 12500)):
        dim = doc.modelspace().add_linear_dim(
            base=(0, 1500), p1=(0, 0), p2=(width, 0), dxfattribs={"layer": "A-DIM"}
        )
        dim.render()

    changes = compare(before, after)
    assert [change.kind for change in changes] == [KIND_DIMENSION]
    assert changes[0].delta is not None
    assert changes[0].delta["before"] == 12000.0
    assert changes[0].delta["after"] == 12500.0


def test_a_changed_block_definition_is_one_change_for_every_instance() -> None:
    before, after = new_doc(), new_doc()
    for doc, panel in ((before, 900), (after, 850)):
        block = doc.blocks.new("DOOR_900")
        block.add_line((0, 0), (panel, 0))
        for index in range(3):
            doc.modelspace().add_blockref(
                "DOOR_900", (index * 5000, 0), dxfattribs={"layer": "A-WALL"}
            )

    changes = compare(before, after)
    assert [change.kind for change in changes] == [KIND_BLOCKDEF]
    assert changes[0].delta == {"block": "DOOR_900", "instances": 3}
    assert changes[0].etype == "INSERT"
    assert len(changes[0].instance_boxes) == 3


def test_an_unchanged_block_definition_produces_nothing() -> None:
    before, after = new_doc(), new_doc()
    for doc in (before, after):
        block = doc.blocks.new("DOOR_900")
        block.add_line((0, 0), (900, 0))
        doc.modelspace().add_blockref("DOOR_900", (0, 0), dxfattribs={"layer": "A-WALL"})
    assert compare(before, after) == []


# --------------------------------------------------------------------------- ordering


def test_changes_are_numbered_in_reading_order() -> None:
    """``seq`` is written into the sidecar and the DXF, so it follows the drawing."""
    before, after = new_doc(), new_doc()
    after.modelspace().add_circle((60000, 50000), 100, dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_circle((10000, 50000), 100, dxfattribs={"layer": "A-WALL"})
    after.modelspace().add_circle((10000, 10000), 100, dxfattribs={"layer": "A-WALL"})

    changes = compare(before, after)
    assert [change.seq for change in changes] == [1, 2, 3]
    assert [change.bbox[0] for change in changes] == [9900.0, 59900.0, 9900.0]


def test_matching_is_stable_when_the_same_shape_appears_many_times() -> None:
    before, after = new_doc(), new_doc()
    for doc in (before, after):
        for index in range(20):
            doc.modelspace().add_circle((index * 1000, 0), 100, dxfattribs={"layer": "A-WALL"})
    signatures_before = frame_signatures(
        before, handles=frame_of(before).entity_handles, origin=(0.0, 0.0), boxes=BoxCache(before)
    )
    signatures_after = frame_signatures(
        after, handles=frame_of(after).entity_handles, origin=(0.0, 0.0), boxes=BoxCache(after)
    )
    pairing = match_entities(signatures_before, signatures_after, CONFIG)
    assert len(pairing.matched) == 20
    assert all(method == "identity" for method in pairing.method.values())
