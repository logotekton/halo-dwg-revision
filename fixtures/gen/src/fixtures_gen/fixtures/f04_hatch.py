"""F04 -- fills: SOLID entities, HATCH (ANSI31 x5, one user pattern, two with
holes, one gradient [R2018 only]).

All HATCH boundaries in this fixture are straight-edge polygons built with
``BoundaryPaths.add_polyline_path`` (bulge always 0) so that
``stats._hatch_area`` (plain shoelace, no arc correction) is exact -- see
``fixtures/README.md`` Decisions.
"""

from __future__ import annotations

import random

from fixtures_gen.base import BuildResult
from fixtures_gen.common import new_doc, version_supports

LAYER = "A-HATCH"


def _rect(x0: float, y0: float, w: float, h: float) -> list[tuple[float, float]]:
    return [(x0, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0, y0 + h)]


def build(version: str, rng: random.Random) -> BuildResult:
    doc = new_doc(version)
    doc.layers.add(name=LAYER, color=2, linetype="CONTINUOUS")
    msp = doc.modelspace()
    omitted: list[str] = []

    solids: list[dict] = []
    # -- 5 SOLID entities (filled quad, not HATCH -- no boundary area truth) --
    for i in range(5):
        x0 = i * 1400.0
        pts = _rect(x0, 0, 900, 600)
        # SOLID vertex order is (0,1,3,2) to avoid a bow-tie fill.
        msp.add_solid([pts[0], pts[1], pts[3], pts[2]], dxfattribs={"layer": LAYER, "color": 1})
        solids.append({"index": i, "bbox": [x0, 0, x0 + 900, 600]})

    # -- 5 ANSI31 pattern hatches --------------------------------------------
    ansi31: list[dict] = []
    for i in range(5):
        x0 = i * 1400.0
        y0 = 1200.0
        w, h = 900.0, 600.0
        pts = _rect(x0, y0, w, h)
        hatch = msp.add_hatch(dxfattribs={"layer": LAYER, "color": 3})
        hatch.paths.add_polyline_path(pts, is_closed=True, flags=1)
        hatch.set_pattern_fill("ANSI31", scale=10.0 + i * 2, angle=float(i * 15))
        ansi31.append({"index": i, "boundary": pts, "area": w * h})

    # -- 1 user-defined pattern hatch ----------------------------------------
    x0, y0, w, h = 0.0, 2400.0, 1400.0, 700.0
    pts = _rect(x0, y0, w, h)
    user_hatch = msp.add_hatch(dxfattribs={"layer": LAYER, "color": 4})
    user_hatch.paths.add_polyline_path(pts, is_closed=True, flags=1)
    user_hatch.set_pattern_fill(
        "HALO-BRICK",
        pattern_type=0,
        definition=[
            (0.0, (0.0, 0.0), (0.0, 60.0), [80.0, -20.0]),
            (90.0, (0.0, 0.0), (200.0, 0.0), [40.0, -20.0]),
        ],
    )
    user_pattern = {"boundary": pts, "area": w * h, "name": "HALO-BRICK"}

    # -- 2 hatches with a rectangular hole -----------------------------------
    holed: list[dict] = []
    for i in range(2):
        x0 = 1600.0 + i * 1800.0
        y0 = 2400.0
        w, h = 1400.0, 900.0
        outer = _rect(x0, y0, w, h)
        hole_w, hole_h = 300.0, 200.0
        hole_x0 = x0 + (w - hole_w) / 2
        hole_y0 = y0 + (h - hole_h) / 2
        hole = _rect(hole_x0, hole_y0, hole_w, hole_h)
        hatch = msp.add_hatch(dxfattribs={"layer": LAYER, "color": 5})
        hatch.paths.add_polyline_path(outer, is_closed=True, flags=1)
        hatch.paths.add_polyline_path(hole, is_closed=True, flags=0)
        hatch.set_pattern_fill("ANSI31", scale=8.0, angle=45.0)
        holed.append(
            {
                "index": i,
                "outer": outer,
                "hole": hole,
                "area": w * h - hole_w * hole_h,
            }
        )

    # -- 1 gradient-filled hatch (R2018 only) --------------------------------
    gradient_info: dict | None = None
    if version_supports(version, "GRADIENT_HATCH"):
        x0, y0, w, h = 5200.0, 2400.0, 1200.0, 800.0
        pts = _rect(x0, y0, w, h)
        grad = msp.add_hatch(dxfattribs={"layer": LAYER, "color": 6})
        grad.paths.add_polyline_path(pts, is_closed=True, flags=1)
        grad.set_gradient(color1=(255, 0, 0), color2=(0, 0, 255), rotation=45.0, name="LINEAR")
        gradient_info = {"boundary": pts, "area": w * h}
    else:
        omitted.append("GRADIENT_HATCH: gradient fill requires DXF R2004+, omitted for " + version)

    extra = {
        "solid_count": len(solids),
        "ansi31_hatches": ansi31,
        "user_pattern_hatch": user_pattern,
        "holed_hatches": holed,
        "gradient_hatch": gradient_info,
        "expected_hatch_area_sum": sum(h["area"] for h in ansi31)
        + user_pattern["area"]
        + sum(h["area"] for h in holed)
        + (gradient_info["area"] if gradient_info else 0.0),
    }
    return BuildResult(doc=doc, omitted=omitted, extra=extra)
