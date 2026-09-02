"""F08 -- floor level table (층/SL/FL/층고/CH) for 5 stories (B1..4F) plus a
section sheet with level lines and "<F>FL SL+<mm>" labels.

Height-field discipline follows ``docs/adr/0003-height-fields.md``: SL
(structural level), FL (finish floor level = SL + floor finish thickness),
FLOOR_HEIGHT (story height = next SL - this SL), CH (ceiling height, from
the level table, never compared for equality against SL/FL/FLOOR_HEIGHT).
The generator enforces the ADR's inequality while building the table:
``CH + SLAB_THICKNESS_MM + FLOOR_FINISH_MM < FLOOR_HEIGHT`` for every row
(see the brief's "Defaults for ambiguity": slab 150mm, floor finish 100mm).
"""

from __future__ import annotations

import random

from fixtures_gen.base import BuildResult
from fixtures_gen.common import ensure_layers, new_doc
from fixtures_gen.tablekit import draw_table

LAYER_GRID = "A-DIM"
LAYER_TEXT = "A-TEXT"
LAYER_LEVEL = "S-SLAB"

SLAB_THICKNESS_MM = 150
FLOOR_FINISH_MM = 100

# (floor name, SL, CH) -- FL and FLOOR_HEIGHT are derived below.
FLOORS: list[tuple[str, float, float]] = [
    ("B1", -3600.0, 3000.0),
    ("1F", 0.0, 2600.0),
    ("2F", 3300.0, 2650.0),
    ("3F", 6600.0, 2600.0),
    ("4F", 9900.0, 2700.0),
]
#: SL used only to derive 4F's FLOOR_HEIGHT (story height up to the roof);
#: not exposed as its own table row.
ROOF_SL = 13200.0


def _fmt_signed(value: float) -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:,.0f}"


def build(version: str, rng: random.Random) -> BuildResult:
    doc = new_doc(version)
    ensure_layers(doc, [LAYER_GRID, LAYER_TEXT, LAYER_LEVEL])
    msp = doc.modelspace()

    sl_sequence = [sl for _name, sl, _ch in FLOORS] + [ROOF_SL]
    rows_data: list[dict] = []
    for i, (name, sl, ch) in enumerate(FLOORS):
        fl = sl + FLOOR_FINISH_MM
        floor_height = sl_sequence[i + 1] - sl_sequence[i]
        max_ch = floor_height - SLAB_THICKNESS_MM - FLOOR_FINISH_MM
        assert ch < max_ch, f"{name}: CH {ch} must be < {max_ch} (ADR-0003 inequality)"
        rows_data.append(
            {
                "floor": name,
                "SL": sl,
                "FL": fl,
                "FLOOR_HEIGHT": floor_height,
                "CH": ch,
            }
        )

    headers = ["층", "SL", "FL", "층고", "CH"]
    rows = [
        [
            r["floor"],
            _fmt_signed(r["SL"]),
            _fmt_signed(r["FL"]),
            f"{r['FLOOR_HEIGHT']:,.0f}",
            f"{r['CH']:,.0f}",
        ]
        for r in rows_data
    ]
    table = draw_table(
        msp,
        origin=(0.0, 0.0),
        col_widths=[700.0, 900.0, 900.0, 900.0, 900.0],
        headers=headers,
        rows=rows,
        merges=[],
        title="층고표 (Level Table)",
        layer_grid=LAYER_GRID,
        layer_text=LAYER_TEXT,
    )

    # -- section sheet: one horizontal level line + label per floor ---------
    section_x0, section_y0 = 0.0, -3200.0
    level_lines: list[dict] = []
    for r in rows_data:
        y = section_y0 + r["SL"] / 1000.0 * 100.0  # compress full-scale mm to a readable sheet
        msp.add_line((section_x0, y), (section_x0 + 6000.0, y), dxfattribs={"layer": LAYER_LEVEL})
        base = r["floor"][:-1] if r["floor"].endswith("F") else r["floor"]
        label = f"{base}FL SL{_fmt_signed(r['SL'])}"
        msp.add_text(label, dxfattribs={"layer": LAYER_TEXT, "height": 110}).set_placement(
            (section_x0 + 6150.0, y)
        )
        level_lines.append({"floor": r["floor"], "y": y, "label": label, "sl": r["SL"]})

    extra = {
        "levels": rows_data,
        "slab_thickness_mm": SLAB_THICKNESS_MM,
        "floor_finish_mm": FLOOR_FINISH_MM,
        "inequality": "CH + SLAB_THICKNESS_MM + FLOOR_FINISH_MM < FLOOR_HEIGHT",
        "table": table,
        "section": {"level_lines": level_lines},
    }
    return BuildResult(doc=doc, extra=extra)
