"""F01 -- basic geometry primitives across 5 layers with varied color/linetype.

LINE, LWPOLYLINE (open/closed/bulge), old-style POLYLINE, ARC, CIRCLE,
ELLIPSE, SPLINE, POINT.
"""

from __future__ import annotations

import random

from fixtures_gen.base import BuildResult
from fixtures_gen.common import new_doc

LAYERS = [
    ("GEOM-CONT", 1, "CONTINUOUS"),
    ("GEOM-DASH", 3, "DASHED"),
    ("GEOM-CTR", 5, "CENTER"),
    ("GEOM-HID", 6, "DOT"),
    ("GEOM-PHTM", 8, "PHANTOM"),
]


def build(version: str, rng: random.Random) -> BuildResult:
    doc = new_doc(version)
    msp = doc.modelspace()
    for name, color, linetype in LAYERS:
        doc.layers.add(name=name, color=color, linetype=linetype)

    # -- LINE: a fan of 6 lines on GEOM-CONT --------------------------------
    origin = (0.0, 0.0)
    for _i in range(6):
        angle = rng.uniform(0, 360)
        length = rng.uniform(500, 2000)
        end = (
            origin[0] + length * _cos(angle),
            origin[1] + length * _sin(angle),
        )
        msp.add_line(origin, end, dxfattribs={"layer": "GEOM-CONT"})

    # -- LWPOLYLINE: open, closed, and one with an arc bulge segment -------
    open_pts = [(0, 3000), (1000, 3000), (1000, 4000), (2500, 4200)]
    msp.add_lwpolyline(open_pts, format="xy", close=False, dxfattribs={"layer": "GEOM-DASH"})

    closed_pts = [(3500, 3000), (5000, 3000), (5000, 4200), (3500, 4200)]
    msp.add_lwpolyline(closed_pts, format="xy", close=True, dxfattribs={"layer": "GEOM-DASH"})

    # xyb points: (x, y, bulge). bulge=1.0 on the last segment -> semicircle.
    bulge_pts = [(6000, 3000, 0.0), (7500, 3000, 1.0), (7500, 4200, 0.0), (6000, 4200, 0.0)]
    msp.add_lwpolyline(bulge_pts, format="xyb", close=True, dxfattribs={"layer": "GEOM-DASH"})

    # -- old-style POLYLINE (2D), closed, no bulge --------------------------
    pl = msp.add_polyline2d(
        [(0, -1500), (1200, -1500), (1200, -600), (600, -300), (0, -600)],
        format="xy",
        dxfattribs={"layer": "GEOM-CTR"},
    )
    pl.close(True)

    # -- ARC: several, including one that wraps through 0 degrees ----------
    arc_specs = [
        ((2500, -1000), 400, 20, 160),
        ((4000, -1000), 300, 350, 30),  # wraps through 0
        ((5500, -1000), 550, 0, 359.9),
    ]
    for center, radius, start, end in arc_specs:
        msp.add_arc(
            center=center,
            radius=radius,
            start_angle=start,
            end_angle=end,
            dxfattribs={"layer": "GEOM-CTR"},
        )

    # -- CIRCLE --------------------------------------------------------------
    for cx, cy in [(0, -3200), (1600, -3200), (3200, -3200)]:
        r = rng.uniform(150, 600)
        msp.add_circle((cx, cy), r, dxfattribs={"layer": "GEOM-HID"})

    # -- ELLIPSE (not part of length_sum, still counted) ---------------------
    msp.add_ellipse(
        center=(5000, -3200),
        major_axis=(700, 0),
        ratio=0.4,
        start_param=0.0,
        end_param=6.283185307179586,
        dxfattribs={"layer": "GEOM-HID"},
    )
    msp.add_ellipse(
        center=(7000, -3200),
        major_axis=(0, 500),
        ratio=0.6,
        start_param=0.3,
        end_param=5.5,
        dxfattribs={"layer": "GEOM-HID"},
    )

    # -- SPLINE (fit points; length recomputed via flattening(0.01)) --------
    fit_pts_1 = [(0, -5000), (900, -4600), (1800, -5200), (2700, -4700), (3600, -5100)]
    msp.add_spline(fit_pts_1, dxfattribs={"layer": "GEOM-PHTM"})

    control_pts = [(4500, -5000), (5200, -4300), (6000, -5600), (6800, -4600)]
    msp.add_spline(control_pts, dxfattribs={"layer": "GEOM-PHTM"}).closed = False

    # -- POINT ----------------------------------------------------------------
    for x in range(0, 2400, 400):
        msp.add_point((x, -6200), dxfattribs={"layer": "GEOM-PHTM"})

    return BuildResult(doc=doc)


def _cos(angle_deg: float) -> float:
    import math

    return math.cos(math.radians(angle_deg))


def _sin(angle_deg: float) -> float:
    import math

    return math.sin(math.radians(angle_deg))
