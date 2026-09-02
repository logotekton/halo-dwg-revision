"""F09 -- a 2x3 room layout with double-line walls (200mm), 6 door openings
(with an arc-swing door block), 4 window openings, room-name TEXT, and two
*intentional* 150mm wall gaps (drafting defects, not door/window openings)
whose positions are recorded in truth for gap-recovery testing.
"""

from __future__ import annotations

import math
import random

from fixtures_gen.base import BuildResult
from fixtures_gen.common import ensure_layers, new_doc

WALL_THICKNESS = 200.0
GAP_WIDTH = 150.0
DOOR_WIDTH = 900.0
WINDOW_WIDTH = 1200.0

COL_X = [0.0, 3600.0, 7200.0]
ROW_Y = [0.0, 3000.0, 6000.0, 9000.0]

# room grid: (col_index, row_index) -> name  (row 0 = bottom)
ROOMS = {
    (0, 0): "거실",
    (1, 0): "침실1",
    (0, 1): "주방",
    (1, 1): "욕실",
    (0, 2): "침실2",
    (1, 2): "다용도실",
}


def _make_door_block(doc) -> None:
    blk = doc.blocks.new("F09-DOOR")
    blk.add_line((0, 0), (0, DOOR_WIDTH), dxfattribs={"layer": "A-DOOR"})
    blk.add_arc(
        center=(0, 0),
        radius=DOOR_WIDTH,
        start_angle=0,
        end_angle=90,
        dxfattribs={"layer": "A-DOOR"},
    )


def _make_window_block(doc) -> None:
    blk = doc.blocks.new("F09-WIN")
    half = WALL_THICKNESS / 2
    blk.add_lwpolyline(
        [(0, -half), (WINDOW_WIDTH, -half), (WINDOW_WIDTH, half), (0, half)],
        format="xy",
        close=True,
        dxfattribs={"layer": "A-WIND"},
    )
    blk.add_line((0, 0), (WINDOW_WIDTH, 0), dxfattribs={"layer": "A-WIND"})


def _draw_wall(msp, p1, p2, breaks: list[tuple[float, float]], layer: str) -> None:
    """``breaks``: list of (center_distance_from_p1, width) intervals with no
    wall line (door/window openings and intentional gaps alike).
    """
    x1, y1 = p1
    x2, y2 = p2
    length = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    # perpendicular unit vector
    px, py = -uy, ux
    half = WALL_THICKNESS / 2

    for side in (-1, 1):
        ox, oy = px * half * side, py * half * side
        segments = [(0.0, length)]
        for center, width in breaks:
            b0, b1 = center - width / 2, center + width / 2
            new_segments = []
            for s0, s1 in segments:
                if b1 <= s0 or b0 >= s1:
                    new_segments.append((s0, s1))
                    continue
                if b0 > s0:
                    new_segments.append((s0, b0))
                if b1 < s1:
                    new_segments.append((b1, s1))
            segments = new_segments
        for s0, s1 in segments:
            if s1 - s0 < 1e-6:
                continue
            sx1, sy1 = x1 + ux * s0 + ox, y1 + uy * s0 + oy
            sx2, sy2 = x1 + ux * s1 + ox, y1 + uy * s1 + oy
            msp.add_line((sx1, sy1), (sx2, sy2), dxfattribs={"layer": layer})


def build(version: str, rng: random.Random) -> BuildResult:
    doc = new_doc(version)
    ensure_layers(doc, ["A-WALL", "A-DOOR", "A-WIND", "A-TEXT"])
    _make_door_block(doc)
    _make_window_block(doc)
    msp = doc.modelspace()

    # openings keyed by wall id -> list of (center, width, kind, tag)
    openings: dict[str, list[dict]] = {
        "V-3600": [
            {"center": 1500.0, "width": DOOR_WIDTH, "kind": "door", "tag": "AD1"},
            {"center": 4500.0, "width": GAP_WIDTH, "kind": "gap", "tag": "GAP1"},
            {"center": 7500.0, "width": GAP_WIDTH, "kind": "gap", "tag": "GAP2"},
        ],
        "H-3000": [
            {"center": 1800.0, "width": DOOR_WIDTH, "kind": "door", "tag": "AD2"},
            {"center": 5400.0, "width": DOOR_WIDTH, "kind": "door", "tag": "AD3"},
        ],
        "H-6000": [
            {"center": 1800.0, "width": DOOR_WIDTH, "kind": "door", "tag": "AD4"},
            {"center": 5400.0, "width": DOOR_WIDTH, "kind": "door", "tag": "AD5"},
        ],
        "H-0": [
            {"center": 1800.0, "width": DOOR_WIDTH, "kind": "door", "tag": "AD6"},
        ],
        "H-9000": [
            {"center": 1800.0, "width": WINDOW_WIDTH, "kind": "window", "tag": "AW1"},
            {"center": 5400.0, "width": WINDOW_WIDTH, "kind": "window", "tag": "AW2"},
        ],
        "V-7200": [
            {"center": 1500.0, "width": WINDOW_WIDTH, "kind": "window", "tag": "AW3"},
        ],
        "V-0": [
            {"center": 1500.0, "width": WINDOW_WIDTH, "kind": "window", "tag": "AW4"},
        ],
    }

    walls = {
        "H-0": ((0.0, 0.0), (7200.0, 0.0)),
        "H-3000": ((0.0, 3000.0), (7200.0, 3000.0)),
        "H-6000": ((0.0, 6000.0), (7200.0, 6000.0)),
        "H-9000": ((0.0, 9000.0), (7200.0, 9000.0)),
        "V-0": ((0.0, 0.0), (0.0, 9000.0)),
        "V-3600": ((3600.0, 0.0), (3600.0, 9000.0)),
        "V-7200": ((7200.0, 0.0), (7200.0, 9000.0)),
    }

    gaps_truth: list[dict] = []
    doors_truth: list[dict] = []
    windows_truth: list[dict] = []

    for wall_id, (p1, p2) in walls.items():
        breaks = [(o["center"], o["width"]) for o in openings.get(wall_id, [])]
        _draw_wall(msp, p1, p2, breaks, layer="A-WALL")

        x1, y1 = p1
        x2, y2 = p2
        length = math.hypot(x2 - x1, y2 - y1)
        ux, uy = (x2 - x1) / length, (y2 - y1) / length
        is_vertical = abs(x2 - x1) < 1e-6
        rotation = 90.0 if is_vertical else 0.0

        for o in openings.get(wall_id, []):
            cx = x1 + ux * o["center"]
            cy = y1 + uy * o["center"]
            if o["kind"] == "door":
                insert_x = cx - (DOOR_WIDTH / 2 if not is_vertical else 0)
                insert_y = cy - (DOOR_WIDTH / 2 if is_vertical else 0)
                msp.add_blockref(
                    "F09-DOOR",
                    (insert_x, insert_y),
                    dxfattribs={"rotation": rotation, "layer": "A-DOOR"},
                )
                doors_truth.append(
                    {"tag": o["tag"], "wall": wall_id, "center": [cx, cy], "width": DOOR_WIDTH}
                )
            elif o["kind"] == "window":
                insert_x = cx - (WINDOW_WIDTH / 2 if not is_vertical else 0)
                insert_y = cy - (WINDOW_WIDTH / 2 if is_vertical else 0)
                msp.add_blockref(
                    "F09-WIN",
                    (insert_x, insert_y),
                    dxfattribs={"rotation": rotation, "layer": "A-WIND"},
                )
                windows_truth.append(
                    {"tag": o["tag"], "wall": wall_id, "center": [cx, cy], "width": WINDOW_WIDTH}
                )
            elif o["kind"] == "gap":
                gaps_truth.append(
                    {
                        "tag": o["tag"],
                        "wall": wall_id,
                        "center": [cx, cy],
                        "width": GAP_WIDTH,
                    }
                )

    room_names: list[dict] = []
    for (ci, ri), name in ROOMS.items():
        cx = (COL_X[ci] + COL_X[ci + 1]) / 2
        cy = (ROW_Y[ri] + ROW_Y[ri + 1]) / 2
        msp.add_text(name, dxfattribs={"layer": "A-TEXT", "height": 200}).set_placement((cx, cy))
        room_names.append({"name": name, "center": [cx, cy]})

    extra = {
        "wall_thickness_mm": WALL_THICKNESS,
        "rooms": room_names,
        "doors": doors_truth,
        "windows": windows_truth,
        "gaps": gaps_truth,
        "gap_width_mm": GAP_WIDTH,
    }
    return BuildResult(doc=doc, extra=extra)
