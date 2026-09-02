"""F02 -- block definitions, INSERTs with rotation/scale, ATTRIB, one nested block.

Blocks: DOOR_900 (door + swing arc), WIN_1800 (window), COL_600 (600x600
column), COL_PAIR (nested: two INSERTs of COL_600 -- the "nested block").
30 top-level INSERTs in modelspace, each with ATTRIB TAG + SIZE.
"""

from __future__ import annotations

import random

from fixtures_gen.base import BuildResult
from fixtures_gen.common import ensure_layers, new_doc

DOOR_TAGS = [f"AD{i + 1}" for i in range(10)]
WIN_TAGS = [f"AW{i + 1}" for i in range(10)]
COL_TAGS = [f"C{i + 1}" for i in range(9)]


def _make_door_block(doc) -> None:
    blk = doc.blocks.new("DOOR_900")
    blk.add_line((0, 0), (0, 900), dxfattribs={"layer": "A-DOOR"})
    blk.add_arc(
        center=(0, 0), radius=900, start_angle=0, end_angle=90, dxfattribs={"layer": "A-DOOR"}
    )
    blk.add_line((0, 0), (900, 0), dxfattribs={"layer": "A-DOOR", "linetype": "DASHED"})
    blk.add_attdef("TAG", dxfattribs={"layer": "A-TEXT", "height": 80, "insert": (200, -150)})
    blk.add_attdef("SIZE", dxfattribs={"layer": "A-TEXT", "height": 60, "insert": (200, -280)})


def _make_window_block(doc) -> None:
    blk = doc.blocks.new("WIN_1800")
    blk.add_lwpolyline(
        [(0, 0), (1800, 0), (1800, 200), (0, 200)],
        format="xy",
        close=True,
        dxfattribs={"layer": "A-WIND"},
    )
    blk.add_line((0, 100), (1800, 100), dxfattribs={"layer": "A-WIND"})
    blk.add_attdef("TAG", dxfattribs={"layer": "A-TEXT", "height": 80, "insert": (200, -150)})
    blk.add_attdef("SIZE", dxfattribs={"layer": "A-TEXT", "height": 60, "insert": (200, -280)})


def _make_column_block(doc) -> None:
    blk = doc.blocks.new("COL_600")
    blk.add_lwpolyline(
        [(0, 0), (600, 0), (600, 600), (0, 600)],
        format="xy",
        close=True,
        dxfattribs={"layer": "S-COL"},
    )
    blk.add_attdef("TAG", dxfattribs={"layer": "A-TEXT", "height": 100, "insert": (150, 250)})
    blk.add_attdef("SIZE", dxfattribs={"layer": "A-TEXT", "height": 60, "insert": (100, 100)})


def _make_nested_block(doc) -> None:
    """COL_PAIR: a block whose definition contains two INSERTs of COL_600."""
    blk = doc.blocks.new("COL_PAIR")
    blk.add_blockref("COL_600", (0, 0))
    blk.add_blockref("COL_600", (1200, 0))
    blk.add_attdef("TAG", dxfattribs={"layer": "A-TEXT", "height": 100, "insert": (150, 850)})
    blk.add_attdef("SIZE", dxfattribs={"layer": "A-TEXT", "height": 60, "insert": (150, 700)})


def build(version: str, rng: random.Random) -> BuildResult:
    doc = new_doc(version)
    ensure_layers(doc, ["A-DOOR", "A-WIND", "S-COL", "A-TEXT"])

    _make_door_block(doc)
    _make_window_block(doc)
    _make_column_block(doc)
    _make_nested_block(doc)

    msp = doc.modelspace()
    placements: list[dict] = []

    cols_per_row = 6
    spacing = 2400.0

    def grid_point(index: int) -> tuple[float, float]:
        row, col = divmod(index, cols_per_row)
        return col * spacing, -row * spacing

    index = 0
    for tag in DOOR_TAGS:
        x, y = grid_point(index)
        rot = rng.uniform(0, 360)
        scale = rng.uniform(0.8, 1.3)
        ins = msp.add_blockref(
            "DOOR_900",
            (x, y),
            dxfattribs={"rotation": rot, "xscale": scale, "yscale": scale, "layer": "A-DOOR"},
        )
        size = "900x2100"
        ins.add_auto_attribs({"TAG": tag, "SIZE": size})
        placements.append(
            {"block": "DOOR_900", "tag": tag, "insert": [x, y], "rotation": rot, "scale": scale}
        )
        index += 1

    for tag in WIN_TAGS:
        x, y = grid_point(index)
        rot = rng.uniform(0, 360)
        scale = rng.uniform(0.8, 1.3)
        ins = msp.add_blockref(
            "WIN_1800",
            (x, y),
            dxfattribs={"rotation": rot, "xscale": scale, "yscale": scale, "layer": "A-WIND"},
        )
        size = "1800x1200"
        ins.add_auto_attribs({"TAG": tag, "SIZE": size})
        placements.append(
            {"block": "WIN_1800", "tag": tag, "insert": [x, y], "rotation": rot, "scale": scale}
        )
        index += 1

    for tag in COL_TAGS:
        x, y = grid_point(index)
        rot = rng.choice([0.0, 90.0, 180.0, 270.0])
        scale = 1.0
        ins = msp.add_blockref(
            "COL_600",
            (x, y),
            dxfattribs={"rotation": rot, "xscale": scale, "yscale": scale, "layer": "S-COL"},
        )
        size = "600x600"
        ins.add_auto_attribs({"TAG": tag, "SIZE": size})
        placements.append(
            {"block": "COL_600", "tag": tag, "insert": [x, y], "rotation": rot, "scale": scale}
        )
        index += 1

    # the 30th INSERT: the nested block COL_PAIR
    x, y = grid_point(index)
    rot = 0.0
    scale = 1.0
    ins = msp.add_blockref(
        "COL_PAIR", (x, y), dxfattribs={"rotation": rot, "xscale": scale, "yscale": scale}
    )
    ins.add_auto_attribs({"TAG": "C-PAIR1", "SIZE": "600x600x2"})
    placements.append(
        {"block": "COL_PAIR", "tag": "C-PAIR1", "insert": [x, y], "rotation": rot, "scale": scale}
    )
    index += 1

    assert index == 30, index

    extra = {
        "blocks": ["DOOR_900", "WIN_1800", "COL_600", "COL_PAIR"],
        "nested_block": "COL_PAIR",
        "nested_block_contains": ["COL_600", "COL_600"],
        "insert_count": 30,
        "attribs_per_insert": ["TAG", "SIZE"],
        "placements": placements,
    }
    return BuildResult(doc=doc, extra=extra)
