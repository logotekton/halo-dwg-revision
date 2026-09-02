"""F10 -- XREF: a host document attaches a grid+title-block document as an
external reference by a *relative* path, plus its own local content (columns
placed at the grid intersections). Two files, generated as a pair.

Not a single-``build()`` fixture like the others -- see :func:`build_pair`.
"""

from __future__ import annotations

import random

import ezdxf.xref

from fixtures_gen.base import BuildResult
from fixtures_gen.common import ensure_layers, new_doc

X_LABELS = ["X1", "X2", "X3"]
Y_LABELS = ["Y1", "Y2"]
SPACING = 6000.0
ORIGIN = (4000.0, 4000.0)
XREF_BLOCK_NAME = "F10_GRID"


def _make_grid_bubble_block(doc) -> None:
    blk = doc.blocks.new("GRID-BUBBLE")
    blk.add_circle((0, 0), 350, dxfattribs={"layer": "X-GRID"})
    blk.add_attdef(
        "LABEL", dxfattribs={"layer": "X-GRID", "height": 300, "insert": (0, -105), "halign": 1}
    )


def _build_grid_doc(version: str) -> tuple:
    doc = new_doc(version)
    ensure_layers(doc, ["X-GRID", "X-TITLE"])
    _make_grid_bubble_block(doc)
    msp = doc.modelspace()

    ox, oy = ORIGIN
    xs = [ox + i * SPACING for i in range(len(X_LABELS))]
    ys = [oy + j * SPACING for j in range(len(Y_LABELS))]
    lines: list[dict] = []
    for label, x in zip(X_LABELS, xs, strict=True):
        y0, y1 = ys[0] - 500, ys[-1] + 500
        msp.add_line((x, y0), (x, y1), dxfattribs={"layer": "X-GRID"})
        bubble = msp.add_blockref("GRID-BUBBLE", (x, y1 + 700), dxfattribs={"layer": "X-GRID"})
        bubble.add_auto_attribs({"LABEL": label})
        lines.append({"id": label, "axis": "X", "position": x})
    for label, y in zip(Y_LABELS, ys, strict=True):
        x0, x1 = xs[0] - 500, xs[-1] + 500
        msp.add_line((x0, y), (x1, y), dxfattribs={"layer": "X-GRID"})
        bubble = msp.add_blockref("GRID-BUBBLE", (x0 - 700, y), dxfattribs={"layer": "X-GRID"})
        bubble.add_auto_attribs({"LABEL": label})
        lines.append({"id": label, "axis": "Y", "position": y})

    blk = doc.blocks.new("X-TITLE")
    w, h = 841.0, 594.0
    blk.add_lwpolyline(
        [(0, 0), (w, 0), (w, h), (0, h)],
        format="xy",
        close=True,
        dxfattribs={"layer": "X-TITLE"},
    )
    blk.add_attdef("DWGNO", dxfattribs={"layer": "X-TITLE", "height": 7, "insert": (w - 210, 10)})
    blk.add_attdef("DWGNAME", dxfattribs={"layer": "X-TITLE", "height": 6, "insert": (w - 210, 20)})
    title_ins = msp.add_blockref(
        "X-TITLE", (0, 0), dxfattribs={"xscale": 100, "yscale": 100, "layer": "X-TITLE"}
    )
    title_attribs = {"DWGNO": "S-100", "DWGNAME": "기준 그리드 평면도"}
    title_ins.add_auto_attribs(title_attribs)

    extra = {"grid_lines": lines, "title_block": title_attribs, "grid_origin": list(ORIGIN)}
    return doc, extra, (xs, ys)


def build_pair(version: str, rng: random.Random) -> dict[str, BuildResult]:
    """Return {"grid": BuildResult, "host": BuildResult}. The host's XREF
    ``xref_path`` is the grid file's bare filename (relative, same directory).
    """
    grid_doc, grid_extra, (xs, ys) = _build_grid_doc(version)
    grid_filename = "F10_grid.dxf" if version == "R2018" else "F10_grid_r2000_cp949.dxf"

    host_doc = new_doc(version)
    ensure_layers(host_doc, ["S-COL", "A-TEXT"])
    host_msp = host_doc.modelspace()

    ins = ezdxf.xref.attach(
        host_doc,
        block_name=XREF_BLOCK_NAME,
        filename=grid_filename,
        insert=(0, 0, 0),
    )

    columns: list[dict] = []
    half = 300.0
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            tag = f"C{i * len(ys) + j + 1}"
            pts = [
                (x - half, y - half),
                (x + half, y - half),
                (x + half, y + half),
                (x - half, y + half),
            ]
            host_msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs={"layer": "S-COL"})
            host_msp.add_text(tag, dxfattribs={"layer": "A-TEXT", "height": 200}).set_placement(
                (x, y + half + 80)
            )
            columns.append({"tag": tag, "center": [x, y]})

    host_extra = {
        "xref": {
            "block_name": XREF_BLOCK_NAME,
            "path": grid_filename,
            "path_kind": "relative",
            "insert": [0.0, 0.0, 0.0],
            "insert_entity_handle": ins.dxf.handle,
        },
        "columns": columns,
    }

    return {
        "grid": BuildResult(doc=grid_doc, extra=grid_extra),
        "host": BuildResult(doc=host_doc, extra=host_extra),
    }
