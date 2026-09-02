"""Every native dependency imports and performs one real operation.

This is the guard against "installs but is actually broken" (wrong wheel,
missing shared library, ABI mismatch) for the heavier native deps.
"""

from __future__ import annotations

import ezdxf
import manifold3d
import numpy as np
import pytest
import shapely.geometry
import trimesh


def test_ezdxf_new_and_add_entity() -> None:
    doc = ezdxf.new("R2018")
    msp = doc.modelspace()
    line = msp.add_line((0, 0), (10, 0))
    assert tuple(line.dxf.start)[:2] == (0.0, 0.0)
    assert len(msp) == 1


def test_shapely_polygon_area() -> None:
    poly = shapely.geometry.Polygon([(0, 0), (4, 0), (4, 3), (0, 3)])
    assert poly.area == pytest.approx(12.0)


def test_manifold3d_cube_volume() -> None:
    cube = manifold3d.Manifold.cube((2, 2, 2))
    assert cube.volume() == pytest.approx(8.0)


def test_trimesh_box_volume() -> None:
    box = trimesh.creation.box(extents=(2, 3, 4))
    assert box.volume == pytest.approx(24.0)


def test_ifcopenshell_file_and_wall() -> None:
    import ifcopenshell
    import ifcopenshell.guid

    ifc_file = ifcopenshell.file(schema="IFC4")
    wall = ifc_file.create_entity("IfcWall", GlobalId=ifcopenshell.guid.new())
    assert wall.is_a("IfcWall")
    assert len(ifc_file.by_type("IfcWall")) == 1


def test_numpy_array_sum() -> None:
    arr = np.arange(5)
    assert int(arr.sum()) == 10
