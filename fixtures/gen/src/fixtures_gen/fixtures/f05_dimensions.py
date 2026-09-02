"""F05 -- dimensions and leaders: linear, aligned, angular, radius, diameter,
ordinate DIMENSION entities, a LEADER, a MULTILEADER (R2018 only, the DXF
entity type for what AutoCAD UI calls "MLEADER"), and two DIMSTYLEs.
"""

from __future__ import annotations

import random

from ezdxf.math import Vec2

from fixtures_gen.base import BuildResult
from fixtures_gen.common import ensure_layers, new_doc, version_supports

LAYER = "A-DIM"


def _make_dimstyles(doc) -> None:
    d1 = doc.dimstyles.new("HALO-DIM1")
    d1.dxf.dimtxt = 100
    d1.dxf.dimasz = 80
    d1.dxf.dimexe = 50
    d1.dxf.dimexo = 30
    d1.dxf.dimclrd = 3
    d1.dxf.dimclrt = 7

    d2 = doc.dimstyles.new("HALO-DIM2")
    d2.dxf.dimtxt = 120
    d2.dxf.dimasz = 60
    d2.dxf.dimexe = 40
    d2.dxf.dimexo = 20
    d2.dxf.dimclrd = 5
    d2.dxf.dimclrt = 1
    d2.dxf.dimtad = 1


def build(version: str, rng: random.Random) -> BuildResult:
    doc = new_doc(version)
    ensure_layers(doc, [LAYER, "S-COL"])
    _make_dimstyles(doc)
    msp = doc.modelspace()
    omitted: list[str] = []
    kinds: list[str] = []

    # -- linear -----------------------------------------------------------
    dim = msp.add_linear_dim(
        base=(0, 800),
        p1=(0, 0),
        p2=(2000, 0),
        angle=0,
        dimstyle="HALO-DIM1",
        dxfattribs={"layer": LAYER},
    )
    dim.render()
    kinds.append("linear")

    # -- aligned ------------------------------------------------------------
    dim = msp.add_aligned_dim(
        p1=(2400, 0),
        p2=(3400, 900),
        distance=250,
        dimstyle="HALO-DIM1",
        dxfattribs={"layer": LAYER},
    )
    dim.render()
    kinds.append("aligned")

    # -- angular (center/radius/angle shortcut) -----------------------------
    dim = msp.add_angular_dim_cra(
        center=(5000, 0),
        radius=600,
        start_angle=10,
        end_angle=100,
        distance=250,
        dimstyle="HALO-DIM2",
        dxfattribs={"layer": LAYER},
    )
    dim.render()
    kinds.append("angular")

    # -- radius ---------------------------------------------------------------
    circle_center = Vec2(7000, 0)
    msp.add_circle(circle_center, 500, dxfattribs={"layer": "S-COL"})
    dim = msp.add_radius_dim(
        center=circle_center,
        radius=500,
        angle=35,
        dimstyle="HALO-DIM2",
        dxfattribs={"layer": LAYER},
    )
    dim.render()
    kinds.append("radius")

    # -- diameter -------------------------------------------------------------
    circle_center2 = Vec2(9000, 0)
    msp.add_circle(circle_center2, 400, dxfattribs={"layer": "S-COL"})
    dim = msp.add_diameter_dim(
        center=circle_center2,
        radius=400,
        angle=60,
        dimstyle="HALO-DIM2",
        dxfattribs={"layer": LAYER},
    )
    dim.render()
    kinds.append("diameter")

    # -- ordinate (x and y) ----------------------------------------------------
    origin = (10500.0, 0.0)
    feature = (11200.0, 350.0)
    dim = msp.add_ordinate_x_dim(
        feature_location=feature,
        offset=(0, 900),
        origin=origin,
        dimstyle="HALO-DIM1",
        dxfattribs={"layer": LAYER},
    )
    dim.render()
    kinds.append("ordinate_x")

    dim = msp.add_ordinate_y_dim(
        feature_location=feature,
        offset=(700, 0),
        origin=origin,
        dimstyle="HALO-DIM1",
        dxfattribs={"layer": LAYER},
    )
    dim.render()
    kinds.append("ordinate_y")

    # -- LEADER -----------------------------------------------------------------
    msp.add_leader([(0, -1200), (500, -1800), (1200, -1800)], dxfattribs={"layer": LAYER})
    kinds.append("leader")

    # -- MULTILEADER (R2018 only) ------------------------------------------------
    if version_supports(version, "MULTILEADER"):
        ml = msp.add_multileader_mtext("Standard")
        ml.quick_leader(
            "배관 Ø100mm 구배 1/100",
            target=Vec2(3000, -1600),
            segment1=Vec2(-500, 400),
        )
        kinds.append("multileader")
    else:
        omitted.append("MULTILEADER: requires DXF R2007+, omitted for " + version)

    extra = {
        "dimstyles": ["HALO-DIM1", "HALO-DIM2"],
        "kinds_created": kinds,
    }
    return BuildResult(doc=doc, omitted=omitted, extra=extra)
