"""엔티티 서명: what "the same entity" means to the comparison (brief R1-06 §1).

The diff never compares two ezdxf entities directly. It compares two
:class:`EntitySignature` values -- a small, hashable, picklable summary of one
entity in *frame-local* coordinates -- and every matching stage, every fold
rule and every label is written against that summary rather than against the
DXF object model. Three reasons, in order of how much they cost to get wrong:

1. **Matching needs keys, not objects.** Pairing 350,000 before entities with
   350,000 after entities has to be a dictionary lookup, so the geometry has to
   collapse into something hashable. :attr:`EntitySignature.geom` is that key.
2. **A drawing that moved is still the same drawing.** Everything here is
   measured from the frame's lower-left corner (``local = world - frame.min``),
   so a set whose 후 files were all shifted by 50 metres compares clean
   (``fixtures/compare/S15_frame_shift``) instead of reporting every entity as
   moved.
3. **The fold rules need the parts, not the whole.** "레이어만 다름" and
   "해치를 같은 경계로 다시 그렸음" are questions about *which* part differs, so
   the signature keeps geometry, properties, text and the per-type extras
   (:attr:`hatch_key`, :attr:`dim_key`, :attr:`raw_text`) apart instead of
   hashing them into one blob.

Two derived keys drive the matching stages (``diff.py``):

* :attr:`geom` -- geometry *including* position. Two entities with the same
  ``(etype, layer, text, geom)`` are the same entity in the same place.
* :attr:`shape` -- the same geometry translated so its anchor sits at the
  origin. Two entities with the same shape are the same entity somewhere else,
  which is what makes 이동 detectable when the handles were renumbered.

Determinism (CLAUDE.md rule 6): every coordinate is rounded to
:data:`GEOM_DECIMALS` before it enters a key, every scalar to
:data:`SCALAR_DECIMALS`, ``-0.0`` is normalised to ``0.0``, and nothing is read
from a ``set`` or an unordered ``dict`` -- attribute maps and hatch vertex sets
are sorted before they are frozen into a tuple.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from typing import Any

import ezdxf.bbox
from ezdxf.document import Drawing
from ezdxf.math import Matrix44

from halo_engine.ingest.encoding import decode_escapes

#: Decimal places every coordinate is rounded to before it becomes part of a
#: key. Three is the contract's coordinate precision
#: (``docs/contracts/compare-dxf.md`` §8) and is two orders of magnitude finer
#: than the smallest move the rules care about (``minor.move_tolerance``,
#: 0.01mm), so it can absorb the float noise of the local-coordinate shift
#: without ever hiding a real difference.
GEOM_DECIMALS = 3

#: Decimal places for non-coordinate numbers: angles, scale factors, radii
#: ratios, dimension measurements. Six, matching the contract's "거리·각도는
#: 6자리".
SCALAR_DECIMALS = 6

#: How deep a block definition is expanded when its content is signed. Two
#: levels covers a title block inside an embedded XREF; deeper nesting is
#: summarised by the nested block's *name*, which still changes the parent's
#: signature when the child is renamed but not when the child's content
#: changes. :func:`block_signature` is recursive and memoised, so the practical
#: limit is the cycle guard rather than this constant.
MAX_BLOCK_DEPTH = 8

#: Types whose anchor is the lower-left corner of their own geometry rather
#: than their first point. A HATCH that was re-generated keeps its boundary but
#: may start at a different vertex (``fixtures/compare/S07_hatch_regen``), so
#: "the first point" is not a stable place to measure it from.
_MIN_ANCHOR_TYPES = frozenset({"HATCH"})


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _r(value: float, decimals: int = GEOM_DECIMALS) -> float:
    """Round, and turn ``-0.0`` into ``0.0`` (contract §8)."""
    rounded = round(float(value), decimals)
    return 0.0 if rounded == 0.0 else rounded


def _point(value: Any) -> tuple[float, float]:
    """Any ezdxf point-ish value as a rounded 2D tuple. Z is dropped (R1 is 2D)."""
    try:
        return (_r(value[0]), _r(value[1]))
    except (TypeError, IndexError, KeyError):
        return (_r(getattr(value, "x", 0.0)), _r(getattr(value, "y", 0.0)))


def _scalar(value: Any) -> Any:
    """One non-coordinate value, rounded if it is a number."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return _r(float(value), SCALAR_DECIMALS)
    if isinstance(value, str):
        return _nfc(value)
    return value


def _attrib_value(entity: Any) -> str:
    return decode_escapes(str(getattr(entity.dxf, "text", "") or ""))


# --------------------------------------------------------------------------- boxes


class BoxCache:
    """Bounding boxes, memoised per block definition.

    ``ezdxf.bbox.extents`` re-expands an INSERT's whole block on every call, so
    a drawing with 3,000 references to the same door costs 3,000 expansions of
    that door. The same memo ``compare/frames.py`` uses for assignment: a
    definition is measured once in its own coordinates and every reference
    costs four point transforms.

    Exact (not ``fast=True``) because these boxes are what the review screen
    zooms to and what the cloud mark is drawn around -- an arc clipped to its
    control points would put the cloud through the middle of a door swing.
    """

    def __init__(self, doc: Drawing) -> None:
        self._doc = doc
        self._cache = ezdxf.bbox.Cache()
        self._blocks: dict[str, tuple[float, float, float, float] | None] = {}

    def _block_box(self, name: str) -> tuple[float, float, float, float] | None:
        if name in self._blocks:
            return self._blocks[name]
        self._blocks[name] = None  # cycle guard: a block that inserts itself
        block = self._doc.blocks.get(name)
        if block is None:
            return None
        box: tuple[float, float, float, float] | None = None
        for entity in block:
            part = self._entity_box(entity)
            if part is None:
                continue
            box = part if box is None else _union(box, part)
        self._blocks[name] = box
        return box

    def _entity_box(self, entity: Any) -> tuple[float, float, float, float] | None:
        if entity.dxftype() == "INSERT":
            local = self._block_box(_nfc(str(entity.dxf.name)))
            if local is None:
                return None
            return _transform_box(local, entity.matrix44())
        measured = ezdxf.bbox.extents([entity], cache=self._cache)
        if not measured.has_data:
            return None
        return (
            float(measured.extmin.x),
            float(measured.extmin.y),
            float(measured.extmax.x),
            float(measured.extmax.y),
        )

    def box(self, entity: Any) -> tuple[float, float, float, float] | None:
        """World-space ``(x0, y0, x1, y1)`` of one entity, or ``None``."""
        try:
            return self._entity_box(entity)
        except Exception:  # noqa: BLE001 - a malformed entity must not fail the sheet
            return None


def _union(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _transform_box(
    box: tuple[float, float, float, float], matrix: Matrix44
) -> tuple[float, float, float, float]:
    corners = [(box[0], box[1]), (box[2], box[1]), (box[2], box[3]), (box[0], box[3])]
    points = [matrix.transform((x, y, 0.0)) for x, y in corners]
    xs = [float(p.x) for p in points]
    ys = [float(p.y) for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def union_boxes(boxes: list[list[float]]) -> list[float]:
    """Union of ``[x0, y0, x1, y1]`` boxes, rounded. Empty input gives a zero box."""
    if not boxes:
        return [0.0, 0.0, 0.0, 0.0]
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[2] for b in boxes)
    y1 = max(b[3] for b in boxes)
    return [_r(x0), _r(y0), _r(x1), _r(y1)]


# --------------------------------------------------------------------------- geometry


def _lwpolyline(entity: Any) -> tuple[list[tuple[float, float]], tuple[Any, ...]]:
    points: list[tuple[float, float]] = []
    bulges: list[float] = []
    widths: list[tuple[float, float]] = []
    for x, y, start_w, end_w, bulge in entity.get_points(format="xyseb"):
        points.append((_r(x), _r(y)))
        bulges.append(_r(bulge, SCALAR_DECIMALS))
        widths.append((_r(start_w, SCALAR_DECIMALS), _r(end_w, SCALAR_DECIMALS)))
    return points, (bool(entity.closed), tuple(bulges), tuple(widths))


def _polyline(entity: Any) -> tuple[list[tuple[float, float]], tuple[Any, ...]]:
    points = [_point(vertex.dxf.location) for vertex in entity.vertices]
    bulges = tuple(_r(float(vertex.dxf.bulge or 0.0), SCALAR_DECIMALS) for vertex in entity.vertices)
    return points, (bool(entity.is_closed), bulges)


def _hatch_boundary(entity: Any) -> list[tuple[float, float]]:
    """Every boundary vertex of a HATCH, in path order.

    Edge paths and polyline paths are both flattened to their vertices: the
    fold rule only asks whether the boundary is the same set of corners, and a
    re-generated hatch may describe the identical outline as edges where the
    original used a polyline.
    """
    points: list[tuple[float, float]] = []
    for path in entity.paths:
        vertices = getattr(path, "vertices", None)
        if vertices is not None:
            points.extend(_point(v) for v in vertices)
            continue
        for edge in getattr(path, "edges", []):
            for name in ("start", "end", "center"):
                value = getattr(edge, name, None)
                if value is not None:
                    points.append(_point(value))
    return points


def _text_points(entity: Any) -> list[tuple[float, float]]:
    points = [_point(entity.dxf.insert)]
    align = entity.dxf.get("align_point", None)
    if align is not None:
        points.append(_point(align))
    return points


def _insert_attribs(entity: Any) -> tuple[tuple[str, str], ...]:
    """``(tag, value)`` of every ATTRIB, sorted by tag (contract: no set order)."""
    pairs = sorted(
        (_nfc(str(attrib.dxf.tag)), _attrib_value(attrib)) for attrib in getattr(entity, "attribs", [])
    )
    return tuple(pairs)


def _dimension_points(entity: Any) -> tuple[list[tuple[float, float]], tuple[str, ...]]:
    """The definition points a DIMENSION actually carries, and which ones those are.

    A missing definition point must not become ``(0, 0)``: the points are
    translated into frame-local coordinates, so a placeholder origin would move
    with the frame and report every dimension on a shifted sheet as changed
    (``fixtures/compare/S15_frame_shift``). The names of the points that *are*
    present travel in the scalars instead, so gaining or losing one is still a
    difference.
    """
    names = ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5", "text_midpoint")
    points: list[tuple[float, float]] = []
    present: list[str] = []
    for name in names:
        value = entity.dxf.get(name, None)
        if value is None:
            continue
        points.append(_point(value))
        present.append(name)
    return points, tuple(present)


def _measurement(entity: Any) -> Any:
    try:
        value = entity.get_measurement()
    except Exception:  # noqa: BLE001 - ezdxf raises for exotic dimension types
        return None
    if isinstance(value, int | float):
        return _r(float(value), SCALAR_DECIMALS)
    if value is None:
        return None
    return str(value)


def _geometry(entity: Any, boxes: BoxCache) -> tuple[list[tuple[float, float]], tuple[Any, ...]]:
    """``(points, scalars)`` of one entity: what the diff calls its geometry.

    ``points`` are translated when the shape key is built, ``scalars`` are not,
    which is exactly the split between "where it is" and "what it is". A type
    this function does not know is described by its bounding box, so an exotic
    entity still participates in matching instead of being invisible.
    """
    etype = entity.dxftype()
    dxf = entity.dxf
    if etype == "LINE":
        return [_point(dxf.start), _point(dxf.end)], ()
    if etype == "LWPOLYLINE":
        return _lwpolyline(entity)
    if etype == "POLYLINE":
        return _polyline(entity)
    if etype == "CIRCLE":
        return [_point(dxf.center)], (_scalar(dxf.radius),)
    if etype == "ARC":
        return [_point(dxf.center)], (
            _scalar(dxf.radius),
            _scalar(dxf.start_angle),
            _scalar(dxf.end_angle),
        )
    if etype == "ELLIPSE":
        return [_point(dxf.center)], (
            _point(dxf.major_axis),
            _scalar(dxf.ratio),
            _scalar(dxf.start_param),
            _scalar(dxf.end_param),
        )
    if etype == "SPLINE":
        points = [_point(p) for p in entity.control_points]
        scalars = (
            _scalar(dxf.degree),
            tuple(_scalar(k) for k in entity.knots),
            tuple(_scalar(w) for w in entity.weights),
            bool(entity.closed),
        )
        return points, scalars
    if etype in {"TEXT", "ATTRIB", "ATTDEF"}:
        return _text_points(entity), (
            _scalar(dxf.height),
            _scalar(dxf.get("rotation", 0.0)),
            _scalar(dxf.get("halign", 0)),
            _scalar(dxf.get("valign", 0)),
            _scalar(dxf.get("width", 1.0)),
            _scalar(dxf.get("oblique", 0.0)),
            _scalar(dxf.get("style", "Standard")),
        )
    if etype == "MTEXT":
        return [_point(dxf.insert)], (
            _scalar(dxf.char_height),
            _scalar(dxf.get("rotation", 0.0)),
            _scalar(dxf.get("width", 0.0)),
            _scalar(dxf.get("attachment_point", 1)),
            _scalar(dxf.get("style", "Standard")),
        )
    if etype == "INSERT":
        return [_point(dxf.insert)], (
            _nfc(str(dxf.name)),
            _scalar(dxf.get("xscale", 1.0)),
            _scalar(dxf.get("yscale", 1.0)),
            _scalar(dxf.get("zscale", 1.0)),
            _scalar(dxf.get("rotation", 0.0)),
            _insert_attribs(entity),
        )
    if etype == "DIMENSION":
        points, present = _dimension_points(entity)
        return points, (
            _scalar(dxf.get("dimtype", 0)),
            _measurement(entity),
            _nfc(str(dxf.get("text", "") or "")),
            _scalar(dxf.get("dimstyle", "Standard")),
            present,
        )
    if etype == "HATCH":
        return _hatch_boundary(entity), (
            _nfc(str(dxf.get("pattern_name", "") or "")),
            bool(dxf.get("solid_fill", 0)),
            _scalar(dxf.get("pattern_scale", 1.0)),
            _scalar(dxf.get("pattern_angle", 0.0)),
            _scalar(dxf.get("hatch_style", 0)),
        )
    if etype == "LEADER":
        return [_point(v) for v in entity.vertices], ()
    if etype == "POINT":
        return [_point(dxf.location)], ()
    if etype in {"SOLID", "TRACE", "3DFACE"}:
        return [_point(dxf.get(name)) for name in ("vtx0", "vtx1", "vtx2", "vtx3")], ()
    box = boxes.box(entity)
    if box is None:
        return [], (etype,)
    return [(_r(box[0]), _r(box[1])), (_r(box[2]), _r(box[3]))], (etype,)


# --------------------------------------------------------------------------- signature


@dataclass(frozen=True)
class EntitySignature:
    """One entity of one 도곽, in frame-local millimetres.

    Frozen and built entirely from tuples, floats and strings: instances are
    hashed as dictionary keys during matching, and the whole comparison runs in
    a worker process (contract §6.2), so nothing here may hold an ezdxf object.
    """

    handle: str
    """Handle in its own working DXF -- the identity stage 3 matches on."""

    index: int
    """Position in the document, used to break every tie deterministically."""

    etype: str
    """DXF record name, e.g. ``LWPOLYLINE``."""

    layer: str
    """Layer name, NFC-normalised."""

    color: int
    """ACI colour; 256 is BYLAYER."""

    linetype: str
    """Linetype name; ``BYLAYER`` when unset."""

    lineweight: int
    """Lineweight in 1/100 mm; -1 is BYLAYER."""

    points: tuple[tuple[float, float], ...]
    """Geometry, frame-local, rounded. Translated to build :attr:`shape`."""

    scalars: tuple[Any, ...]
    """The position-independent half of the geometry (radius, angle, block name)."""

    anchor: tuple[float, float]
    """Where the entity is measured from: its first point, or its lower-left corner."""

    text: str | None
    """Plain text with formatting stripped, or ``None`` for a type that has none."""

    raw_text: str | None
    """Text exactly as stored -- what tells `mtext_format_only` from a real edit."""

    block_name: str | None
    """Block referenced by an INSERT, so ``blockdef`` can find its instances."""

    hatch_key: tuple[Any, ...] | None
    """``(pattern, solid, scale, angle, box, sorted vertices)`` for `hatch_regen`."""

    dim_key: tuple[Any, ...] | None
    """``(dimtype, measurement, override, sorted defpoints)`` for `dim_regen`."""

    box: tuple[float, float, float, float] | None = field(default=None)
    """Frame-local bounding box, or ``None`` when it could not be measured."""

    @property
    def geom(self) -> tuple[Any, ...]:
        """Geometry *including* position -- the stage-1 identity key."""
        return (self.points, self.scalars)

    @property
    def shape(self) -> tuple[Any, ...]:
        """Geometry translated to the origin -- the stage-4 이동 key."""
        ax, ay = self.anchor
        return (
            tuple((_r(x - ax), _r(y - ay)) for x, y in self.points),
            self.scalars,
        )

    def identity_key(self) -> tuple[Any, ...]:
        """``(etype, layer, text, geom)``: same entity, same place, same everything."""
        return (self.etype, self.layer, self.text, self.points, self.scalars)

    def fingerprint_key(self, tolerance: float) -> tuple[Any, ...]:
        """:meth:`identity_key` with coordinates quantised to the matching grid."""
        return (
            self.etype,
            self.layer,
            self.text,
            tuple((_q(x, tolerance), _q(y, tolerance)) for x, y in self.points),
            self.scalars,
        )

    def shape_key(self) -> tuple[Any, ...]:
        """``(etype, text, shape)``: the same thing drawn somewhere else.

        Layer is deliberately absent. An entity that was both moved and put on
        another layer is one change, not a removal plus an addition.
        """
        return (self.etype, self.text, self.shape)

    def properties(self) -> tuple[Any, ...]:
        return (self.layer, self.color, self.linetype, self.lineweight)


def _q(value: float, tolerance: float) -> int:
    """Quantise one coordinate onto the ``match.fingerprint_tolerance`` grid."""
    return int(round(value / tolerance)) if tolerance > 0 else int(round(value))


def signature_of(
    entity: Any, *, index: int, origin: tuple[float, float], boxes: BoxCache
) -> EntitySignature:
    """Sign one entity, expressed relative to ``origin`` (the frame's lower-left)."""
    etype = entity.dxftype()
    dxf = entity.dxf
    ox, oy = origin
    points, scalars = _geometry(entity, boxes)
    local = tuple((_r(x - ox), _r(y - oy)) for x, y in points)

    if etype in _MIN_ANCHOR_TYPES or not local:
        anchor = (
            (min(x for x, _ in local), min(y for _, y in local)) if local else (0.0, 0.0)
        )
    else:
        anchor = local[0]

    text: str | None = None
    raw_text: str | None = None
    if etype == "TEXT" or etype == "ATTRIB" or etype == "ATTDEF":
        raw_text = str(dxf.get("text", "") or "")
        text = decode_escapes(raw_text)
    elif etype == "MTEXT":
        raw_text = str(entity.text)
        text = _nfc(decode_escapes(entity.plain_text()))

    hatch_key: tuple[Any, ...] | None = None
    if etype == "HATCH":
        hatch_key = (*scalars, tuple(sorted(local)))
    dim_key: tuple[Any, ...] | None = None
    if etype == "DIMENSION":
        dim_key = (scalars[0], scalars[1], scalars[2], tuple(sorted(local)))

    world_box = boxes.box(entity)
    box = (
        (_r(world_box[0] - ox), _r(world_box[1] - oy), _r(world_box[2] - ox), _r(world_box[3] - oy))
        if world_box is not None
        else None
    )

    return EntitySignature(
        handle=str(dxf.handle or ""),
        index=index,
        etype=etype,
        layer=_nfc(str(dxf.get("layer", "0"))),
        color=int(dxf.get("color", 256)),
        linetype=_nfc(str(dxf.get("linetype", "BYLAYER"))),
        lineweight=int(dxf.get("lineweight", -1)),
        points=local,
        scalars=scalars,
        anchor=anchor,
        text=text,
        raw_text=raw_text,
        block_name=_nfc(str(dxf.name)) if etype == "INSERT" else None,
        hatch_key=hatch_key,
        dim_key=dim_key,
        box=box,
    )


def frame_signatures(
    doc: Drawing, *, handles: list[str], origin: tuple[float, float], boxes: BoxCache | None = None
) -> list[EntitySignature]:
    """Sign every model-space entity of one 도곽, in document order.

    Only the handles ``compare/frames.py`` assigned to the frame take part
    (brief: "도곽 밖 엔티티는 비교하지 않는다"). Document order is the tie-break
    every later stage falls back on, so it is preserved rather than sorted.
    """
    wanted = set(handles)
    cache = boxes if boxes is not None else BoxCache(doc)
    out: list[EntitySignature] = []
    for index, entity in enumerate(doc.modelspace()):
        handle = str(entity.dxf.handle or "")
        if handle not in wanted:
            continue
        out.append(signature_of(entity, index=index, origin=origin, boxes=cache))
    return out


# --------------------------------------------------------------------------- blocks


def block_signature(
    doc: Drawing, name: str, *, boxes: BoxCache, _seen: frozenset[str] | None = None, _depth: int = 0
) -> tuple[Any, ...]:
    """A hashable summary of one block *definition*, nested blocks expanded.

    Recursive on purpose: the change the user sees is "every door got shorter",
    and if the shortened line lives in a block nested inside ``DOOR_900`` a
    flat comparison of ``DOOR_900``'s own entities would report nothing. The
    nested definition is expanded into the parent's signature, so the change
    surfaces on the block that actually has instances on the sheet.

    Cycles (a block that inserts itself, which real drawings do contain) are
    cut by ``_seen``, and depth is capped by :data:`MAX_BLOCK_DEPTH`.
    """
    seen = _seen or frozenset()
    if name in seen or _depth > MAX_BLOCK_DEPTH:
        return ("<cycle>", name)
    block = doc.blocks.get(name)
    if block is None:
        return ("<missing>", name)
    seen = seen | {name}

    parts: list[tuple[Any, ...]] = []
    for entity in block:
        etype = entity.dxftype()
        points, scalars = _geometry(entity, boxes)
        layer = _nfc(str(entity.dxf.get("layer", "0")))
        text: str | None = None
        if etype in {"TEXT", "ATTRIB", "ATTDEF"}:
            text = decode_escapes(str(entity.dxf.get("text", "") or ""))
        elif etype == "MTEXT":
            text = _nfc(decode_escapes(entity.plain_text()))
        nested: tuple[Any, ...] = ()
        if etype == "INSERT":
            nested = block_signature(
                doc, _nfc(str(entity.dxf.name)), boxes=boxes, _seen=seen, _depth=_depth + 1
            )
        parts.append((etype, layer, text, tuple(points), scalars, nested))
    base = block.block.dxf.base_point if block.block is not None else (0.0, 0.0, 0.0)
    return (_point(base), tuple(parts))


__all__ = [
    "GEOM_DECIMALS",
    "MAX_BLOCK_DEPTH",
    "SCALAR_DECIMALS",
    "BoxCache",
    "EntitySignature",
    "block_signature",
    "frame_signatures",
    "signature_of",
    "union_boxes",
]
