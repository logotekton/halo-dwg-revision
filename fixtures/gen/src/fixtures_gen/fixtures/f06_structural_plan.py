"""F06 -- structural plan: column grid X1-X4/Y1-Y3 (8400/7200 spacing), grid
bubbles, 12 columns (LWPOLYLINE 600x600 + solid-fill HATCH + C1/C2 tag TEXT),
beam centerlines (G1/B1 tags), a slab tag ("S1 T=150"), and an X-TITLE title
block (drawing number S-101, name "2층 구조평면도", scale 1/100) placed in
model space at 1:100 (the block is authored in paper mm, 841x594 = A1, and
inserted with a uniform scale factor of 100).

This module is reused (with a tile offset) by F11/F12 for the large fixtures.
"""

from __future__ import annotations

import random

from fixtures_gen.base import BuildResult
from fixtures_gen.common import ensure_layers, new_doc

X_LABELS = ["X1", "X2", "X3", "X4"]
Y_LABELS = ["Y1", "Y2", "Y3"]
X_SPACING = 8400.0
Y_SPACING = 7200.0
GRID_ORIGIN = (8000.0, 8000.0)
COLUMN_SIZE = 600.0
BUBBLE_RADIUS = 400.0
BUBBLE_OFFSET = 700.0


def _make_grid_bubble_block(doc) -> None:
    if "GRID-BUBBLE" in doc.blocks:
        return
    blk = doc.blocks.new("GRID-BUBBLE")
    blk.add_circle((0, 0), BUBBLE_RADIUS, dxfattribs={"layer": "X-GRID"})
    blk.add_attdef(
        "LABEL",
        dxfattribs={
            "layer": "X-GRID",
            "height": BUBBLE_RADIUS * 0.9,
            "insert": (0, -BUBBLE_RADIUS * 0.35),
            "halign": 1,  # center
        },
    )


def _make_title_block(doc) -> None:
    if "X-TITLE" in doc.blocks:
        return
    blk = doc.blocks.new("X-TITLE")
    # A1 paper size in mm, authored at 1:1 inside the block; inserted at
    # xscale=yscale=100 gives the correct 1:100 placement in model space.
    w, h = 841.0, 594.0
    blk.add_lwpolyline(
        [(0, 0), (w, 0), (w, h), (0, h)],
        format="xy",
        close=True,
        dxfattribs={"layer": "X-TITLE"},
    )
    strip_h = 40.0
    blk.add_lwpolyline(
        [(w - 220, 0), (w - 220, strip_h), (w, strip_h)],
        format="xy",
        dxfattribs={"layer": "X-TITLE"},
    )
    blk.add_attdef(
        "DWGNO",
        dxfattribs={"layer": "X-TITLE", "height": 7, "insert": (w - 210, 26)},
    )
    blk.add_attdef(
        "DWGNAME",
        dxfattribs={"layer": "X-TITLE", "height": 6, "insert": (w - 210, 15)},
    )
    blk.add_attdef(
        "SCALE",
        dxfattribs={"layer": "X-TITLE", "height": 5, "insert": (w - 210, 5)},
    )


def build(
    version: str,
    rng: random.Random,
    tile_offset: tuple[float, float] = (0.0, 0.0),
    tag_suffix: str = "",
    build_title: bool = True,
    doc=None,
) -> BuildResult:
    """Build one structural-plan tile.

    ``tile_offset``/``tag_suffix``/``build_title``/``doc`` are used by F11/F12
    to stamp many tiles into a single shared document without name clashes.
    """
    owns_doc = doc is None
    if owns_doc:
        doc = new_doc(version)
    ensure_layers(doc, ["S-COL", "S-BEAM", "S-SLAB", "A-TEXT", "X-GRID", "X-TITLE"])
    _make_grid_bubble_block(doc)
    if build_title:
        _make_title_block(doc)
    msp = doc.modelspace()

    ox, oy = GRID_ORIGIN
    ox += tile_offset[0]
    oy += tile_offset[1]
    x_positions = [ox + i * X_SPACING for i in range(len(X_LABELS))]
    y_positions = [oy + j * Y_SPACING for j in range(len(Y_LABELS))]

    grid_lines: list[dict] = []
    for label, x in zip(X_LABELS, x_positions, strict=True):
        y0, y1 = y_positions[0] - 300, y_positions[-1] + 300
        msp.add_line((x, y0), (x, y1), dxfattribs={"layer": "X-GRID"})
        bubble = msp.add_blockref(
            "GRID-BUBBLE", (x, y1 + BUBBLE_OFFSET), dxfattribs={"layer": "X-GRID"}
        )
        bubble.add_auto_attribs({"LABEL": label + tag_suffix})
        grid_lines.append(
            {"id": label + tag_suffix, "axis": "X", "position": x, "start": [x, y0], "end": [x, y1]}
        )

    for label, y in zip(Y_LABELS, y_positions, strict=True):
        x0, x1 = x_positions[0] - 300, x_positions[-1] + 300
        msp.add_line((x0, y), (x1, y), dxfattribs={"layer": "X-GRID"})
        bubble = msp.add_blockref(
            "GRID-BUBBLE", (x0 - BUBBLE_OFFSET, y), dxfattribs={"layer": "X-GRID"}
        )
        bubble.add_auto_attribs({"LABEL": label + tag_suffix})
        grid_lines.append(
            {"id": label + tag_suffix, "axis": "Y", "position": y, "start": [x0, y], "end": [x1, y]}
        )

    columns: list[dict] = []
    half = COLUMN_SIZE / 2
    last_i, last_j = len(X_LABELS) - 1, len(Y_LABELS) - 1
    corner_set = {(0, 0), (0, last_j), (last_i, 0), (last_i, last_j)}
    for i, x in enumerate(x_positions):
        for j, y in enumerate(y_positions):
            tag = ("C1" if (i, j) in corner_set else "C2") + tag_suffix
            pts = [
                (x - half, y - half),
                (x + half, y - half),
                (x + half, y + half),
                (x - half, y + half),
            ]
            msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs={"layer": "S-COL"})
            hatch = msp.add_hatch(dxfattribs={"layer": "S-COL", "color": 252})
            hatch.paths.add_polyline_path(pts, is_closed=True, flags=1)
            hatch.set_solid_fill(color=252)
            msp.add_text(tag, dxfattribs={"layer": "A-TEXT", "height": 200}).set_placement(
                (x, y + half + 80)
            )
            grid_ref = [X_LABELS[i] + tag_suffix, Y_LABELS[j] + tag_suffix]
            columns.append(
                {
                    "tag": tag,
                    "center": [x, y],
                    "size": [COLUMN_SIZE, COLUMN_SIZE],
                    "grid": grid_ref,
                }
            )

    beams: list[dict] = []
    for j, y in enumerate(y_positions):
        for i in range(len(x_positions) - 1):
            x0, x1 = x_positions[i], x_positions[i + 1]
            tag = f"G{j + 1}{tag_suffix}"
            msp.add_line((x0, y), (x1, y), dxfattribs={"layer": "S-BEAM", "linetype": "DASHED"})
            mx = (x0 + x1) / 2
            msp.add_text(tag, dxfattribs={"layer": "A-TEXT", "height": 150}).set_placement(
                (mx, y + 120)
            )
            beams.append({"tag": tag, "from": [x0, y], "to": [x1, y], "kind": "girder"})

    for i, x in enumerate(x_positions):
        for j in range(len(y_positions) - 1):
            y0, y1 = y_positions[j], y_positions[j + 1]
            tag = f"B{i + 1}{tag_suffix}"
            msp.add_line((x, y0), (x, y1), dxfattribs={"layer": "S-BEAM", "linetype": "DASHED"})
            my = (y0 + y1) / 2
            msp.add_text(tag, dxfattribs={"layer": "A-TEXT", "height": 150}).set_placement(
                (x + 120, my)
            )
            beams.append({"tag": tag, "from": [x, y0], "to": [x, y1], "kind": "beam"})

    slab_center = [
        (x_positions[0] + x_positions[-1]) / 2,
        (y_positions[0] + y_positions[-1]) / 2,
    ]
    slab_tag = "S1 T=150" + (f" ({tag_suffix})" if tag_suffix else "")
    msp.add_text(slab_tag, dxfattribs={"layer": "A-TEXT", "height": 250}).set_placement(slab_center)

    title_attribs = None
    if build_title:
        title_ins = msp.add_blockref(
            "X-TITLE", (0, 0), dxfattribs={"xscale": 100, "yscale": 100, "layer": "X-TITLE"}
        )
        title_attribs = {"DWGNO": "S-101", "DWGNAME": "2층 구조평면도", "SCALE": "1/100"}
        title_ins.add_auto_attribs(title_attribs)

    extra = {
        "grid": {"x_spacing": X_SPACING, "y_spacing": Y_SPACING, "lines": grid_lines},
        "columns": columns,
        "beams": beams,
        "slab": {"tag": "S1", "thickness_mm": 150, "location": slab_center},
        "title_block": title_attribs,
    }
    return BuildResult(doc=doc, extra=extra)
