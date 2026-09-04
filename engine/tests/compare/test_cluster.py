"""``compare/cluster.py``: grouping, numbering and the cloud-mark geometry.

The cloud mark is the only part of the comparison that ends up printed on a
drawing and handed to a site engineer, so its geometry is tested against the
contract's numbers directly (``docs/contracts/compare-dxf.md`` §5) rather than
against a golden file: an arc chord of 100mm at 1:100 and 50mm at 1:50 is a
promise to the person reading the paper.
"""

from __future__ import annotations

import math

import pytest

from halo_engine.compare.cluster import (
    BLOCKDEF_SPLIT_RATIO,
    badge_geometry,
    build_clusters,
    cloud_polyline,
    cluster_signature,
    grouping_distance,
)
from halo_engine.compare.diff import KIND_ADDED, KIND_BLOCKDEF, KIND_MOVED, ChangeRecord
from halo_engine.compare.frames import FrameRecord

from .scenario_helpers import packaged_compare_config

CONFIG = packaged_compare_config()
A1_FRAME = FrameRecord(file_id="f", bbox=[0.0, 0.0, 84100.0, 59400.0], norm_key="A-101")


def change(seq: int, box: list[float], *, kind: str = KIND_ADDED, **kwargs: object) -> ChangeRecord:
    return ChangeRecord(
        seq=seq,
        kind=kind,
        etype=str(kwargs.pop("etype", "LWPOLYLINE")),
        layer=str(kwargs.pop("layer", "A-WALL")),
        bbox=box,
        after_handle=f"{seq:X}",
        **kwargs,  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------------- grouping


def test_the_grouping_distance_comes_from_the_settings() -> None:
    expected = max(
        84100.0 * CONFIG.cluster.grow_ratio,
        CONFIG.cluster.grow_min * 1.0,
    )
    assert grouping_distance(A1_FRAME, CONFIG, 1.0) == expected


def test_changes_closer_than_the_grouping_distance_share_one_cloud() -> None:
    distance = grouping_distance(A1_FRAME, CONFIG, 1.0)
    near = distance / 2
    clusters = build_clusters(
        [
            change(1, [10000.0, 10000.0, 10100.0, 10100.0]),
            change(2, [10100.0 + near, 10000.0, 10200.0 + near, 10100.0]),
        ],
        A1_FRAME,
        CONFIG,
    )
    assert len(clusters) == 1
    assert clusters[0].change_seqs == [1, 2]


def test_changes_further_apart_get_their_own_clouds() -> None:
    distance = grouping_distance(A1_FRAME, CONFIG, 1.0)
    clusters = build_clusters(
        [
            change(1, [10000.0, 10000.0, 10100.0, 10100.0]),
            change(2, [10100.0 + distance * 3, 10000.0, 10200.0 + distance * 3, 10100.0]),
        ],
        A1_FRAME,
        CONFIG,
    )
    assert len(clusters) == 2


def test_minor_changes_never_get_a_cloud_mark() -> None:
    """Contract §3: folded changes are recorded, listed, and not drawn."""
    clusters = build_clusters(
        [change(1, [10000.0, 10000.0, 10100.0, 10100.0], minor=True, minor_reason="layer_only")],
        A1_FRAME,
        CONFIG,
    )
    assert clusters == []


def test_numbering_reads_the_sheet_top_row_first_then_left_to_right() -> None:
    clusters = build_clusters(
        [
            change(1, [40000.0, 8000.0, 40100.0, 8100.0]),  # bottom row, right
            change(2, [8000.0, 8000.0, 8100.0, 8100.0]),  # bottom row, left
            change(3, [40000.0, 50000.0, 40100.0, 50100.0]),  # top row, right
            change(4, [8000.0, 50000.0, 8100.0, 50100.0]),  # top row, left
        ],
        A1_FRAME,
        CONFIG,
    )
    assert [cluster.change_seqs for cluster in clusters] == [[4], [3], [2], [1]]
    assert [cluster.number for cluster in clusters] == [1, 2, 3, 4]


def test_a_moved_cluster_covers_both_positions() -> None:
    moved = change(
        1,
        [10000.0, 10000.0, 12000.0, 11000.0],
        kind=KIND_MOVED,
        delta={"move": [1250.0, 0.0], "distance": 1250.0},
    )
    clusters = build_clusters([moved], A1_FRAME, CONFIG)
    assert clusters[0].bbox == moved.bbox
    assert clusters[0].kind == KIND_MOVED


def test_a_cluster_of_several_kinds_is_mixed() -> None:
    clusters = build_clusters(
        [
            change(1, [10000.0, 10000.0, 10100.0, 10100.0], kind=KIND_ADDED),
            change(2, [10100.0, 10000.0, 10200.0, 10100.0], kind=KIND_MOVED),
        ],
        A1_FRAME,
        CONFIG,
    )
    assert len(clusters) == 1
    assert clusters[0].kind == "mixed"


# --------------------------------------------------------------------------- blockdef


def _blockdef(boxes: list[list[float]]) -> ChangeRecord:
    union = [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]
    return ChangeRecord(
        seq=1,
        kind=KIND_BLOCKDEF,
        etype="INSERT",
        layer="A-DOOR",
        bbox=union,
        delta={"block": "DOOR_900", "instances": len(boxes)},
        instance_boxes=boxes,
        instance_handles=[(f"B{i}", f"A{i}") for i in range(len(boxes))],
    )


def test_a_tight_blockdef_change_is_one_cloud() -> None:
    span = A1_FRAME.width * BLOCKDEF_SPLIT_RATIO * 0.5
    boxes = [[x, 10000.0, x + 900.0, 11000.0] for x in (10000.0, 10000.0 + span)]
    clusters = build_clusters([_blockdef(boxes)], A1_FRAME, CONFIG)
    assert len(clusters) == 1


def test_a_blockdef_change_spread_over_the_sheet_splits_per_instance() -> None:
    """Brief Defaults for ambiguity: one cloud around the whole sheet says nothing."""
    boxes = [[x, 10000.0, x + 900.0, 11000.0] for x in (5000.0, 35000.0, 70000.0)]
    clusters = build_clusters([_blockdef(boxes)], A1_FRAME, CONFIG)
    assert len(clusters) == 3
    assert all(cluster.change_seqs == [1] for cluster in clusters)
    assert all(cluster.kind == KIND_BLOCKDEF for cluster in clusters)


# --------------------------------------------------------------------------- signature


def test_the_signature_survives_renumbering_but_not_a_different_membership() -> None:
    members = [
        change(1, [0.0, 0.0, 1.0, 1.0]),
        change(2, [0.0, 0.0, 1.0, 1.0]),
    ]
    renumbered = [
        change(7, [0.0, 0.0, 1.0, 1.0]),
        change(9, [0.0, 0.0, 1.0, 1.0]),
    ]
    renumbered[0].after_handle = members[0].after_handle
    renumbered[1].after_handle = members[1].after_handle
    assert cluster_signature(members) == cluster_signature(renumbered)
    assert cluster_signature(members) != cluster_signature(members[:1])
    assert len(cluster_signature(members)) == 16


# --------------------------------------------------------------------------- geometry


def test_the_cloud_rectangle_is_the_box_plus_the_margin() -> None:
    box = [10000.0, 10000.0, 11000.0, 10500.0]
    points = cloud_polyline(box, CONFIG, 1.0)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    margin = CONFIG.cloud.margin
    assert min(xs) == box[0] - margin
    assert min(ys) == box[1] - margin
    assert max(xs) == box[2] + margin
    assert max(ys) == box[3] + margin


def test_the_cloud_starts_at_the_lower_left_and_runs_counter_clockwise() -> None:
    box = [10000.0, 10000.0, 11000.0, 10500.0]
    points = cloud_polyline(box, CONFIG, 1.0)
    margin = CONFIG.cloud.margin
    assert points[0][:2] == (box[0] - margin, box[1] - margin)
    # Shoelace: positive area means counter-clockwise, which is what makes a
    # positive bulge arc outwards (contract §5).
    area = 0.0
    for index, (x, y, _bulge) in enumerate(points):
        nx, ny, _ = points[(index + 1) % len(points)]
        area += x * ny - nx * y
    assert area > 0


def test_every_cloud_vertex_carries_the_configured_bulge() -> None:
    points = cloud_polyline([0.0, 0.0, 1000.0, 500.0], CONFIG, 1.0)
    assert {point[2] for point in points} == {CONFIG.cloud.arc_bulge}


def test_each_side_is_divided_into_chords_of_at_most_the_arc_length() -> None:
    box = [0.0, 0.0, 1000.0, 500.0]
    points = cloud_polyline(box, CONFIG, 1.0)
    margin, arc = CONFIG.cloud.margin, CONFIG.cloud.arc
    width = (box[2] + margin) - (box[0] - margin)
    height = (box[3] + margin) - (box[1] - margin)
    expected = 2 * math.ceil(width / arc) + 2 * math.ceil(height / arc)
    assert len(points) == expected
    for index, (x, y, _bulge) in enumerate(points):
        nx, ny, _ = points[(index + 1) % len(points)]
        assert math.hypot(nx - x, ny - y) <= arc + 1e-6


def test_a_one_to_fifty_sheet_draws_everything_half_size() -> None:
    """Contract §5: ``scale_factor = scale_denominator / 100`` multiplies every length."""
    box = [0.0, 0.0, 1000.0, 500.0]
    full = badge_geometry(box, CONFIG, 1.0)
    half = badge_geometry(box, CONFIG, 0.5)
    assert half.side == pytest.approx(full.side / 2)
    assert half.text_height == pytest.approx(full.text_height / 2)

    full_points = cloud_polyline(box, CONFIG, 1.0)
    half_points = cloud_polyline(box, CONFIG, 0.5)
    assert min(p[0] for p in half_points) == box[0] - CONFIG.cloud.margin * 0.5
    assert len(half_points) > len(full_points)  # half-length chords, twice as many


def test_the_badge_is_an_equilateral_triangle_outside_the_cloud_corner() -> None:
    box = [10000.0, 10000.0, 11000.0, 10500.0]
    badge = badge_geometry(box, CONFIG, 1.0)
    margin, side = CONFIG.cloud.margin, CONFIG.cloud.badge_side

    assert badge.points[0] == (box[2] + margin, box[3] + margin)
    lengths = [
        math.hypot(
            badge.points[(i + 1) % 3][0] - badge.points[i][0],
            badge.points[(i + 1) % 3][1] - badge.points[i][1],
        )
        for i in range(3)
    ]
    assert lengths == pytest.approx([side, side, side], abs=1e-3)
    assert badge.points[2][1] > badge.points[0][1]  # apex up
    assert badge.center == pytest.approx(
        (
            sum(p[0] for p in badge.points) / 3,
            sum(p[1] for p in badge.points) / 3,
        ),
        abs=1e-3,
    )


def test_cloud_and_badge_coordinates_are_rounded_to_three_decimals() -> None:
    """Contract §8: three decimals is what makes the file byte-stable."""
    box = [10000.123456, 10000.987654, 11000.5, 10500.25]
    for x, y, _bulge in cloud_polyline(box, CONFIG, 1.0):
        assert x == round(x, 3)
        assert y == round(y, 3)
    for x, y in badge_geometry(box, CONFIG, 1.0).points:
        assert x == round(x, 3)
        assert y == round(y, 3)
