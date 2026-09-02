"""Independent statistics computation, per ADR-0002 Section 6.

This module is the *cross-check* half of the generator: fixture builders
never compute truth numbers while placing entities. Instead, ``build_truth``
re-opens the DXF bytes that were just written with ``ezdxf.readfile`` and
recomputes every number from scratch, exactly as the viewer/engine
cross-validation described in ``docs/adr/0002-working-dxf.md`` will.

Definitions (ADR-0002 Section 6, ``docs/briefs/W1-03.md`` Inputs/Constraints):

* ``count_by_type``  -- dxftype() -> count, over the entities directly in a space.
* ``length_sum``     -- sum of lengths for LINE/LWPOLYLINE/POLYLINE/ARC/CIRCLE
                        (analytic) and SPLINE (``flattening(0.01)`` polyline
                        approximation -- the brief calls this out explicitly
                        in Constraints even though the Inputs summary omits
                        SPLINE from the type list; see README Decisions).
* ``hatch_area_sum`` -- signed sum of HATCH boundary-path polygon areas:
                        external/outermost paths add, other (hole/island)
                        paths subtract. Fixtures only ever build HATCH
                        boundaries as straight-edge ``PolylinePath`` loops
                        (no bulges, no EdgePath), so plain shoelace area is
                        exact -- see README Decisions.
* ``text_count``     -- count of TEXT + MTEXT entities.
* ``text_hash``      -- sha1(NFC(text))[:16] per TEXT/MTEXT entity, entities
                        ordered by ascending numeric handle, concatenated and
                        hashed again with sha1 -> hex digest. ``None`` when
                        there are no text entities in the group.
* ``insert_by_block`` -- dxf.name -> count, over INSERT entities directly in
                        a space (not recursing into block definitions).
* ``bbox``           -- ``[xmin, ymin, xmax, ymax]`` via ``ezdxf.bbox.extents``,
                        ``None`` when the space/layer has no entities with
                        extents.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from typing import Any

import ezdxf.bbox
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Layout

LENGTH_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "SPLINE"}
TEXT_TYPES = {"TEXT", "MTEXT"}


def _nfc_sha1_16(text: str) -> str:
    return hashlib.sha1(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()[:16]


def _entity_text(entity: DXFGraphic) -> str:
    if entity.dxftype() == "TEXT":
        return entity.dxf.text
    if entity.dxftype() == "MTEXT":
        return entity.text
    return ""


def _polyline_length(points_xyb: list[tuple[float, float, float]], closed: bool) -> float:
    """``points_xyb``: list of (x, y, bulge). Bulge follows the DXF convention:
    ``4 * atan(bulge)`` is the included angle of the arc replacing the
    straight segment from this vertex to the next.
    """
    n = len(points_xyb)
    if n < 2:
        return 0.0
    seg_count = n if closed else n - 1
    total = 0.0
    for i in range(seg_count):
        x1, y1, bulge = points_xyb[i]
        x2, y2, _ = points_xyb[(i + 1) % n]
        chord = math.hypot(float(x2) - float(x1), float(y2) - float(y1))
        bulge = float(bulge)
        if bulge:
            angle = 4.0 * math.atan(bulge)
            if angle:
                radius = abs(chord / (2.0 * math.sin(angle / 2.0)))
                total += radius * abs(angle)
                continue
        total += chord
    return total


def _entity_length(entity: DXFGraphic) -> float:
    t = entity.dxftype()
    if t == "LINE":
        return float((entity.dxf.end - entity.dxf.start).magnitude)
    if t == "CIRCLE":
        return 2.0 * math.pi * float(entity.dxf.radius)
    if t == "ARC":
        span = (float(entity.dxf.end_angle) - float(entity.dxf.start_angle)) % 360.0
        if span == 0.0:
            span = 360.0
        return float(entity.dxf.radius) * math.radians(span)
    if t == "LWPOLYLINE":
        pts = [(float(x), float(y), float(b)) for x, y, b in entity.get_points("xyb")]
        return _polyline_length(pts, bool(entity.closed))
    if t == "POLYLINE":
        if entity.is_2d_polyline or entity.is_3d_polyline:
            if entity.is_2d_polyline:
                pts = [
                    (float(v.dxf.location.x), float(v.dxf.location.y), float(v.dxf.bulge))
                    for v in entity.vertices
                ]
                return _polyline_length(pts, bool(entity.is_closed))
            locs = [v.dxf.location for v in entity.vertices]
            n = len(locs)
            seg_count = n if entity.is_closed else n - 1
            total = 0.0
            for i in range(max(seg_count, 0)):
                a = locs[i]
                b = locs[(i + 1) % n]
                total += float((b - a).magnitude)
            return total
        return 0.0
    if t == "SPLINE":
        pts = list(entity.flattening(0.01))
        total = 0.0
        for a, b in zip(pts, pts[1:], strict=False):
            total += float((b - a).magnitude)
        return total
    return 0.0


def _hatch_area(entity: DXFGraphic) -> float:
    total = 0.0
    for path in entity.paths:
        verts = getattr(path, "vertices", None)
        if not verts or len(verts) < 3:
            continue
        area = _shoelace([(float(x), float(y)) for x, y, _b in verts])
        is_hole = not (path.path_type_flags & 0b10001)  # EXTERNAL(1) | OUTERMOST(16)
        total += -area if is_hole else area
    return total


def _shoelace(points: list[tuple[float, float]]) -> float:
    n = len(points)
    acc = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def _handle_key(entity: DXFGraphic) -> int:
    try:
        return int(entity.dxf.handle, 16)
    except (TypeError, ValueError):
        return 0


def _empty_group() -> dict[str, Any]:
    return {
        "count_by_type": {},
        "length_sum": 0.0,
        "hatch_area_sum": 0.0,
        "text_count": 0,
        "text_hash": None,
        "insert_by_block": {},
        "bbox": None,
    }


def _finalize_group(entities: list[DXFGraphic]) -> dict[str, Any]:
    group = _empty_group()
    count_by_type: dict[str, int] = {}
    insert_by_block: dict[str, int] = {}
    length_sum = 0.0
    hatch_area_sum = 0.0
    text_entities: list[DXFGraphic] = []

    for e in entities:
        t = e.dxftype()
        count_by_type[t] = count_by_type.get(t, 0) + 1
        if t in LENGTH_TYPES:
            length_sum += _entity_length(e)
        if t == "HATCH":
            hatch_area_sum += _hatch_area(e)
        if t in TEXT_TYPES:
            text_entities.append(e)
        if t == "INSERT":
            name = e.dxf.name
            insert_by_block[name] = insert_by_block.get(name, 0) + 1

    text_entities.sort(key=_handle_key)
    text_hash = None
    if text_entities:
        joined = "".join(_nfc_sha1_16(_entity_text(e)) for e in text_entities)
        text_hash = hashlib.sha1(joined.encode("ascii")).hexdigest()

    bbox = ezdxf.bbox.extents(entities) if entities else None
    bbox_out = None
    if bbox is not None and bbox.has_data:
        bbox_out = [
            round(float(bbox.extmin.x), 6),
            round(float(bbox.extmin.y), 6),
            round(float(bbox.extmax.x), 6),
            round(float(bbox.extmax.y), 6),
        ]

    group["count_by_type"] = dict(sorted(count_by_type.items()))
    group["length_sum"] = round(length_sum, 6)
    group["hatch_area_sum"] = round(hatch_area_sum, 6)
    group["text_count"] = len(text_entities)
    group["text_hash"] = text_hash
    group["insert_by_block"] = dict(sorted(insert_by_block.items()))
    group["bbox"] = bbox_out
    return group


def _space_stats(layout: Layout) -> dict[str, Any]:
    entities = list(layout)
    by_layer: dict[str, list[DXFGraphic]] = {}
    for e in entities:
        by_layer.setdefault(e.dxf.layer, []).append(e)
    return {
        "totals": _finalize_group(entities),
        "by_layer": {layer: _finalize_group(es) for layer, es in sorted(by_layer.items())},
    }


def compute_stats(doc: Drawing) -> dict[str, Any]:
    """Compute the full per-space / per-layer / totals statistics tree for ``doc``.

    Only PaperSpace layouts that actually contain entities are included, to
    keep truth files small for fixtures that never use paper space (all of
    them, currently -- see README Decisions).
    """
    by_space: dict[str, Any] = {"Model": _space_stats(doc.modelspace())}
    for layout in doc.layouts:
        if layout.name == "Model":
            continue
        if len(layout) == 0:
            continue
        by_space[layout.name] = _space_stats(layout)

    all_entities: list[DXFGraphic] = []
    for space_name in by_space:
        layout = doc.modelspace() if space_name == "Model" else doc.layout(space_name)
        all_entities.extend(list(layout))

    return {
        "by_space": by_space,
        "totals": _finalize_group(all_entities),
    }
