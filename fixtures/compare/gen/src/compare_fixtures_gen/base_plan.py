"""Base floor plan shared by every synthetic revision-pair scenario (R1-07).

One A1 sheet at 1:100 (frame = 841x594mm x 100 = 84,100 x 59,400mm, mm world
coordinates, docs/contracts/r1.md SS5) with a ``TITLEBLOCK`` block (ATTRIBs
``DWG_NO``/``TITLE``/``SCALE``/``DATE``/``PROJECT``) bottom-right, a column
grid X1-X5/Y1-Y4 with bubble blocks, double-line walls forming 6 rooms, 6
``DOOR_900`` instances (ATTRIB ``TAG``), 4 ``WIN_1800`` instances, 12 columns
(outline + SOLID hatch), 6 room-name TEXTs, a legend MTEXT using format codes
(``\\P``, ``{\\fArial;}``), 4 linear DIMENSIONs, 2 ANSI31 HATCHes and 1
LEADER -- see docs/briefs/R1-07.md Goal 2.

Determinism strategy (mirrors ``fixtures/gen/src/fixtures_gen/common.py``,
copied rather than imported per the brief's Inputs note):

* ``ezdxf.options.write_fixed_meta_data_for_testing = True`` pins
  ``$TDCREATE``/``$TDUPDATE``/``$FINGERPRINTGUID``/``$VERSIONGUID`` instead of
  writing the current time / a random GUID on every ``saveas()``.
* No randomness anywhere -- every scenario plants a fixed, literal edit.
* Every builder function creates entities in a fixed order over plain lists
  (never a ``set`` or an unordered ``dict``), so ezdxf's incrementing handle
  counter assigns the same handle to the same entity every run, and
  before/after documents built by the same call sequence get identical
  handles for identical content (Definition of done "핸들 안정").

``build_base_plan()`` is a fixed pipeline of independent *steps* (grid,
walls, columns, doors, windows, room texts, legend, dimensions, hatches,
leader -- see :data:`DEFAULT_STEP_ORDER`). Each step reads only module-level
constants, never another step's output, so ``reversed_layout=True`` (used by
scenario S12) can run the exact same steps in reverse order -- and the
layer/block-definition table in reverse too -- to renumber every handle in
the drawing while producing byte-for-byte the same geometry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import ezdxf
from ezdxf.document import Drawing

# Must be set before any Drawing is created/saved (fixtures/README.md Decisions #1).
ezdxf.options.write_fixed_meta_data_for_testing = True

INSUNITS_MM = 4

#: A1 paper size in mm. Frame in model space = PAPER_W/H * scale_denominator.
PAPER_W = 841.0
PAPER_H = 594.0

LAYER_DEFS: dict[str, dict[str, Any]] = {
    "A-WALL": {"color": 7, "linetype": "CONTINUOUS"},
    "A-DOOR": {"color": 4, "linetype": "CONTINUOUS"},
    "A-WIND": {"color": 6, "linetype": "CONTINUOUS"},
    "A-COL": {"color": 1, "linetype": "CONTINUOUS"},
    "A-GRID": {"color": 8, "linetype": "CENTER"},
    "A-TEXT": {"color": 7, "linetype": "CONTINUOUS"},
    "A-DIM": {"color": 3, "linetype": "CONTINUOUS"},
    "A-HATCH": {"color": 2, "linetype": "CONTINUOUS"},
    "TITLE": {"color": 7, "linetype": "CONTINUOUS"},
}
#: >= 8 layers per the brief Goal 2. Order matters for S12 (reversed_layout).
LAYER_ORDER = list(LAYER_DEFS.keys())

# --- interior layout constants (baseline "design units": world mm at
# scale_denominator == 100, i.e. content_scale == 1.0; see _Ctx.pt) ---------

GRID_ORIGIN = (10000.0, 8000.0)
X_SPACING = 8000.0
Y_SPACING = 6000.0
X_LABELS = ["X1", "X2", "X3", "X4", "X5"]
Y_LABELS = ["Y1", "Y2", "Y3", "Y4"]

COLUMN_SIZE = 500.0
#: Only 3x4 = 12 of the 5x4 = 20 grid intersections carry a column (X1/X3/X5).
COLUMN_GRID_I = (0, 2, 4)
COLUMN_GRID_J = (0, 1, 2, 3)

WALL_X0, WALL_Y0, WALL_X1, WALL_Y1 = 8500.0, 6500.0, 43500.0, 27500.0
WALL_THK = 200.0
PART_V1_X, PART_V2_X = 20500.0, 31500.0
PART_H_Y = 17000.0

ROOM_NAMES = ["거실", "주방", "식당", "침실1", "침실2", "욕실"]
ROOM_CENTERS = [
    ((WALL_X0 + PART_V1_X) / 2.0, (WALL_Y0 + PART_H_Y) / 2.0),
    ((PART_V1_X + PART_V2_X) / 2.0, (WALL_Y0 + PART_H_Y) / 2.0),
    ((PART_V2_X + WALL_X1) / 2.0, (WALL_Y0 + PART_H_Y) / 2.0),
    ((WALL_X0 + PART_V1_X) / 2.0, (PART_H_Y + WALL_Y1) / 2.0),
    ((PART_V1_X + PART_V2_X) / 2.0, (PART_H_Y + WALL_Y1) / 2.0),
    ((PART_V2_X + WALL_X1) / 2.0, (PART_H_Y + WALL_Y1) / 2.0),
]

DOOR_PANEL_LEN = 900.0
#: (tag, center_x, center_y) -- all on horizontal walls so rotation stays 0.
DOOR_SPECS = [
    ("D1", 14500.0, PART_H_Y),
    ("D2", 26000.0, PART_H_Y),
    ("D3", 37500.0, PART_H_Y),
    ("D4", 14500.0, WALL_Y1),
    ("D5", 26000.0, WALL_Y1),
    ("D6", 14500.0, WALL_Y0),
]
WINDOW_WIDTH = 1800.0
WINDOW_SPECS = [
    (10000.0, WALL_Y1),
    (35000.0, WALL_Y1),
    (10000.0, WALL_Y0),
    (35000.0, WALL_Y0),
]

LEGEND_LOCAL = (46000.0, 20000.0)
LEGEND_WIDTH = 18000.0
LEGEND_CHAR_HEIGHT = 300.0
LEGEND_TEXT = (
    r"범례\P{\fArial;}A-WALL : 벽체\PA-DOOR : 문\PA-WIND : 창호"
)

#: (x0, y0, x1, y1) in local units, two ANSI31 fills below the building.
HATCH_SPECS = [
    (8500.0, 2000.0, 20000.0, 4500.0),
    (23500.0, 2000.0, 35000.0, 4500.0),
]

LEADER_LOCAL = [(44500.0, 9000.0), (46000.0, 9800.0), (46000.0, 10800.0)]

TB_W, TB_H = 150.0, 40.0


def round3(x: float) -> float:
    r = round(float(x), 3)
    return 0.0 if r == 0 else r


def frame_bbox(origin: tuple[float, float], scale_denom: float) -> list[float]:
    """Frame outline bbox for a sheet at ``origin`` with ``scale_denom`` (no
    build required -- pure geometry, used by scenarios that need a frame's
    bbox for a sheet they are not (re)building, e.g. S14's removed/added
    sides)."""
    ox, oy = origin
    fw = PAPER_W * scale_denom
    fh = PAPER_H * scale_denom
    return [round3(ox), round3(oy), round3(ox + fw), round3(oy + fh)]


def default_clean_regions(origin: tuple[float, float], scale_denom: float) -> list[list[float]]:
    """Two boxes guaranteed empty of every entity the base plan ever draws:
    a strip above the building/grid/dimensions, and a strip left of it. Valid
    for any ``origin``/``scale_denom`` since every interior coordinate is
    ``origin + local * (scale_denom/100)`` (see ``_Ctx.pt``)."""
    cs = float(scale_denom) / 100.0
    ox, oy = origin
    fw = PAPER_W * scale_denom
    fh = PAPER_H * scale_denom
    top = [round3(ox), round3(oy + 32000.0 * cs), round3(ox + fw), round3(oy + fh)]
    left = [round3(ox), round3(oy), round3(ox + 8000.0 * cs), round3(oy + fh)]
    return [top, left]


def new_doc() -> Drawing:
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = INSUNITS_MM
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LUNITS"] = 2
    doc.header["$LUPREC"] = 2
    return doc


def ensure_layers(doc: Drawing, names) -> None:
    for name in names:
        if name in doc.layers:
            continue
        d = LAYER_DEFS.get(name, {"color": 7, "linetype": "CONTINUOUS"})
        doc.layers.add(name=name, color=d["color"], linetype=d["linetype"])


def _own_attribs_by_insert(doc: Drawing) -> None:
    """AutoCAD writes an ATTRIB's owner (group 330) as its INSERT; ezdxf
    writes the layout block record instead. Match production drawings (see
    ``fixtures/gen/src/fixtures_gen/common.py`` for the same fix)."""
    for layout in doc.layouts:
        for insert in layout.query("INSERT"):
            for attrib in insert.attribs:
                attrib.dxf.owner = insert.dxf.handle


def save(doc: Drawing, path: Path) -> None:
    _own_attribs_by_insert(doc)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(path))


def _grid_positions() -> tuple[list[float], list[float]]:
    ox_l, oy_l = GRID_ORIGIN
    xs = [ox_l + i * X_SPACING for i in range(len(X_LABELS))]
    ys = [oy_l + j * Y_SPACING for j in range(len(Y_LABELS))]
    return xs, ys


# --- block definitions (each guarded so a shared multi-sheet doc, S13/S14,
# only creates them once) ---------------------------------------------------


def _ensure_door_block(doc: Drawing) -> None:
    if "DOOR_900" in doc.blocks:
        return
    blk = doc.blocks.new("DOOR_900")
    blk.add_line((0.0, 0.0), (DOOR_PANEL_LEN, 0.0), dxfattribs={"layer": "A-DOOR"})
    blk.add_arc((0.0, 0.0), DOOR_PANEL_LEN, 0, 90, dxfattribs={"layer": "A-DOOR"})
    blk.add_attdef(
        "TAG",
        insert=(DOOR_PANEL_LEN / 2.0, DOOR_PANEL_LEN + 60.0),
        dxfattribs={"layer": "A-DOOR", "height": 150.0, "halign": 1},
    )


def door_panel_line(doc: Drawing):
    """The LINE inside ``DOOR_900`` whose length S11 changes."""
    blk = doc.blocks.get("DOOR_900")
    for e in blk:
        if e.dxftype() == "LINE":
            return e
    raise RuntimeError("DOOR_900 block has no panel LINE")


def _ensure_window_block(doc: Drawing) -> None:
    if "WIN_1800" in doc.blocks:
        return
    blk = doc.blocks.new("WIN_1800")
    blk.add_line((0.0, 0.0), (WINDOW_WIDTH, 0.0), dxfattribs={"layer": "A-WIND"})
    blk.add_line((0.0, 60.0), (WINDOW_WIDTH, 60.0), dxfattribs={"layer": "A-WIND"})


def _ensure_grid_bubble_block(doc: Drawing) -> None:
    if "GRID_BUBBLE" in doc.blocks:
        return
    blk = doc.blocks.new("GRID_BUBBLE")
    r = 400.0
    blk.add_circle((0.0, 0.0), r, dxfattribs={"layer": "A-GRID"})
    blk.add_attdef(
        "LABEL",
        insert=(0.0, -r * 0.35),
        dxfattribs={"layer": "A-GRID", "height": r * 0.9, "halign": 1},
    )


def _ensure_titleblock(doc: Drawing) -> None:
    if "TITLEBLOCK" in doc.blocks:
        return
    blk = doc.blocks.new("TITLEBLOCK")
    blk.add_lwpolyline(
        [(0.0, 0.0), (TB_W, 0.0), (TB_W, TB_H), (0.0, TB_H)],
        format="xy",
        close=True,
        dxfattribs={"layer": "TITLE"},
    )
    blk.add_line((0.0, TB_H * 0.55), (TB_W, TB_H * 0.55), dxfattribs={"layer": "TITLE"})
    # 5 ATTRIBs: DWG_NO, TITLE, SCALE, DATE, PROJECT (frames.yaml tag lists).
    blk.add_attdef("DWG_NO", insert=(4.0, 8.0), dxfattribs={"layer": "TITLE", "height": 5.0})
    blk.add_attdef("TITLE", insert=(4.0, TB_H - 16.0), dxfattribs={"layer": "TITLE", "height": 6.0})
    blk.add_attdef("SCALE", insert=(60.0, 8.0), dxfattribs={"layer": "TITLE", "height": 5.0})
    blk.add_attdef("DATE", insert=(100.0, 8.0), dxfattribs={"layer": "TITLE", "height": 5.0})
    blk.add_attdef("PROJECT", insert=(4.0, TB_H - 8.0), dxfattribs={"layer": "TITLE", "height": 5.0})


BLOCK_BUILDERS: list[Callable[[Drawing], None]] = [
    _ensure_door_block,
    _ensure_window_block,
    _ensure_grid_bubble_block,
    _ensure_titleblock,
]


# --- refs returned to scenarios --------------------------------------------


@dataclass
class DoorRef:
    insert: Any
    tag: str
    index: int


@dataclass
class ColumnRef:
    poly: Any
    hatch: Any
    index: int
    center: tuple[float, float]


@dataclass
class DimensionRef:
    dimension: Any
    name: str


@dataclass
class SheetRefs:
    doc: Drawing
    sheet_no: str
    origin: tuple[float, float]
    scale_denom: float
    frame_bbox: list[float] = field(default_factory=list)
    titleblock_insert: Any = None
    doors: list[DoorRef] = field(default_factory=list)
    windows: list[Any] = field(default_factory=list)
    columns: list[ColumnRef] = field(default_factory=list)
    walls: dict[str, Any] = field(default_factory=dict)
    room_texts: list[Any] = field(default_factory=list)
    legend_mtext: Any = None
    dimensions: list[DimensionRef] = field(default_factory=list)
    hatches_ansi31: list[Any] = field(default_factory=list)
    leader: Any = None


@dataclass
class _Ctx:
    doc: Drawing
    msp: Any
    origin: tuple[float, float]
    scale_denom: float
    content_scale: float
    sheet_no: str
    title: str
    date_text: str
    project: str

    def pt(self, x: float, y: float) -> tuple[float, float]:
        return (self.origin[0] + x * self.content_scale, self.origin[1] + y * self.content_scale)


# --- steps (each independent -- no step reads another step's output, so
# reversing DEFAULT_STEP_ORDER only changes handle numbering, never
# geometry) ------------------------------------------------------------------


def _step_frame_and_titleblock(ctx: _Ctx, refs: SheetRefs) -> None:
    ox, oy = ctx.origin
    fw = PAPER_W * ctx.scale_denom
    fh = PAPER_H * ctx.scale_denom
    ctx.msp.add_lwpolyline(
        [(ox, oy), (ox + fw, oy), (ox + fw, oy + fh), (ox, oy + fh)],
        format="xy",
        close=True,
        dxfattribs={"layer": "TITLE"},
    )
    refs.frame_bbox = [round3(ox), round3(oy), round3(ox + fw), round3(oy + fh)]
    tb_x = ox + fw - TB_W * ctx.scale_denom
    tb_y = oy
    ins = ctx.msp.add_blockref(
        "TITLEBLOCK",
        (tb_x, tb_y),
        dxfattribs={"layer": "TITLE", "xscale": ctx.scale_denom, "yscale": ctx.scale_denom},
    )
    ins.add_auto_attribs(
        {
            "DWG_NO": ctx.sheet_no,
            "TITLE": ctx.title,
            "SCALE": f"1:{int(ctx.scale_denom)}",
            "DATE": ctx.date_text,
            "PROJECT": ctx.project,
        }
    )
    refs.titleblock_insert = ins


def _step_grid(ctx: _Ctx, refs: SheetRefs) -> None:
    cs = ctx.content_scale
    x_positions, y_positions = _grid_positions()
    y0l, y1l = y_positions[0] - 300.0, y_positions[-1] + 300.0
    for label, x in zip(X_LABELS, x_positions, strict=True):
        ctx.msp.add_line(ctx.pt(x, y0l), ctx.pt(x, y1l), dxfattribs={"layer": "A-GRID"})
        bubble = ctx.msp.add_blockref(
            "GRID_BUBBLE",
            ctx.pt(x, y1l + 700.0),
            dxfattribs={"layer": "A-GRID", "xscale": cs, "yscale": cs},
        )
        bubble.add_auto_attribs({"LABEL": label})
    x0l, x1l = x_positions[0] - 300.0, x_positions[-1] + 300.0
    for label, y in zip(Y_LABELS, y_positions, strict=True):
        ctx.msp.add_line(ctx.pt(x0l, y), ctx.pt(x1l, y), dxfattribs={"layer": "A-GRID"})
        bubble = ctx.msp.add_blockref(
            "GRID_BUBBLE",
            ctx.pt(x0l - 700.0, y),
            dxfattribs={"layer": "A-GRID", "xscale": cs, "yscale": cs},
        )
        bubble.add_auto_attribs({"LABEL": label})


def _wall_rect_h(ctx: _Ctx, y_center_l: float, x0_l: float, x1_l: float):
    half = WALL_THK / 2.0
    y0l, y1l = y_center_l - half, y_center_l + half
    pts = [ctx.pt(x0_l, y0l), ctx.pt(x1_l, y0l), ctx.pt(x1_l, y1l), ctx.pt(x0_l, y1l)]
    return ctx.msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs={"layer": "A-WALL"})


def _wall_rect_v(ctx: _Ctx, x_center_l: float, y0_l: float, y1_l: float):
    half = WALL_THK / 2.0
    x0l, x1l = x_center_l - half, x_center_l + half
    pts = [ctx.pt(x0l, y0_l), ctx.pt(x1l, y0_l), ctx.pt(x1l, y1_l), ctx.pt(x0l, y1_l)]
    return ctx.msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs={"layer": "A-WALL"})


def _step_walls(ctx: _Ctx, refs: SheetRefs) -> None:
    w: dict[str, Any] = {}
    w["ext_bottom"] = _wall_rect_h(ctx, WALL_Y0, WALL_X0, WALL_X1)
    w["ext_top"] = _wall_rect_h(ctx, WALL_Y1, WALL_X0, WALL_X1)
    w["ext_left"] = _wall_rect_v(ctx, WALL_X0, WALL_Y0, WALL_Y1)
    w["ext_right"] = _wall_rect_v(ctx, WALL_X1, WALL_Y0, WALL_Y1)
    w["part_v1"] = _wall_rect_v(ctx, PART_V1_X, WALL_Y0, WALL_Y1)
    w["part_v2"] = _wall_rect_v(ctx, PART_V2_X, WALL_Y0, WALL_Y1)
    w["part_h"] = _wall_rect_h(ctx, PART_H_Y, WALL_X0, WALL_X1)
    refs.walls = w


def _step_columns(ctx: _Ctx, refs: SheetRefs) -> None:
    x_positions, y_positions = _grid_positions()
    half = COLUMN_SIZE / 2.0
    idx = 0
    for i in COLUMN_GRID_I:
        for j in COLUMN_GRID_J:
            xl, yl = x_positions[i], y_positions[j]
            pts = [
                ctx.pt(xl - half, yl - half),
                ctx.pt(xl + half, yl - half),
                ctx.pt(xl + half, yl + half),
                ctx.pt(xl - half, yl + half),
            ]
            poly = ctx.msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs={"layer": "A-COL"})
            hatch = ctx.msp.add_hatch(dxfattribs={"layer": "A-COL"})
            hatch.paths.add_polyline_path(pts, is_closed=True)
            hatch.set_solid_fill(color=1)
            refs.columns.append(ColumnRef(poly=poly, hatch=hatch, index=idx, center=ctx.pt(xl, yl)))
            idx += 1


def _step_doors(ctx: _Ctx, refs: SheetRefs) -> None:
    cs = ctx.content_scale
    for i, (tag, xl, yl) in enumerate(DOOR_SPECS):
        insert_pt = ctx.pt(xl - DOOR_PANEL_LEN / 2.0, yl)
        ins = ctx.msp.add_blockref(
            "DOOR_900", insert_pt, dxfattribs={"layer": "A-DOOR", "xscale": cs, "yscale": cs}
        )
        ins.add_auto_attribs({"TAG": tag})
        refs.doors.append(DoorRef(insert=ins, tag=tag, index=i))


def _step_windows(ctx: _Ctx, refs: SheetRefs) -> None:
    cs = ctx.content_scale
    for xl, yl in WINDOW_SPECS:
        insert_pt = ctx.pt(xl - WINDOW_WIDTH / 2.0, yl - 30.0)
        ins = ctx.msp.add_blockref(
            "WIN_1800", insert_pt, dxfattribs={"layer": "A-WIND", "xscale": cs, "yscale": cs}
        )
        refs.windows.append(ins)


def _step_room_texts(ctx: _Ctx, refs: SheetRefs) -> None:
    for name, (xl, yl) in zip(ROOM_NAMES, ROOM_CENTERS, strict=True):
        t = ctx.msp.add_text(name, dxfattribs={"layer": "A-TEXT", "height": 300.0 * ctx.content_scale})
        t.set_placement(ctx.pt(xl, yl))
        refs.room_texts.append(t)


def _step_legend(ctx: _Ctx, refs: SheetRefs) -> None:
    mt = ctx.msp.add_mtext(
        LEGEND_TEXT,
        dxfattribs={
            "layer": "A-TEXT",
            "char_height": LEGEND_CHAR_HEIGHT * ctx.content_scale,
            "width": LEGEND_WIDTH * ctx.content_scale,
        },
    )
    mt.set_location(ctx.pt(*LEGEND_LOCAL))
    refs.legend_mtext = mt


def _step_dimensions(ctx: _Ctx, refs: SheetRefs) -> None:
    specs = [
        ("overall_width", ctx.pt(WALL_X0, WALL_Y0 - 1500.0), ctx.pt(WALL_X0, WALL_Y0), ctx.pt(WALL_X1, WALL_Y0), 0),
        (
            "overall_height",
            ctx.pt(WALL_X0 - 1500.0, WALL_Y0),
            ctx.pt(WALL_X0, WALL_Y0),
            ctx.pt(WALL_X0, WALL_Y1),
            90,
        ),
        (
            "room_a_width",
            ctx.pt(WALL_X0, WALL_Y1 + 1500.0),
            ctx.pt(WALL_X0, WALL_Y1),
            ctx.pt(PART_V1_X, WALL_Y1),
            0,
        ),
        (
            "room_b_width",
            ctx.pt(PART_V1_X, WALL_Y1 + 1500.0),
            ctx.pt(PART_V1_X, WALL_Y1),
            ctx.pt(PART_V2_X, WALL_Y1),
            0,
        ),
    ]
    for name, base, p1, p2, angle in specs:
        dso = ctx.msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=angle, dxfattribs={"layer": "A-DIM"})
        dso.render()
        refs.dimensions.append(DimensionRef(dimension=dso.dimension, name=name))


def _step_hatches(ctx: _Ctx, refs: SheetRefs) -> None:
    for x0l, y0l, x1l, y1l in HATCH_SPECS:
        pts = [ctx.pt(x0l, y0l), ctx.pt(x1l, y0l), ctx.pt(x1l, y1l), ctx.pt(x0l, y1l)]
        h = ctx.msp.add_hatch(dxfattribs={"layer": "A-HATCH", "color": 2})
        h.paths.add_polyline_path(pts, is_closed=True)
        h.set_pattern_fill("ANSI31", scale=40.0 * ctx.content_scale)
        refs.hatches_ansi31.append(h)


def _step_leader(ctx: _Ctx, refs: SheetRefs) -> None:
    pts = [ctx.pt(x, y) for x, y in LEADER_LOCAL]
    refs.leader = ctx.msp.add_leader(pts, dxfattribs={"layer": "A-DIM"})


DEFAULT_STEP_ORDER: list[Callable[[_Ctx, SheetRefs], None]] = [
    _step_frame_and_titleblock,
    _step_grid,
    _step_walls,
    _step_columns,
    _step_doors,
    _step_windows,
    _step_room_texts,
    _step_legend,
    _step_dimensions,
    _step_hatches,
    _step_leader,
]


def build_base_plan(
    *,
    origin: tuple[float, float] = (0.0, 0.0),
    sheet_no: str = "A-101",
    title: str = "1층 평면도",
    scale_denom: float = 100,
    date_text: str = "2026-09-04",
    project: str = "대명건설",
    doc: Drawing | None = None,
    reversed_layout: bool = False,
) -> SheetRefs:
    """Build one sheet's worth of entities.

    ``doc`` may be an already-built shared document (S13/S14 multi-sheet
    files) -- layer/block creation is idempotent so a second call on the same
    doc adds nothing twice. ``reversed_layout=True`` (S12 only) runs the
    layer table, block-definition table and entity-creation steps in reverse
    order, changing every handle while leaving geometry identical -- see the
    module docstring.
    """
    if doc is None:
        doc = new_doc()
    layer_order = list(reversed(LAYER_ORDER)) if reversed_layout else list(LAYER_ORDER)
    ensure_layers(doc, layer_order)
    block_order = list(reversed(BLOCK_BUILDERS)) if reversed_layout else list(BLOCK_BUILDERS)
    for builder in block_order:
        builder(doc)
    msp = doc.modelspace()
    ctx = _Ctx(
        doc=doc,
        msp=msp,
        origin=origin,
        scale_denom=float(scale_denom),
        content_scale=float(scale_denom) / 100.0,
        sheet_no=sheet_no,
        title=title,
        date_text=date_text,
        project=project,
    )
    refs = SheetRefs(doc=doc, sheet_no=sheet_no, origin=origin, scale_denom=float(scale_denom))
    steps = list(reversed(DEFAULT_STEP_ORDER)) if reversed_layout else list(DEFAULT_STEP_ORDER)
    for step in steps:
        step(ctx, refs)
    return refs
