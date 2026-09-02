"""``LayerStatsDocument`` computation (docs/contracts/stats-definition.md,
``packages/schema/src/stats/layer-stats.schema.json``).

Deliberately independent of ``fixtures_gen.stats`` (brief W2-03 Constraints:
"엔진 stats.py와 fixtures_gen/stats.py는 서로 임포트하지 않는다") -- the two
implementations exist to cross-check each other, so sharing code between them
would defeat the point.

Definitions, verbatim from the contract:

* Bucket key: ``(space, layer)``. ``space`` is ``MODEL`` or ``PAPER:<layout
  name>``. Entities inside block *definitions* are never counted -- only
  INSERT counts, not what an INSERT points at.
* ``count_by_type``: DXF type name -> count of top-level entities. ATTRIB,
  SEQEND and VERTEX are never counted (they belong to their owning entity).
* ``length_sum_mm``: LINE, LWPOLYLINE, POLYLINE (2D only), ARC, CIRCLE,
  ELLIPSE, SPLINE. Bulges use the analytic arc formula; ELLIPSE/SPLINE use a
  0.01mm ``flattening`` polyline approximation.
* ``hatch_area_sum_mm2``: signed sum of HATCH boundary polygon areas
  (external/outermost paths add, island/hole paths subtract).
* ``text_count`` / ``text_hash``: TEXT + MTEXT + ATTRIB (collected via
  ``insert.attribs``, attributed to the ATTRIB's *own* layer -- not the
  INSERT's). MTEXT uses the raw ``.text`` (control codes included). Hash:
  NFC-normalise each string, sort ascending by code point, join with
  ``"\\n"``, ``sha1`` and take the first 16 hex characters (empty set ->
  hash of the empty string).
* ``insert_by_block``: block name -> INSERT count (XREF blocks included).
* ``bbox``: union of ``geometricExtents`` of every entity attributed to the
  bucket (top-level entities plus that bucket's ATTRIBs).

Robustness (brief W3-08, G0 follow-up 2): two malformations observed on real
acad-ts-written DXF (``fixtures/generated/F06.dwg``/``F03.dwg`` round-tripped
through ``acad-bridge dwg2dxf``, both reproduced in
``tests/ingest/test_stats_robustness.py``) must turn into a diagnostic and a
skip, never an uncaught exception:

* A **dead ATTRIB** (``entity.is_alive is False``) inside ``insert.attribs``.
  ezdxf's own ``Drawing.audit()`` silently destroys one of two entities that
  share a handle (acad-ts's DXF writer occasionally emits a duplicate
  handle -- see ``packages/acad-bridge/README.md`` "Known acad-ts gaps"); the
  owning INSERT's ``attribs`` list still holds the now-``dxf``-less object,
  and touching ``attrib.dxf.text``/``.layer`` raises ``AttributeError``.
* A **zero-length OCS/direction vector** (e.g. an MTEXT ``text_direction`` of
  ``(0, 0, 0)``). ezdxf's typed attribute setter normally refuses this
  (``validator=is_not_null_vector, fixer=RETURN_DEFAULT``), but entities
  loaded through ezdxf's ``fast_load_dxfattribs`` path (MTEXT among them)
  bypass that validator, so a genuinely zero vector written by a buggy
  producer survives into the in-memory document. ``ezdxf.bbox.extents()``
  then builds an ``OCS``/``UCS`` from it and ``Vec3.normalize()`` raises
  ``ZeroDivisionError``.

Diagnostics never enter the returned document (the schema is closed,
``additionalProperties: false``, and this is cross-check data, not geometry
truth) -- callers that want them pass a list via the ``diagnostics`` keyword
and it is appended to in place, brief "Defaults for ambiguity": ``{code,
message, handle?, layer?}`` per entry.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from dataclasses import dataclass, field
from typing import Any

import ezdxf
import ezdxf.bbox
from ezdxf.document import Drawing
from ezdxf.entities import DXFGraphic
from ezdxf.layouts import Layout
from ezdxf.math import BoundingBox

SCHEMA_VERSION = "0.1"

#: Types counted in ``length_sum_mm`` (docstring above; POLYLINE only when 2D).
LENGTH_TYPES = {"LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"}
TEXT_TYPES = {"TEXT", "MTEXT"}
#: Flattening tolerance for ELLIPSE/SPLINE arc-length approximation, mm.
FLATTEN_DISTANCE = 0.01
#: HatchBoundaryPath.path_type_flags bits: EXTERNAL(1) | OUTERMOST(16).
_EXTERNAL_OR_OUTERMOST = 0b10001

#: Diagnostic ``code`` for a dead ATTRIB skipped in ``insert.attribs``.
DIAG_DEAD_ATTRIB = "dead-attrib"
#: Diagnostic ``code`` for a computation excluded by a zero-length OCS/direction vector.
DIAG_ZERO_LENGTH_OCS_VECTOR = "zero-length-ocs-vector"
#: Diagnostic ``code`` for an ATTRIB/SEQEND/VERTEX handed to us as a top-level entity.
DIAG_UNEXPECTED_OWNED_ENTITY = "unexpected-owned-entity-at-top-level"
#: Types the contract (stats-definition.md) says are never counted at the top level --
#: they belong to their owning entity. A well-formed file never yields these from a
#: layout's top-level iterator; a malformed producer can (observed on acad-ts DXF
#: output: a SEQEND left outside its INSERT's structure after a duplicate-handle fixup).
_OWNED_ENTITY_TYPES = frozenset({"ATTRIB", "SEQEND", "VERTEX"})


def _diagnostic(
    code: str, message: str, *, handle: str | None = None, layer: str | None = None
) -> dict[str, Any]:
    """One ``{code, message, handle?, layer?}`` entry (brief W3-08 "Defaults for ambiguity").

    Optional keys are omitted rather than written as ``null`` -- keeps the
    ``*.working.json`` meta a caller eventually writes this into terse.
    """
    entry: dict[str, Any] = {"code": code, "message": message}
    if handle is not None:
        entry["handle"] = handle
    if layer is not None:
        entry["layer"] = layer
    return entry


def _safe_handle(entity: DXFGraphic) -> str | None:
    """``entity.dxf.handle``, or ``None`` if ``entity`` is not alive."""
    try:
        return str(entity.dxf.handle)
    except AttributeError:
        return None


def _safe_layer(entity: DXFGraphic) -> str | None:
    """``entity.dxf.layer``, or ``None`` if ``entity`` is not alive."""
    try:
        return str(entity.dxf.layer)
    except AttributeError:
        return None


def producer_info() -> dict[str, str]:
    """``producer`` object for a document this module computed.

    ``"engine.ezdxf"`` is the only enum member (``packages/schema/src/ndj/document.schema.json``
    ``$defs/producer``) that fits an ezdxf-based Python reader; see the W2-03
    report's Decisions for why ``fixtures_gen.stats`` reuses the same name
    with a distinguishing version string instead of the schema's unlisted
    ``"fixtures-gen"``.
    """
    return {"name": "engine.ezdxf", "version": ezdxf.__version__}


def _space_label(layout: Layout) -> str:
    return "MODEL" if layout.name == "Model" else f"PAPER:{layout.name}"


def _nfc_sorted_join(texts: list[str]) -> str:
    normalised = [unicodedata.normalize("NFC", t) for t in texts]
    return "\n".join(sorted(normalised))


def _text_hash(texts: list[str]) -> str:
    joined = _nfc_sorted_join(texts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def _polyline_length(points_xyb: list[tuple[float, float, float]], closed: bool) -> float:
    """``points_xyb``: ``(x, y, bulge)``. ``4 * atan(bulge)`` is the arc's
    included angle replacing the straight segment to the next vertex.
    """
    n = len(points_xyb)
    if n < 2:
        return 0.0
    seg_count = n if closed else n - 1
    total = 0.0
    for i in range(seg_count):
        x1, y1, bulge = points_xyb[i]
        x2, y2, _ = points_xyb[(i + 1) % n]
        chord = math.hypot(x2 - x1, y2 - y1)
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


def entity_length(entity: DXFGraphic) -> float:
    """Length in mm of one LENGTH_TYPES entity, or 0.0 for anything else."""
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


def _path_points(path: Any) -> list[tuple[float, float]] | None:
    verts = getattr(path, "vertices", None)
    if verts:
        return [(float(x), float(y)) for x, y, _b in verts]
    edges = getattr(path, "edges", None)
    if edges:
        pts: list[tuple[float, float]] = []
        for edge in edges:
            flat = getattr(edge, "flattening", None)
            if callable(flat):
                pts.extend((float(p.x), float(p.y)) for p in flat(FLATTEN_DISTANCE))
            else:  # pragma: no cover - defensive, every ezdxf edge type flattens
                start = getattr(edge, "start", None)
                if start is not None:
                    pts.append((float(start.x), float(start.y)))
        return pts
    return None


def _shoelace(points: list[tuple[float, float]]) -> float:
    n = len(points)
    if n < 3:
        return 0.0
    acc = 0.0
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        acc += x1 * y2 - x2 * y1
    return abs(acc) / 2.0


def hatch_area(entity: DXFGraphic) -> float:
    """Net HATCH area: external/outermost boundary paths add, holes subtract."""
    total = 0.0
    for path in entity.paths:
        points = _path_points(path)
        if not points or len(points) < 3:
            continue
        area = _shoelace(points)
        is_hole = not (path.path_type_flags & _EXTERNAL_OR_OUTERMOST)
        total += -area if is_hole else area
    return total


def _bbox_of(
    entities: list[DXFGraphic], diagnostics: list[dict[str, Any]]
) -> dict[str, list[float]] | None:
    """Union bbox of ``entities``, computed one entity at a time.

    ``ezdxf.bbox.extents()`` normally takes the whole list in one call, but
    that means a single bad entity takes the *entire* bucket's bbox down
    with it. Excluding just that entity keeps the rest of the union intact.
    Two ways one entity can fail here (module docstring):

    * ``ZeroDivisionError`` -- a zero-length OCS/direction vector.
    * ``AttributeError`` -- an INSERT whose bbox ``ezdxf.bbox.extents()``
      computes by disassembling into the block's geometry *and the INSERT's
      own ATTRIBs* (attributes are visual, so they count towards the bbox
      too). That disassembly does not check ``is_alive`` the way this
      module's own attrib loop does, so a dead ATTRIB (see
      ``compute_layer_stats``) blows up here even though ``entity`` itself
      -- the INSERT -- is perfectly alive.
    """
    box = BoundingBox()
    for entity in entities:
        try:
            entity_box = ezdxf.bbox.extents([entity])
        except ZeroDivisionError:
            diagnostics.append(
                _diagnostic(
                    DIAG_ZERO_LENGTH_OCS_VECTOR,
                    f"{entity.dxftype()} has a zero-length OCS/direction vector; "
                    "excluded from bbox",
                    handle=_safe_handle(entity),
                    layer=_safe_layer(entity),
                )
            )
            continue
        except AttributeError:
            diagnostics.append(
                _diagnostic(
                    DIAG_DEAD_ATTRIB,
                    f"{entity.dxftype()} #{_safe_handle(entity)} bbox computation touched "
                    "a destroyed sub-entity (duplicate-handle ATTRIB fixed up by ezdxf's "
                    "audit); excluded from bbox",
                    handle=_safe_handle(entity),
                    layer=_safe_layer(entity),
                )
            )
            continue
        if entity_box.has_data:
            box.extend(entity_box)
    if not box.has_data:
        return None
    return {
        "min": [round(float(box.extmin.x), 6), round(float(box.extmin.y), 6)],
        "max": [round(float(box.extmax.x), 6), round(float(box.extmax.y), 6)],
    }


@dataclass
class _Bucket:
    count_by_type: dict[str, int] = field(default_factory=dict)
    length_sum_mm: float = 0.0
    hatch_area_sum_mm2: float = 0.0
    texts: list[str] = field(default_factory=list)
    insert_by_block: dict[str, int] = field(default_factory=dict)
    bbox_entities: list[DXFGraphic] = field(default_factory=list)

    def add_top_level(self, entity: DXFGraphic, diagnostics: list[dict[str, Any]]) -> None:
        t = entity.dxftype()
        if t in _OWNED_ENTITY_TYPES:
            diagnostics.append(
                _diagnostic(
                    DIAG_UNEXPECTED_OWNED_ENTITY,
                    f"{t} appeared as a top-level entity (should be owned by another "
                    "entity); excluded from count_by_type per stats-definition.md",
                    handle=_safe_handle(entity),
                    layer=_safe_layer(entity),
                )
            )
            return
        self.count_by_type[t] = self.count_by_type.get(t, 0) + 1
        if t in LENGTH_TYPES:
            try:
                self.length_sum_mm += entity_length(entity)
            except ZeroDivisionError:
                diagnostics.append(
                    _diagnostic(
                        DIAG_ZERO_LENGTH_OCS_VECTOR,
                        f"{t} length computation failed on a zero-length OCS/direction "
                        "vector; excluded from length_sum_mm",
                        handle=_safe_handle(entity),
                        layer=_safe_layer(entity),
                    )
                )
        if t == "HATCH":
            try:
                self.hatch_area_sum_mm2 += hatch_area(entity)
            except ZeroDivisionError:
                diagnostics.append(
                    _diagnostic(
                        DIAG_ZERO_LENGTH_OCS_VECTOR,
                        "HATCH area computation failed on a zero-length OCS/direction "
                        "vector; excluded from hatch_area_sum_mm2",
                        handle=_safe_handle(entity),
                        layer=_safe_layer(entity),
                    )
                )
        if t in TEXT_TYPES:
            self.texts.append(entity.dxf.text if t == "TEXT" else entity.text)
        if t == "INSERT":
            name = unicodedata.normalize("NFC", entity.dxf.name)
            self.insert_by_block[name] = self.insert_by_block.get(name, 0) + 1
        self.bbox_entities.append(entity)

    def add_attrib(self, attrib: DXFGraphic) -> None:
        self.texts.append(attrib.dxf.text)
        self.bbox_entities.append(attrib)

    def to_aggregate(self, diagnostics: list[dict[str, Any]]) -> dict[str, Any]:
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
        bbox = _bbox_of(self.bbox_entities, diagnostics)
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


def compute_layer_stats(
    doc: Drawing,
    *,
    file_sha256: str,
    diagnostics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compute the full ``LayerStatsDocument`` for ``doc``.

    ``diagnostics``, when given, is appended to in place with one entry per
    entity this function had to skip or partially exclude instead of raising
    (module docstring: dead ATTRIBs, zero-length OCS/direction vectors).
    Never written into the returned document itself.
    """
    diag: list[dict[str, Any]] = diagnostics if diagnostics is not None else []
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
            bucket_for(space, layer).add_top_level(entity, diag)
            if entity.dxftype() == "INSERT":
                for attrib in entity.attribs:
                    if not attrib.is_alive:
                        diag.append(
                            _diagnostic(
                                DIAG_DEAD_ATTRIB,
                                f"INSERT #{entity.dxf.handle} on layer {layer!r} "
                                "references a destroyed ATTRIB (duplicate handle in "
                                "the source file, fixed up by ezdxf's audit); skipped",
                                handle=entity.dxf.handle,
                                layer=layer,
                            )
                        )
                        continue
                    attrib_layer = unicodedata.normalize("NFC", attrib.dxf.layer)
                    bucket_for(space, attrib_layer).add_attrib(attrib)

    bucket_docs = []
    for (space, layer), bucket in sorted(buckets.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        bucket_docs.append({"layer": layer, "space": space, "aggregate": bucket.to_aggregate(diag)})

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
        "totals": totals_bucket.to_aggregate(diag),
    }


__all__ = [
    "DIAG_DEAD_ATTRIB",
    "DIAG_UNEXPECTED_OWNED_ENTITY",
    "DIAG_ZERO_LENGTH_OCS_VECTOR",
    "FLATTEN_DISTANCE",
    "LENGTH_TYPES",
    "SCHEMA_VERSION",
    "TEXT_TYPES",
    "compute_layer_stats",
    "entity_length",
    "hatch_area",
    "producer_info",
]
