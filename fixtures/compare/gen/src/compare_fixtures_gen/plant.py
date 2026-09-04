"""Helpers for planting a deterministic edit onto an "after" document built by
:func:`compare_fixtures_gen.base_plan.build_base_plan`, and for computing the
bbox values ``truth.json`` needs (docs/contracts/r1.md SS4 `RevisionTruth`,
docs/contracts/compare-dxf.md SS5).

Bboxes are computed with :mod:`ezdxf.bbox` on the live in-memory entities
rather than by hand -- robust for arcs, hatches and rendered DIMENSION
geometry alike, and it is what the entities *actually* occupy after an edit.
"""

from __future__ import annotations

from ezdxf import bbox as ez_bbox


def round3(x: float) -> float:
    r = round(float(x), 3)
    return 0.0 if r == 0 else r


def bbox_of(entities) -> list[float]:
    entities = [e for e in entities if e is not None]
    box = ez_bbox.extents(entities, fast=False)
    if not box.has_data:
        raise ValueError("no geometry to compute a bbox for")
    return [
        round3(box.extmin.x),
        round3(box.extmin.y),
        round3(box.extmax.x),
        round3(box.extmax.y),
    ]


def union_bbox(a: list[float], b: list[float]) -> list[float]:
    return [
        round3(min(a[0], b[0])),
        round3(min(a[1], b[1])),
        round3(max(a[2], b[2])),
        round3(max(a[3], b[3])),
    ]


def insert_entities(insert):
    """``insert`` plus its attached ATTRIBs -- pass this to :func:`bbox_of`
    so a door/window/bubble's tag text is included in its bbox."""
    return [insert, *insert.attribs]


def move_insert(insert, dx: float, dy: float) -> None:
    """Translate an INSERT (and its attached ATTRIBs) in place, keeping its
    handle. ``Insert.translate`` transforms attached ATTRIB entities too."""
    insert.translate(dx, dy, 0.0)


def set_text(entity, new_text: str) -> None:
    entity.dxf.text = new_text
