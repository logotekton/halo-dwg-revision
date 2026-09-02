"""F07 -- member schedule tables drawn with LINE + TEXT (not ACAD_TABLE, per
the brief's "국내 도면 관행"): a column (기둥) schedule and a beam (보)
schedule, each with a header row and one vertically-merged cell in the
"부호" (tag) column.
"""

from __future__ import annotations

import random

from fixtures_gen.base import BuildResult
from fixtures_gen.common import ensure_layers, new_doc
from fixtures_gen.tablekit import draw_table

LAYER_GRID = "A-DIM"
LAYER_TEXT = "A-TEXT"


def build(version: str, rng: random.Random) -> BuildResult:
    doc = new_doc(version)
    ensure_layers(doc, [LAYER_GRID, LAYER_TEXT])
    msp = doc.modelspace()

    col_headers = ["부호", "층", "단면 b×h", "주근", "띠철근"]
    col_rows = [
        ["C1", "1층", "600x600", "8-D25", "D10@200"],
        ["", "2층", "600x600", "8-D25", "D10@200"],
        ["C2", "1층", "500x500", "6-D22", "D10@200"],
        ["C2", "2층", "500x500", "6-D22", "D10@200"],
    ]
    col_table = draw_table(
        msp,
        origin=(0.0, 0.0),
        col_widths=[900.0, 700.0, 1200.0, 1400.0, 1400.0],
        headers=col_headers,
        rows=col_rows,
        merges=[(1, 2, 0)],
        title="기둥 일람표 (Column Schedule)",
        layer_grid=LAYER_GRID,
        layer_text=LAYER_TEXT,
    )

    beam_headers = ["부호", "위치", "단면", "상부근", "하부근", "늑근"]
    beam_rows = [
        ["G1", "단부", "400x600", "4-D22", "3-D22", "D10@150"],
        ["", "중앙", "400x600", "3-D22", "4-D22", "D10@200"],
        ["B1", "단부", "300x500", "3-D19", "3-D19", "D10@150"],
        ["B1", "중앙", "300x500", "2-D19", "3-D19", "D10@200"],
    ]
    beam_table = draw_table(
        msp,
        origin=(0.0, -2200.0),
        col_widths=[900.0, 700.0, 1000.0, 1200.0, 1200.0, 1400.0],
        headers=beam_headers,
        rows=beam_rows,
        merges=[(1, 2, 0)],
        title="보 일람표 (Beam Schedule)",
        layer_grid=LAYER_GRID,
        layer_text=LAYER_TEXT,
    )

    extra = {"tables": {"column_schedule": col_table, "beam_schedule": beam_table}}
    return BuildResult(doc=doc, extra=extra)
