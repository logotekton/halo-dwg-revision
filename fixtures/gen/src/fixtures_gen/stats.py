"""Independent statistics computation: a ``LayerStatsDocument`` (brief W2-03,
``docs/contracts/stats-definition.md``, ``packages/schema/src/stats/layer-stats.schema.json``).

This module is the *cross-check* half of the generator: fixture builders
never compute truth numbers while placing entities. Instead, ``compute_layer_stats``
re-opens the DXF bytes that were just written with ``ezdxf.readfile`` and
recomputes every number from scratch -- independently of
``halo_engine.ingest.stats`` (brief Constraints: "서로 임포트하지 않는다"), so
the F01-F10 crosscheck test (``tests/test_engine_crosscheck.py``) is
meaningful.

Definitions (``docs/contracts/stats-definition.md``):

* Bucket key ``(space, layer)``. ``space`` is ``MODEL`` or ``PAPER:<layout
  name>``. Only top-level entities of a space are counted -- never the
  content of a block *definition* (an INSERT counts, what it points at
  doesn't).
* ``count_by_type``  -- ``dxftype()`` -> count over top-level entities.
  ATTRIB, ATTDEF, SEQEND and VERTEX are never counted (owned entities).
* ``length_sum_mm``  -- LINE, LWPOLYLINE, POLYLINE (2D only), ARC, CIRCLE,
  ELLIPSE, SPLINE. Bulges use the analytic arc formula; ELLIPSE/SPLINE use a
  0.01mm ``flattening`` polyline approximation.
* ``hatch_area_sum_mm2`` -- signed sum of HATCH boundary-path polygon areas:
  external/outermost paths add, other (hole/island) paths subtract.
  Fixtures only ever build HATCH boundaries as straight-edge
  ``PolylinePath`` loops (no bulges, no EdgePath), so plain shoelace area is
  exact -- see ``fixtures/README.md`` Decisions.
* ``text_count`` / ``text_hash`` -- TEXT + MTEXT + ATTRIB (collected via
  ``insert.attribs``, attributed to the ATTRIB's own layer). MTEXT uses the
  raw ``.text`` (control codes included). Hash: NFC-normalise each string,
  sort ascending by code point, join with ``"\\n"``, ``sha1`` and keep the
  first 16 hex characters (empty set -> hash of the empty string).
* ``insert_by_block`` -- ``dxf.name`` -> count over top-level INSERTs (NFC
  normalised, XREF blocks included).
* ``bbox`` -- ``{"min": [x, y], "max": [x, y]}`` via ``ezdxf.bbox.extents``
  over every entity attributed to the bucket (top-level entities and that
  bucket's ATTRIBs); omitted when the bucket has no entity with extents.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from typing import Any

import ezdxf
import ezdxf.bbox
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Layout

import fixtures_gen

SCHEMA_VERSION = "0.1"

LENGTH_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"}
TEXT_TYPES = {"TEXT", "MTEXT"}
FLATTEN_DISTANCE = 0.01
#: HatchBoundaryPath.path_type_flags bits: EXTERNAL(1) | OUTERMOST(16).
_EXTERNAL_OR_OUTERMOST = 0b10001


def producer_info() -> dict[str, str]:
    """``producer`` for a document this module computed.

    ``"fixtures-gen"`` is not a member of the schema's closed ``producer.name``
    enum (``packages/schema/src/ndj/document.schema.json`` ``$defs/producer``
    only lists ``viewer.mlightcad``/``engine.ezdxf``/``acad-ts``/``libredwg-web``),
    so this reuses ``"engine.ezdxf"`` -- both this module and
    ``halo_engine.ingest.stats`` are, after all, ezdxf-based readers -- and
    distinguishes itself in ``version`` instead. See the W2-03 report's
    Decisions and its "Shared-file patch" note asking packages/schema to add
    a ``"fixtures-gen"`` enum member.
    """
    return {
        "name": "engine.ezdxf",
        "version": f"fixtures-gen/{fixtures_gen.__version__}+ezdxf/{ezdxf.__version__}",
    }


def _nfc_sorted_join(texts: list[str]) -> str:
    normalised = [unicodedata.normalize("NFC", t) for t in texts]
    return "\n".join(sorted(normalised))


def _text_hash(texts: list[str]) -> str:
    joined = _nfc_sorted_join(texts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def _space_label(layout: Layout) -> str:
    return "MODEL" if layout.name == "Model" else f"PAPER:{layout.name}"


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


def _flattened_length(entity: DXFGraphic) -> float:
    pts = list(entity.flattening(FLATTEN_DISTANCE))
    total = 0.0
    for a, b in zip(pts, pts[1:], strict=False):
        total += float((b - a).magnitude)
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
        # Contract: "POLYLINE(2D)" only -- 3D polylines are not measured.
        if entity.is_2d_polyline:
            pts = [
                (float(v.dxf.location.x), float(v.dxf.location.y), float(v.dxf.bulge))
                for v in entity.vertices
            ]
            return _polyline_length(pts, bool(entity.is_closed))
        return 0.0
    if t in ("ELLIPSE", "SPLINE"):
        return _flattened_length(entity)
    return 0.0


def _hatch_area(entity: DXFGraphic) -> float:
    total = 0.0
    for path in entity.paths:
        verts = getattr(path, "vertices", None)
        if not verts or len(verts) < 3:
            continue
        area = _shoelace([(float(x), float(y)) for x, y, _b in verts])
        is_hole = not (path.path_type_flags & _EXTERNAL_OR_OUTERMOST)
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


def _round6(value: float) -> float:
    """``round(x, 6)`` with negative zero normalised to ``0.0`` (mirrors the
    engine's ``halo_engine.ingest.stats._round6``; spline flattening yields
    ``-0.0`` on some platforms and JSON keeps the sign)."""
    return round(float(value), 6) + 0.0


def _bbox_of(entities: list[DXFGraphic]) -> dict[str, list[float]] | None:
    if not entities:
        return None
    box = ezdxf.bbox.extents(entities)
    if not box.has_data:
        return None
    return {
        "min": [_round6(box.extmin.x), _round6(box.extmin.y)],
        "max": [_round6(box.extmax.x), _round6(box.extmax.y)],
    }


class _Bucket:
    __slots__ = (
        "count_by_type",
        "length_sum_mm",
        "hatch_area_sum_mm2",
        "texts",
        "insert_by_block",
        "bbox_entities",
    )

    def __init__(self) -> None:
        self.count_by_type: dict[str, int] = {}
        self.length_sum_mm = 0.0
        self.hatch_area_sum_mm2 = 0.0
        self.texts: list[str] = []
        self.insert_by_block: dict[str, int] = {}
        self.bbox_entities: list[DXFGraphic] = []

    def add_top_level(self, entity: DXFGraphic) -> None:
        t = entity.dxftype()
        self.count_by_type[t] = self.count_by_type.get(t, 0) + 1
        if t in LENGTH_TYPES:
            self.length_sum_mm += _entity_length(entity)
        if t == "HATCH":
            self.hatch_area_sum_mm2 += _hatch_area(entity)
        if t in TEXT_TYPES:
            self.texts.append(entity.dxf.text if t == "TEXT" else entity.text)
        if t == "INSERT":
            name = unicodedata.normalize("NFC", entity.dxf.name)
            self.insert_by_block[name] = self.insert_by_block.get(name, 0) + 1
        self.bbox_entities.append(entity)

    def add_attrib(self, attrib: DXFGraphic) -> None:
        self.texts.append(attrib.dxf.text)
        self.bbox_entities.append(attrib)

    def to_aggregate(self) -> dict[str, Any]:
        count_by_type = dict(sorted(self.count_by_type.items()))
        aggregate: dict[str, Any] = {
            "entity_count": sum(count_by_type.values()),
            "count_by_type": count_by_type,
            "length_sum_mm": round(self.length_sum_mm, 6),
            "hatch_area_sum_mm2": round(self.hatch_area_sum_mm2, 6),
            "text_count": len(self.texts),
            "text_hash": _text_hash(self.texts),
            "insert_by_block": dict(sorted(self.insert_by_block.items())),
        }
        bbox = _bbox_of(self.bbox_entities)
        if bbox is not None:
            aggregate["bbox"] = bbox
        return aggregate


def _iter_spaces(doc: Drawing) -> list[Layout]:
    spaces = [doc.modelspace()]
    for layout in doc.layouts:
        if layout.name == "Model":
            continue
        if len(layout) == 0:
            continue
        spaces.append(layout)
    return spaces


def compute_layer_stats(doc: Drawing, *, file_sha256: str) -> dict[str, Any]:
    """Compute the full ``LayerStatsDocument`` for ``doc``."""
    buckets: dict[tuple[str, str], _Bucket] = {}

    def bucket_for(space: str, layer: str) -> _Bucket:
        key = (space, layer)
        b = buckets.get(key)
        if b is None:
            b = _Bucket()
            buckets[key] = b
        return b

    for layout in _iter_spaces(doc):
        space = _space_label(layout)
        for entity in layout:
            layer = unicodedata.normalize("NFC", entity.dxf.layer)
            bucket_for(space, layer).add_top_level(entity)
            if entity.dxftype() == "INSERT":
                for attrib in entity.attribs:
                    attrib_layer = unicodedata.normalize("NFC", attrib.dxf.layer)
                    bucket_for(space, attrib_layer).add_attrib(attrib)

    bucket_docs = []
    for (space, layer), bucket in sorted(buckets.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        bucket_docs.append({"layer": layer, "space": space, "aggregate": bucket.to_aggregate()})

    totals_bucket = _Bucket()
    for bucket in buckets.values():
        for t, c in bucket.count_by_type.items():
            totals_bucket.count_by_type[t] = totals_bucket.count_by_type.get(t, 0) + c
        totals_bucket.length_sum_mm += bucket.length_sum_mm
        totals_bucket.hatch_area_sum_mm2 += bucket.hatch_area_sum_mm2
        totals_bucket.texts.extend(bucket.texts)
        for name, c in bucket.insert_by_block.items():
            totals_bucket.insert_by_block[name] = totals_bucket.insert_by_block.get(name, 0) + c
        totals_bucket.bbox_entities.extend(bucket.bbox_entities)

    return {
        "schema_version": SCHEMA_VERSION,
        "file_sha256": file_sha256,
        "producer": producer_info(),
        "buckets": bucket_docs,
        "totals": totals_bucket.to_aggregate(),
    }
