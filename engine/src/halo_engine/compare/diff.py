"""엔티티 비교: two 도곽 in, a list of 변경 out (brief R1-06 §1, contract §3).

This is the module the whole product is about. Everything upstream exists to
put two sheets side by side in the same coordinate system, and everything
downstream (clusters, cloud marks, the revision table) is a presentation of
what :func:`diff_pair` decided. So the rules are written out here in full
rather than buried in helpers, and every threshold comes from ``compare.yaml``
(CLAUDE.md rule 7) -- there is no number in this file that a site engineer
cannot change.

**Coordinates.** Everything is frame-local: ``local = world - frame.bbox.min``.
A 후 file that was shifted 50 metres east compares clean, which is the whole
point of comparing sheets instead of files. ``offset = after.bbox.min -
before.bbox.min`` is reported so the DXF writer can bring 전 entities into the
후 sheet's world coordinates, and every ``bbox`` on a change is already in
those 후 world coordinates.

**Matching, in five stages.** Each stage only sees what the previous stages
left unpaired, so the strongest evidence wins and the weakest never gets the
chance to make a mistake:

1. *identity* -- same ``(etype, layer, text, geometry)`` at the same place.
   O(n) over a dictionary, and on a real revision it settles well over 99% of
   the sheet.
2. *fingerprint* -- the same key with coordinates quantised onto the
   ``match.fingerprint_tolerance`` (1mm) grid. Candidates are gathered from the
   **±1 neighbouring cells** as well as the entity's own, because a shift of a
   third of a millimetre across a cell boundary would otherwise lose the pair;
   the actual distance decides, and the closest pair is taken first.
3. *handle* -- the same handle and type. This is what recognises "the same
   entity, edited": the dimension whose measurement changed, the text that was
   re-typed, the wall that was moved to another layer. It runs *after* the
   position stages, not before, because a whole-sheet redraw recycles handles
   onto unrelated entities (``fixtures/compare/S12_whole_redraw``) and a
   handle-first pass would report a false change for every one of them.
4. *shape* -- the same geometry translated to the origin. Distance greater
   than the tolerance means ``moved``; this is what survives a redraw.
5. *proximity* -- the same type and layer within the tolerance of each other.
   The last resort, for an entity whose geometry was re-generated in place: a
   hatch rebuilt from the same boundary starting at a different vertex
   (``S07``), a text whose string changed after a redraw (``S12``).

Whatever is left is ``removed`` on the 전 side and ``added`` on the 후 side.

**Folding.** A difference that a person would not call a revision is still
recorded -- the review screen can show it -- but marked ``minor`` and kept out
of every cluster, cloud mark and revision-table row (contract §3). The rules
are in :func:`_facts` and :data:`_FOLD_ORDER`; several reasons on one change
are joined with ``+`` in the order the schema lists them.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ezdxf.document import Drawing

from halo_engine.compare.config import CompareConfig
from halo_engine.compare.frames import FrameRecord
from halo_engine.compare.signatures import (
    GEOM_DECIMALS,
    SCALAR_DECIMALS,
    BoxCache,
    EntitySignature,
    block_signature,
    frame_signatures,
    union_boxes,
)

#: ``change.kind`` (contract §3).
KIND_ADDED = "added"
KIND_REMOVED = "removed"
KIND_MODIFIED = "modified"
KIND_MOVED = "moved"
KIND_TEXT = "text"
KIND_DIMENSION = "dimension"
KIND_BLOCKDEF = "blockdef"

#: Which ``kind`` wins when one pair differs in several ways at once. A
#: dimension whose measurement changed also has different definition points;
#: calling that `modified` would hide the only fact the user cares about.
_KIND_PRIORITY = (KIND_MOVED, KIND_DIMENSION, KIND_TEXT, KIND_MODIFIED)

#: ``change.minor_reason`` values in the order the schema joins them with `+`
#: (``packages/schema/src/compare/change.schema.json``).
_FOLD_ORDER = (
    "move_le_0_01",
    "layer_only",
    "color_only",
    "linetype_only",
    "lineweight_only",
    "hatch_regen",
    "dim_regen",
    "mtext_format_only",
)

#: Entity types whose string content is a change of its own (`text`) rather
#: than one more property of the geometry.
_TEXTUAL = frozenset({"TEXT", "MTEXT", "ATTRIB", "ATTDEF"})

#: Ceiling on the candidate pairs one shape group may generate in stage 4.
#: A pathological sheet -- ten thousand unmatched identical bolts -- would
#: otherwise turn the stage quadratic. Beyond the cap the group is paired in
#: document order, which is still deterministic and still correct for the
#: common case where the two sides are the same list in the same order.
MAX_GROUP_PAIRS = 40_000

#: ``warnings`` code: the two 도곽 rectangles differ in size by more than this
#: fraction, so the sheets may not be the same sheet at the same scale. The
#: comparison continues (brief Defaults for ambiguity) -- the user decides.
FRAME_SIZE_TOLERANCE = 0.01
WARN_FRAME_SIZE_DIFFERS = "frame_size_differs"


def _r(value: float, decimals: int = GEOM_DECIMALS) -> float:
    rounded = round(float(value), decimals)
    return 0.0 if rounded == 0.0 else rounded


@dataclass
class ChangeRecord:
    """One ``change`` row, plus the handles the DXF writer needs to draw it.

    Picklable and made of built-ins only: the comparison runs in the job
    runner's ``ProcessPoolExecutor`` (contract §6.2) and these records are what
    comes back out of it.
    """

    seq: int
    """1-based position in the pair's deterministic order. ``id`` is ``ch<seq>``."""

    kind: str
    """One of the ``change.kind`` constants above."""

    etype: str
    """DXF type of the entity the change is about; ``INSERT`` for `blockdef`."""

    layer: str
    """Layer in its own drawing -- the 후 layer when there is a 후 side."""

    before_handle: str | None = None
    after_handle: str | None = None

    bbox: list[float] = field(default_factory=list)
    """``[x0, y0, x1, y1]`` in the 후 sheet's world coordinates (mm)."""

    delta: dict[str, Any] | None = None
    """What differs; shape depends on ``kind`` (``change.schema.json``)."""

    minor: bool = False
    minor_reason: str | None = None

    provenance: dict[str, Any] = field(default_factory=dict)
    """``{before?, after?}`` -- ``{file, handle, path, space}`` each (rule 5)."""

    instance_boxes: list[list[float]] = field(default_factory=list)
    """`blockdef` only: one 후 world box per affected INSERT, for clustering."""

    instance_handles: list[tuple[str | None, str | None]] = field(default_factory=list)
    """`blockdef` only: ``(before, after)`` handle of every affected INSERT."""

    @property
    def id(self) -> str:
        return f"ch{self.seq}"

    def to_row(self) -> dict[str, Any]:
        """The ``change`` columns ``repos.replace_changes`` inserts."""
        return {
            "seq": self.seq,
            "kind": self.kind,
            "etype": self.etype,
            "layer": self.layer,
            "before_handle": self.before_handle,
            "after_handle": self.after_handle,
            "bbox": list(self.bbox),
            "delta": dict(self.delta) if self.delta is not None else None,
            "minor": self.minor,
            "minor_reason": self.minor_reason,
            "provenance": dict(self.provenance),
        }


@dataclass
class DiffResult:
    """What :func:`diff_pair` produces for one 도곽 짝."""

    changes: list[ChangeRecord] = field(default_factory=list)
    """Every difference, minor ones included, in ``seq`` order."""

    offset: tuple[float, float] = (0.0, 0.0)
    """``after.bbox.min - before.bbox.min`` -- the sidecar's ``frame.offset_before``."""

    warnings: list[str] = field(default_factory=list)
    """Message codes raised while comparing, e.g. ``frame_size_differs``."""

    @property
    def minor_count(self) -> int:
        return sum(1 for change in self.changes if change.minor)

    @property
    def has_real_changes(self) -> bool:
        """``sheet_pair.status`` is ``changed`` only when something non-minor differs."""
        return any(not change.minor for change in self.changes)


# --------------------------------------------------------------------------- matching


@dataclass
class _Pairing:
    """Bookkeeping for the five matching stages."""

    matched: list[tuple[int, int]] = field(default_factory=list)
    """``(before index, after index)`` pairs, in the order the stages made them."""

    method: dict[tuple[int, int], str] = field(default_factory=dict)
    used_before: set[int] = field(default_factory=set)
    used_after: set[int] = field(default_factory=set)

    def take(self, before: int, after: int, method: str) -> None:
        self.matched.append((before, after))
        self.method[(before, after)] = method
        self.used_before.add(before)
        self.used_after.add(after)

    def free_before(self, count: int) -> list[int]:
        return [i for i in range(count) if i not in self.used_before]

    def free_after(self, count: int) -> list[int]:
        return [i for i in range(count) if i not in self.used_after]


def _distance(a: EntitySignature, b: EntitySignature) -> float:
    return math.hypot(b.anchor[0] - a.anchor[0], b.anchor[1] - a.anchor[1])


def _cell(anchor: tuple[float, float], tolerance: float) -> tuple[int, int]:
    return (int(math.floor(anchor[0] / tolerance)), int(math.floor(anchor[1] / tolerance)))


def _greedy(candidates: list[tuple[float, int, int]], pairing: _Pairing, method: str) -> None:
    """Assign candidate ``(distance, after index, before index)`` triples, closest first.

    Sorting on the two indices after the distance is what makes a tie
    deterministic: two identical entities the same distance away are taken in
    document order, never in whatever order a dictionary happened to yield
    (brief Defaults for ambiguity: "거리 동률이면 핸들 정렬 순").
    """
    for _distance_value, after_index, before_index in sorted(candidates):
        if before_index in pairing.used_before or after_index in pairing.used_after:
            continue
        pairing.take(before_index, after_index, method)


def _stage_identity(
    before: list[EntitySignature], after: list[EntitySignature], pairing: _Pairing
) -> None:
    """Stage 1: identical entity, identical place. One dictionary pass."""
    buckets: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for index, signature in enumerate(before):
        buckets[signature.identity_key()].append(index)
    cursor: dict[tuple[Any, ...], int] = defaultdict(int)
    for after_index, signature in enumerate(after):
        key = signature.identity_key()
        bucket = buckets.get(key)
        if not bucket:
            continue
        position = cursor[key]
        if position >= len(bucket):
            continue
        cursor[key] = position + 1
        pairing.take(bucket[position], after_index, "identity")


def _stage_fingerprint(
    before: list[EntitySignature],
    after: list[EntitySignature],
    pairing: _Pairing,
    tolerance: float,
) -> None:
    """Stage 2: quantised fingerprint, ±1 cells, actual distance decides."""
    buckets: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for index in pairing.free_before(len(before)):
        signature = before[index]
        buckets[(signature.fingerprint_key(tolerance), _cell(signature.anchor, tolerance))].append(
            index
        )
    if not buckets:
        return

    candidates: list[tuple[float, int, int]] = []
    for after_index in pairing.free_after(len(after)):
        signature = after[after_index]
        key = signature.fingerprint_key(tolerance)
        cx, cy = _cell(signature.anchor, tolerance)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for before_index in buckets.get((key, (cx + dx, cy + dy)), ()):
                    gap = _distance(before[before_index], signature)
                    if gap <= tolerance:
                        candidates.append((round(gap, SCALAR_DECIMALS), after_index, before_index))
    _greedy(candidates, pairing, "fingerprint")


def _boxes_overlap(a: EntitySignature, b: EntitySignature) -> bool:
    if a.box is None or b.box is None:
        return False
    return not (
        a.box[2] < b.box[0] or b.box[2] < a.box[0] or a.box[3] < b.box[1] or b.box[3] < a.box[1]
    )


def _stage_handle(
    before: list[EntitySignature],
    after: list[EntitySignature],
    pairing: _Pairing,
    tolerance: float,
) -> None:
    """Stage 3: same handle, same type -- the entity that was edited in place.

    Guarded by "the two are plausibly the same object": either their boxes
    overlap or their shapes are identical. Without the guard a redrawn sheet,
    which reissues every handle, would pair unrelated entities that happen to
    have inherited each other's numbers.
    """
    by_handle: dict[tuple[str, str], int] = {}
    for index in pairing.free_before(len(before)):
        signature = before[index]
        if signature.handle:
            by_handle.setdefault((signature.handle, signature.etype), index)
    if not by_handle:
        return
    for after_index in pairing.free_after(len(after)):
        signature = after[after_index]
        before_index = by_handle.get((signature.handle, signature.etype))
        if before_index is None or before_index in pairing.used_before:
            continue
        candidate = before[before_index]
        if (
            _boxes_overlap(candidate, signature)
            or candidate.shape == signature.shape
            or _distance(candidate, signature) <= tolerance
        ):
            pairing.take(before_index, after_index, "handle")


def _stage_shape(
    before: list[EntitySignature], after: list[EntitySignature], pairing: _Pairing
) -> None:
    """Stage 4: the same shape somewhere else. This is how 이동 survives a redraw."""
    buckets: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for index in pairing.free_before(len(before)):
        buckets[before[index].shape_key()].append(index)
    if not buckets:
        return

    after_groups: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for after_index in pairing.free_after(len(after)):
        after_groups[after[after_index].shape_key()].append(after_index)

    candidates: list[tuple[float, int, int]] = []
    for key, after_indices in after_groups.items():
        before_indices = buckets.get(key)
        if not before_indices:
            continue
        if len(before_indices) * len(after_indices) > MAX_GROUP_PAIRS:
            # Too many indistinguishable candidates to rank by distance; pair
            # them off in document order, which is what "the same list drawn
            # again" actually is.
            for before_index, after_index in zip(before_indices, after_indices, strict=False):
                pairing.take(before_index, after_index, "shape")
            continue
        for after_index in after_indices:
            for before_index in before_indices:
                gap = _distance(before[before_index], after[after_index])
                candidates.append((round(gap, SCALAR_DECIMALS), after_index, before_index))
    _greedy(candidates, pairing, "shape")


def _stage_proximity(
    before: list[EntitySignature],
    after: list[EntitySignature],
    pairing: _Pairing,
    tolerance: float,
) -> None:
    """Stage 5: same type and layer, within tolerance -- re-generated in place."""
    buckets: dict[tuple[Any, ...], list[int]] = defaultdict(list)
    for index in pairing.free_before(len(before)):
        signature = before[index]
        buckets[(signature.etype, signature.layer, _cell(signature.anchor, tolerance))].append(
            index
        )
    if not buckets:
        return

    candidates: list[tuple[float, int, int]] = []
    for after_index in pairing.free_after(len(after)):
        signature = after[after_index]
        cx, cy = _cell(signature.anchor, tolerance)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                key = (signature.etype, signature.layer, (cx + dx, cy + dy))
                for before_index in buckets.get(key, ()):
                    gap = _distance(before[before_index], signature)
                    if gap <= tolerance:
                        candidates.append((round(gap, SCALAR_DECIMALS), after_index, before_index))
    _greedy(candidates, pairing, "proximity")


def match_entities(
    before: list[EntitySignature], after: list[EntitySignature], config: CompareConfig
) -> _Pairing:
    """Run the five stages and return the pairing. Exposed for the unit tests."""
    tolerance = config.match.fingerprint_tolerance
    pairing = _Pairing()
    _stage_identity(before, after, pairing)
    _stage_fingerprint(before, after, pairing, tolerance)
    _stage_handle(before, after, pairing, tolerance)
    _stage_shape(before, after, pairing)
    _stage_proximity(before, after, pairing, tolerance)
    return pairing


# --------------------------------------------------------------------------- classify


@dataclass
class _Facts:
    """Everything that differs between one matched pair, before it is named."""

    move: tuple[float, float] | None = None
    distance: float = 0.0
    geometry: bool = False
    hatch_regen: bool = False
    dim_regen: bool = False
    dim_value: bool = False
    text: bool = False
    raw_text: bool = False
    properties: list[str] = field(default_factory=list)

    def any(self) -> bool:
        return bool(
            self.move is not None
            or self.geometry
            or self.hatch_regen
            or self.dim_regen
            or self.dim_value
            or self.text
            or self.raw_text
            or self.properties
        )


def _facts(before: EntitySignature, after: EntitySignature) -> _Facts:
    facts = _Facts()

    if before.layer != after.layer:
        facts.properties.append("layer_only")
    if before.color != after.color:
        facts.properties.append("color_only")
    if before.linetype != after.linetype:
        facts.properties.append("linetype_only")
    if before.lineweight != after.lineweight:
        facts.properties.append("lineweight_only")

    if before.text != after.text:
        facts.text = True
    elif before.raw_text != after.raw_text:
        facts.raw_text = True

    same_geometry = before.points == after.points and before.scalars == after.scalars
    if not same_geometry:
        if before.shape == after.shape:
            facts.move = (
                _r(after.anchor[0] - before.anchor[0]),
                _r(after.anchor[1] - before.anchor[1]),
            )
            facts.distance = round(_distance(before, after), SCALAR_DECIMALS)
        elif (
            before.etype == "HATCH"
            and before.hatch_key is not None
            and before.hatch_key == after.hatch_key
        ):
            facts.hatch_regen = True
        elif before.etype == "DIMENSION":
            if before.dim_key is not None and before.dim_key == after.dim_key:
                facts.dim_regen = True
            else:
                facts.dim_value = _dim_value_differs(before, after)
                facts.geometry = True
        else:
            facts.geometry = True
    elif before.etype == "DIMENSION" and _dim_value_differs(before, after):
        facts.dim_value = True

    return facts


def _dim_value_differs(before: EntitySignature, after: EntitySignature) -> bool:
    """A dimension's measurement or its override text -- what the sheet prints."""
    if before.dim_key is None or after.dim_key is None:
        return False
    return bool(before.dim_key[1] != after.dim_key[1] or before.dim_key[2] != after.dim_key[2])


def _classify(
    before: EntitySignature, after: EntitySignature, config: CompareConfig
) -> tuple[str, bool, str | None, dict[str, Any] | None] | None:
    """``(kind, minor, minor_reason, delta)`` for one matched pair, or ``None``.

    ``None`` means the two are the same entity in every way the contract cares
    about -- by far the most common answer, and the one that keeps a real
    revision's change list down to the handful of things a person actually did.
    """
    facts = _facts(before, after)
    if not facts.any():
        return None

    fold = set(config.minor.fold)
    reasons: list[str] = []
    unfolded = False

    if facts.move is not None:
        if facts.distance <= config.minor.move_tolerance:
            reasons.append("move_le_0_01")
        else:
            unfolded = True
    for reason in facts.properties:
        if reason in fold:
            reasons.append(reason)
        else:
            unfolded = True
    if facts.hatch_regen:
        if "hatch_regen" in fold:
            reasons.append("hatch_regen")
        else:
            unfolded = True
    if facts.dim_regen:
        if "dim_regen" in fold:
            reasons.append("dim_regen")
        else:
            unfolded = True
    if facts.raw_text:
        if "mtext_format_only" in fold:
            reasons.append("mtext_format_only")
        else:
            unfolded = True
    if facts.geometry or facts.text or facts.dim_value:
        unfolded = True

    candidates: list[str] = []
    if facts.move is not None and facts.distance > config.minor.move_tolerance:
        candidates.append(KIND_MOVED)
    if facts.dim_value:
        candidates.append(KIND_DIMENSION)
    if facts.text and before.etype in _TEXTUAL:
        candidates.append(KIND_TEXT)
    if not candidates:
        candidates.append(KIND_MOVED if facts.move is not None else KIND_MODIFIED)
    kind = next(name for name in _KIND_PRIORITY if name in candidates)

    delta: dict[str, Any] = {}
    if facts.move is not None:
        delta["move"] = [facts.move[0], facts.move[1]]
        delta["distance"] = facts.distance
    if facts.text:
        delta["before"] = before.text
        delta["after"] = after.text
    if facts.dim_value:
        delta["before"] = before.dim_key[1] if before.dim_key else None
        delta["after"] = after.dim_key[1] if after.dim_key else None
        delta["before_text"] = before.dim_key[2] if before.dim_key else None
        delta["after_text"] = after.dim_key[2] if after.dim_key else None
    for reason in facts.properties:
        name = reason.removesuffix("_only")
        delta[name] = [getattr(before, name), getattr(after, name)]
    if after.block_name:
        # The label says `블록 DOOR_900 이동 1,250mm 동` rather than just `블록
        # 이동`. `change` has no block column, and `delta` is the open field the
        # contract left for exactly this (change.schema.json $defs.delta).
        delta["block"] = after.block_name

    minor = not unfolded and bool(reasons)
    reason_text = (
        "+".join(name for name in _FOLD_ORDER if name in reasons) if minor and reasons else None
    )
    return kind, minor, reason_text, delta or None


# --------------------------------------------------------------------------- assembly


def _world_box(signature: EntitySignature, origin: tuple[float, float]) -> list[float] | None:
    if signature.box is None:
        return None
    return [
        _r(signature.box[0] + origin[0]),
        _r(signature.box[1] + origin[1]),
        _r(signature.box[2] + origin[0]),
        _r(signature.box[3] + origin[1]),
    ]


def _provenance(signature: EntitySignature, file_id: str) -> dict[str, Any]:
    return {"file": file_id, "handle": signature.handle, "path": [], "space": "MODEL"}


def _fallback_box(signature: EntitySignature, origin: tuple[float, float]) -> list[float]:
    """A box for an entity ``ezdxf.bbox`` could not measure: its own anchor point."""
    return [
        _r(signature.anchor[0] + origin[0]),
        _r(signature.anchor[1] + origin[1]),
        _r(signature.anchor[0] + origin[0]),
        _r(signature.anchor[1] + origin[1]),
    ]


def _blockdef_names(
    before_doc: Drawing,
    after_doc: Drawing,
    instances: dict[str, list[tuple[int, int]]],
    before_boxes: BoxCache,
    after_boxes: BoxCache,
) -> list[str]:
    """Block names whose *definition* differs between the two drawings.

    Only blocks that actually have a reference on this sheet: a definition
    nobody inserts is not a change anybody can see, and comparing every
    definition in a 68-file set would cost more than the sheets do.
    """
    changed: list[str] = []
    for name in sorted(instances):
        if before_doc.blocks.get(name) is None or after_doc.blocks.get(name) is None:
            continue
        if block_signature(before_doc, name, boxes=before_boxes) != block_signature(
            after_doc, name, boxes=after_boxes
        ):
            changed.append(name)
    return changed


def diff_pair(
    before_doc: Drawing,
    after_doc: Drawing,
    before_frame: FrameRecord,
    after_frame: FrameRecord,
    config: CompareConfig,
) -> DiffResult:
    """Compare one 도곽 짝 and return every difference (contract §6).

    ``before_doc``/``after_doc`` are the two working DXFs, already open;
    ``before_frame``/``after_frame`` are the ``sheet_frame`` records whose
    ``entity_handles`` say which entities belong to this sheet. The two
    documents are never written to.
    """
    before_origin = (before_frame.bbox[0], before_frame.bbox[1])
    after_origin = (after_frame.bbox[0], after_frame.bbox[1])
    offset = (_r(after_origin[0] - before_origin[0]), _r(after_origin[1] - before_origin[1]))

    warnings: list[str] = []
    if _sizes_differ(before_frame, after_frame):
        warnings.append(WARN_FRAME_SIZE_DIFFERS)

    before_boxes = BoxCache(before_doc)
    after_boxes = BoxCache(after_doc)
    before = frame_signatures(
        before_doc, handles=before_frame.entity_handles, origin=before_origin, boxes=before_boxes
    )
    after = frame_signatures(
        after_doc, handles=after_frame.entity_handles, origin=after_origin, boxes=after_boxes
    )

    pairing = match_entities(before, after, config)

    # Block definitions first: a `blockdef` change replaces the per-instance
    # records its references would otherwise produce (brief §1).
    instances: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for before_index, after_index in pairing.matched:
        name = after[after_index].block_name
        if name is not None and before[before_index].block_name == name:
            instances[name].append((before_index, after_index))
    changed_blocks = _blockdef_names(before_doc, after_doc, instances, before_boxes, after_boxes)
    suppressed = set(changed_blocks)

    records: list[ChangeRecord] = []

    for before_index, after_index in pairing.matched:
        before_signature = before[before_index]
        after_signature = after[after_index]
        if after_signature.block_name in suppressed:
            continue
        verdict = _classify(before_signature, after_signature, config)
        if verdict is None:
            continue
        kind, minor, reason, delta = verdict
        before_box = _world_box(before_signature, after_origin) or _fallback_box(
            before_signature, after_origin
        )
        after_box = _world_box(after_signature, after_origin) or _fallback_box(
            after_signature, after_origin
        )
        records.append(
            ChangeRecord(
                seq=0,
                kind=kind,
                etype=after_signature.etype,
                layer=after_signature.layer,
                before_handle=before_signature.handle,
                after_handle=after_signature.handle,
                bbox=union_boxes([before_box, after_box]),
                delta=delta,
                minor=minor,
                minor_reason=reason,
                provenance={
                    "before": _provenance(before_signature, before_frame.file_id),
                    "after": _provenance(after_signature, after_frame.file_id),
                },
            )
        )

    for name in changed_blocks:
        records.append(
            _blockdef_record(
                name, instances[name], before, after, before_frame, after_frame, after_origin
            )
        )

    for before_index in pairing.free_before(len(before)):
        signature = before[before_index]
        box = _world_box(signature, after_origin) or _fallback_box(signature, after_origin)
        records.append(
            ChangeRecord(
                seq=0,
                kind=KIND_REMOVED,
                etype=signature.etype,
                layer=signature.layer,
                before_handle=signature.handle,
                after_handle=None,
                bbox=box,
                delta={"block": signature.block_name} if signature.block_name else None,
                minor=False,
                minor_reason=None,
                provenance={"before": _provenance(signature, before_frame.file_id)},
            )
        )

    for after_index in pairing.free_after(len(after)):
        signature = after[after_index]
        box = _world_box(signature, after_origin) or _fallback_box(signature, after_origin)
        records.append(
            ChangeRecord(
                seq=0,
                kind=KIND_ADDED,
                etype=signature.etype,
                layer=signature.layer,
                before_handle=None,
                after_handle=signature.handle,
                bbox=box,
                delta={"block": signature.block_name} if signature.block_name else None,
                minor=False,
                minor_reason=None,
                provenance={"after": _provenance(signature, after_frame.file_id)},
            )
        )

    records.sort(key=_change_sort_key)
    for seq, record in enumerate(records, start=1):
        record.seq = seq

    return DiffResult(changes=records, offset=offset, warnings=warnings)


def _change_sort_key(record: ChangeRecord) -> tuple[Any, ...]:
    """Reading order: top row first, then left to right, then by handle.

    ``seq`` is written into the sidecar as ``ch<seq>`` and into the DXF as
    XDATA, so it has to be a function of the drawing rather than of the order
    the matching stages happened to finish in.
    """
    box = record.bbox or [0.0, 0.0, 0.0, 0.0]
    return (
        -box[3],
        box[0],
        record.kind,
        record.etype,
        record.after_handle or "",
        record.before_handle or "",
    )


def _blockdef_record(
    name: str,
    pairs: list[tuple[int, int]],
    before: list[EntitySignature],
    after: list[EntitySignature],
    before_frame: FrameRecord,
    after_frame: FrameRecord,
    after_origin: tuple[float, float],
) -> ChangeRecord:
    """One ``blockdef`` change standing for every reference to the block.

    The user's mental model is "the door block changed", not "six doors
    changed", and the drawing says the same thing: the instances are untouched.
    So one record carries ``delta.block`` and ``delta.instances``, and
    ``cluster.py`` decides whether that becomes one cloud mark or one per
    instance (brief Defaults for ambiguity: split above 30% of the frame's long
    side).
    """
    ordered = sorted(pairs, key=lambda item: (_handle_key(after[item[1]].handle), item[1]))
    boxes: list[list[float]] = []
    handles: list[tuple[str | None, str | None]] = []
    for before_index, after_index in ordered:
        signature = after[after_index]
        box = _world_box(signature, after_origin) or _fallback_box(signature, after_origin)
        boxes.append(box)
        handles.append((before[before_index].handle, signature.handle))

    first_before, first_after = ordered[0]
    representative = after[first_after]
    return ChangeRecord(
        seq=0,
        kind=KIND_BLOCKDEF,
        etype="INSERT",
        layer=representative.layer,
        before_handle=before[first_before].handle,
        after_handle=representative.handle,
        bbox=union_boxes(boxes) if boxes else [0.0, 0.0, 0.0, 0.0],
        delta={"block": name, "instances": len(ordered)},
        minor=False,
        minor_reason=None,
        provenance={
            "before": _provenance(before[first_before], before_frame.file_id),
            "after": _provenance(representative, after_frame.file_id),
        },
        instance_boxes=boxes,
        instance_handles=handles,
    )


def _handle_key(handle: str) -> tuple[int, str]:
    """Sort handles as the numbers they are: ``FB`` after ``F8``, ``100`` after ``FF``."""
    try:
        return (int(handle, 16), handle)
    except (TypeError, ValueError):
        return (1 << 62, handle or "")


def _sizes_differ(before: FrameRecord, after: FrameRecord) -> bool:
    """Frames more than 1% apart in either dimension (brief Defaults for ambiguity)."""
    for mine, theirs in ((before.width, after.width), (before.height, after.height)):
        reference = max(abs(mine), abs(theirs))
        if reference <= 0:
            continue
        if abs(mine - theirs) / reference > FRAME_SIZE_TOLERANCE:
            return True
    return False


__all__ = [
    "FRAME_SIZE_TOLERANCE",
    "KIND_ADDED",
    "KIND_BLOCKDEF",
    "KIND_DIMENSION",
    "KIND_MODIFIED",
    "KIND_MOVED",
    "KIND_REMOVED",
    "KIND_TEXT",
    "MAX_GROUP_PAIRS",
    "WARN_FRAME_SIZE_DIFFERS",
    "ChangeRecord",
    "DiffResult",
    "diff_pair",
    "match_entities",
]
