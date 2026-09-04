"""비교 DXF와 사이드카: the two files the viewer opens (``docs/contracts/compare-dxf.md``).

One 도곽 짝 produces exactly two artefacts, and this module writes both:

* ``compare.dxf`` -- an ordinary DXF the viewer draws with no special knowledge
  at all. Everything the review screen does is layer visibility: the 후 sheet on
  its own layers, what was added on ``__CMP_ADDED``, what was removed on
  ``__CMP_REMOVED``, the cloud marks and numbers on ``REV-<YYYYMMDD>``, and one
  invisible hit rectangle per cluster on ``__CMP_LABEL``.
* ``clusters.json`` -- the same comparison as data: the clusters, the changes,
  and the map from a handle *inside the compare DXF* to the cluster it belongs
  to, which is what turns a click in the viewer into a selected cloud mark.

**Why a new document.** The compare DXF is assembled entity by entity into a
fresh drawing rather than edited out of the 후 file, for two reasons: it must
contain one sheet and nothing else (contract §1), and the 전 file's blocks have
to arrive under a ``__B_`` prefix because a block of the same name may have a
different definition on each side (contract §3).

**Why blocks get cloned.** Layer visibility is the only thing the review screen
does, and a viewer decides visibility and colour per *drawn* entity. A moved
door is an INSERT, and what an INSERT draws are the entities of its block
definition -- which sit on ``A-DOOR`` whatever the reference sits on. So an
INSERT or DIMENSION that lands on a comparison layer is pointed at a relayered
clone of its block (:class:`_RelayeredBlocks`); otherwise "전" view would not
hide the added door and the door would not be red.

**Determinism** (contract §8) is not a nice-to-have here -- it is what lets a
re-run be diffed against the previous one, and it is an acceptance criterion.
Four things were found to break it and all four are handled:

1. ``ezdxf``'s ``Importer`` collects the layers, linetypes, styles and dimstyles
   it needs in ``set``s, so the table entries came out in hash order and two
   runs of the same comparison differed. Every table is therefore imported
   whole, in the source document's own order, *before* any entity is imported;
   the importer then finds everything it needs already present and adds nothing.
2. The CLASSES section is filled during ``write`` from
   ``entitydb.dxf_types_in_use()``, another ``set``
   (:func:`pin_classes_for_determinism`).
3. ``ezdxf`` regenerates ``$FINGERPRINTGUID`` and ``$VERSIONGUID`` and refreshes
   ``$TDUPDATE`` while writing, after any value we set. All three are rewritten
   in the serialised text.
4. ``ezdxf`` stamps its own version and the wall-clock time into two
   ``DICTIONARYVAR`` objects as it writes. The timestamp is replaced with
   ``run_date`` midnight in the same pass.

The first two were only visible across processes: inside one interpreter the
hash seed is fixed, and the job runner compares in a fresh pool worker
(``tests/compare/test_determinism.py`` runs the comparison under two explicit
``PYTHONHASHSEED`` values for exactly that reason).

The output is written as bytes with LF endings, so the file is identical on
Windows and macOS.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.addons.importer import Importer
from ezdxf.document import Drawing
from ezdxf.lldxf.const import DXFError
from ezdxf.render.arrows import ARROWS
from ezdxf.tools.juliandate import juliandate

from halo_engine.bundle.guard import assert_writable_path
from halo_engine.compare.cluster import ClusterRecord, build_clusters
from halo_engine.compare.config import CompareConfig, scale_factor
from halo_engine.compare.diff import KIND_BLOCKDEF, ChangeRecord, diff_pair
from halo_engine.compare.frames import FrameRecord

logger = logging.getLogger("halo_engine.compare.compare_dxf")

#: DXF version of the compare drawing: R2018 (contract §1).
DXF_VERSION = "R2018"

#: ``$INSUNITS`` 4 = millimetres (contract §1).
INSUNITS_MM = 4

#: The four layers the comparison owns (contract §2). Original layers keep
#: their own names and colours.
LAYER_ADDED = "__CMP_ADDED"
LAYER_REMOVED = "__CMP_REMOVED"
LAYER_LABEL = "__CMP_LABEL"

#: ACI colours of those layers (contract §2).
COLOR_ADDED = 1
COLOR_REMOVED = 4
COLOR_LABEL = 8

#: Prefix for every block definition that came from the 전 drawing (contract §3).
#: Always applied, even when the two definitions are identical, so that the
#: rule needs no exception and a reader can tell at a glance which side a block
#: belongs to. ``*`` is folded to ``_`` because a name that starts with ``*`` is
#: reserved for anonymous blocks.
BEFORE_BLOCK_PREFIX = "__B_"

#: Prefixes of the relayered clone blocks (contract §3). The name is built from
#: the block's name *in the compare document*, so a 전 block keeps its ``__B_``
#: too: ``__CMPR___B_DOOR_900``. See :class:`_RelayeredBlocks`.
ADDED_BLOCK_PREFIX = "__CMPA_"
REMOVED_BLOCK_PREFIX = "__CMPR_"

#: Longest name a DXF block table entry may carry.
MAX_BLOCK_NAME = 255

#: How much of the original name a clone keeps when the full name would
#: overflow :data:`MAX_BLOCK_NAME`; the rest is a sha1 prefix.
CLONE_NAME_KEEP = 200

#: BLOCK flags meaning "the content is in another file": ``BLK_XREF``,
#: ``BLK_XREF_OVERLAY``, ``BLK_EXTERNAL``. A clone never carries them.
_XREF_FLAGS = 4 | 8 | 16

#: XDATA application id every marker and every changed entity carries.
APPID = "HALO_CMP"

#: ``$FINGERPRINTGUID`` / ``$VERSIONGUID`` after pinning (contract §8).
ZERO_GUID = "{00000000-0000-0000-0000-000000000000}"

#: ezdxf's own ``CREATED_BY_EZDXF`` / ``WRITTEN_BY_EZDXF`` marker, written into
#: a ``DICTIONARYVAR`` as ``<version> @ <ISO timestamp>``. The timestamp is the
#: wall clock at the moment of writing, so it is replaced with ``run_date``.
_EZDXF_MARKER_RE = re.compile(
    r"^\S+ @ \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)

#: Header variables holding the drawing's timestamps. ``$TDCREATE`` survives
#: whatever :func:`pin_header_for_determinism` set; ``$TDUPDATE`` is refreshed
#: from the clock during ``write``, so the serialised text copies ``$TDCREATE``'s
#: value onto the other three.
_PINNED_TIME_VARS = ("$TDCREATE", "$TDUCREATE", "$TDUPDATE", "$TDUUPDATE")

#: Layout blocks are never renamed or re-imported: the target document has its
#: own.
_LAYOUT_BLOCK_PREFIXES = ("*Model_Space", "*Paper_Space")

SCHEMA_VERSION = "0.1"

CLUSTERS_JSON_NAME = "clusters.json"
COMPARE_DXF_NAME = "compare.dxf"


# --------------------------------------------------------------------------- results


@dataclass
class CompareDxfResult:
    """What :func:`write_compare_dxf` produced."""

    path: Path
    handle_to_cluster: dict[str, str] = field(default_factory=dict)
    """Compare-DXF handle -> ``c<number>`` (contract §7)."""

    change_handles: dict[int, dict[str, list[str]]] = field(default_factory=dict)
    """``change.seq`` -> ``{"added": [...], "removed": [...]}`` inside the compare DXF."""

    sha256: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ComparePairInput:
    """One unit of work for the ``compare.run`` job's process pool.

    Every field is a built-in, a picklable dataclass or a pydantic model:
    ezdxf documents never cross the process boundary (contract §6.2).
    """

    pair_id: str
    pair_key: str
    before_path: str
    after_path: str
    before_frame: FrameRecord
    after_frame: FrameRecord
    run_date: str
    out_dir: str
    bundle_root: str


@dataclass
class ComparePairOutput:
    """What one worker hands back for one 도곽 짝. Never an exception."""

    pair_id: str
    status: str = "same"
    changes: list[ChangeRecord] = field(default_factory=list)
    clusters: list[ClusterRecord] = field(default_factory=list)
    compare_dxf_path: str | None = None
    clusters_json_path: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    elapsed_s: float = 0.0
    entity_count: int = 0


# --------------------------------------------------------------------------- header


def pin_header_for_determinism(doc: Drawing, run_date: str) -> None:
    """Freeze every header variable that would otherwise carry the clock (contract §8).

    ``run_date`` is an explicit input of the comparison, never today's date
    (contract §11), so the drawing's creation and update stamps are that date at
    midnight UTC. The two GUIDs are also set here for completeness, but ezdxf
    regenerates them during ``write`` -- :func:`_normalise` has the last word.
    """
    stamp = juliandate(datetime.fromisoformat(f"{run_date}T00:00:00"))
    doc.header["$FINGERPRINTGUID"] = ZERO_GUID
    doc.header["$VERSIONGUID"] = ZERO_GUID
    for key in ("$TDCREATE", "$TDUPDATE", "$TDUCREATE", "$TDUUPDATE"):
        doc.header[key] = stamp
    doc.header["$TDINDWG"] = 0.0


def _normalise(text: str, run_date: str) -> str:
    """Rewrite the values ezdxf stamps while writing (contract §8).

    A DXF text file is a strict sequence of ``(group code, value)`` line pairs,
    so this walks the pairs rather than pattern-matching lines. Two things are
    replaced and nothing else:

    * the value of ``$FINGERPRINTGUID`` and ``$VERSIONGUID``, which ezdxf
      regenerates during ``write`` after anything :func:`pin_header_for_determinism`
      set, and ``$TDUPDATE``/``$TDUCREATE``/``$TDUUPDATE``, which it refreshes from
      the clock -- they take ``$TDCREATE``'s already-written text, so the value
      is formatted exactly the way ezdxf formats it;
    * the ``ezdxf`` version-and-timestamp marker, which lives in a
      ``DICTIONARYVAR`` object in the OBJECTS section and carries the wall
      clock down to the microsecond.

    Walking the pairs is what keeps a TEXT entity whose content happens to look
    like a GUID or like a version stamp untouched.
    """
    marker = f"{ezdxf.__version__} @ {run_date}T00:00:00+00:00"
    lines = text.split("\n")
    total = len(lines)
    record = ""
    stamp: str | None = None
    index = 0
    while index + 1 < total:
        code = lines[index].strip()
        if not code.isdigit():
            break  # not a tag stream any more; leave the rest exactly as written
        value = lines[index + 1]
        name = value.strip()
        if code == "0":
            record = name
        elif code == "9" and name in {"$FINGERPRINTGUID", "$VERSIONGUID"}:
            if index + 3 < total and lines[index + 2].strip() == "2":
                lines[index + 3] = ZERO_GUID
        elif code == "9" and name in _PINNED_TIME_VARS:
            if index + 3 < total and lines[index + 2].strip() == "40":
                if name == "$TDCREATE":
                    stamp = lines[index + 3]
                elif stamp is not None:
                    lines[index + 3] = stamp
        elif code == "1" and record == "DICTIONARYVAR" and _EZDXF_MARKER_RE.match(name):
            lines[index + 1] = marker
        index += 2
    return "\n".join(lines)


def pin_classes_for_determinism(doc: Drawing) -> None:
    """Put the CLASSES section in a fixed order (contract §8).

    ``ezdxf`` fills the section during ``write`` from
    ``entitydb.dxf_types_in_use()``, which is a ``set``: the same drawing came
    out with ``ACDBPLACEHOLDER`` before ``LAYOUT`` in one process and after it
    in the next, purely because of ``PYTHONHASHSEED``. Registering the classes
    up front and sorting them makes the order a property of the drawing.
    Re-registration during ``write`` is a no-op for classes that are already
    there, so the sorted order survives.

    CLASS records have no handles and DXF readers do not care about their
    order, so sorting them costs nothing but the determinism it buys.
    """
    doc.classes.add_required_classes(doc.dxfversion)
    doc.classes.classes = dict(sorted(doc.classes.classes.items()))


def serialize(doc: Drawing, run_date: str) -> bytes:
    """The compare DXF as bytes: written, normalised, UTF-8, LF."""
    pin_classes_for_determinism(doc)
    stream = io.StringIO()
    doc.write(stream)
    return _normalise(stream.getvalue(), run_date).encode("utf-8")


# --------------------------------------------------------------------------- assembly


def _is_layout_block(name: str) -> bool:
    return any(name.startswith(prefix) for prefix in _LAYOUT_BLOCK_PREFIXES)


def prefix_before_blocks(doc: Drawing) -> dict[str, str]:
    """Rename every block of the 전 drawing to ``__B_<name>`` and fix the references.

    Contract §3: the prefix is unconditional. The same name can mean two
    different definitions on the two sides -- that is exactly what a
    ``blockdef`` change *is* -- so the compare DXF can never let them share one
    table entry. Anonymous dimension geometry blocks (``*D1``) are renamed too,
    with their leading ``*`` folded to ``_``: they are per-drawing and would
    otherwise collide silently, drawing the 후 dimension where the 전 one
    should be.

    Mutates ``doc`` in place -- it is the worker's own copy of the working DXF,
    never the file on disk (CLAUDE.md rule 1).
    """
    taken = {block.name for block in doc.blocks}
    mapping: dict[str, str] = {}
    for name in sorted(block.name for block in doc.blocks):
        if _is_layout_block(name):
            continue
        candidate = BEFORE_BLOCK_PREFIX + name.replace("*", "_")
        while candidate in taken:
            candidate += "_"
        taken.add(candidate)
        mapping[name] = candidate

    for old, new in mapping.items():
        doc.blocks.rename_block(old, new)

    def _retarget(container: Any) -> None:
        for entity in container:
            etype = entity.dxftype()
            if etype == "INSERT":
                name = str(entity.dxf.name)
                if name in mapping:
                    entity.dxf.name = mapping[name]
            elif etype == "DIMENSION":
                geometry = entity.dxf.get("geometry", None)
                if geometry in mapping:
                    entity.dxf.geometry = mapping[geometry]

    _retarget(doc.modelspace())
    for block in doc.blocks:
        _retarget(block)
    return mapping


def _arrow_names(doc: Drawing) -> list[str]:
    """Every arrow a dimension style of ``doc`` asks for, in table order."""
    names: list[str] = []
    for dimstyle in doc.dimstyles:
        for attribute in ("dimblk", "dimblk1", "dimblk2", "dimldrblk"):
            value = str(dimstyle.dxf.get(attribute, "") or "")
            if value and value not in names:
                names.append(value)
    return names


def _import_one(importer: Importer, entity: Any, layout: Any) -> Any | None:
    """Import one entity and hand back the copy, or ``None`` for an unsupported type.

    ``Importer`` appends to the target layout and reports nothing, so the copy
    is identified by the layout having grown. Needed because almost everything
    downstream -- the layer move, the XDATA, ``handle_to_cluster`` -- is about
    the *new* entity.
    """
    before = len(layout)
    importer.import_entity(entity, layout)
    if len(layout) == before:
        return None
    copy = layout[-1]
    if entity.dxftype() == "DIMENSION":
        geometry = entity.dxf.get("geometry", None)
        if geometry:
            copy.dxf.geometry = importer.import_block(str(geometry), rename=False)
    return copy


def _set_xdata(entity: Any, values: list[tuple[str, Any]]) -> None:
    entity.set_xdata(APPID, [(1000, f"{key}={value}") for key, value in values])


def _ensure_layers(target: Drawing, config: CompareConfig, revision_layer: str) -> None:
    """The four comparison layers, in the fixed order of contract §2."""
    for name, color in (
        (LAYER_ADDED, COLOR_ADDED),
        (LAYER_REMOVED, COLOR_REMOVED),
        (revision_layer, config.cloud.color),
        (LAYER_LABEL, COLOR_LABEL),
    ):
        if name in target.layers:
            continue
        layer = target.layers.add(name, color=color)
        if name == LAYER_LABEL:
            # A hit region, not a drawing: never displayed, never plotted
            # (contract §2). The viewer reaches it by handle, not by sight.
            layer.off()
            layer.dxf.plot = 0


def _mark_one(entity: Any, layer: str) -> None:
    """Put one entity on ``layer`` and hand every appearance back to the layer."""
    entity.dxf.layer = layer
    entity.dxf.color = 256  # BYLAYER
    entity.dxf.linetype = "BYLAYER"
    if entity.dxf.is_supported("lineweight"):
        entity.dxf.lineweight = -1  # BYLAYER
    # A 24-bit true colour outranks ``color`` in every reader, so BYLAYER only
    # takes effect once it is gone (R1-06b).
    entity.dxf.discard("true_color")


def _mark_layer(entity: Any, layer: str) -> None:
    """Move an entity onto a comparison layer and let the layer own its colour.

    Contract §2: an entity that keeps its own red stays red on the cyan
    ``__CMP_REMOVED`` layer, which defeats the whole point of the two colours.
    The original layer survives in XDATA.

    An INSERT's ATTRIBs are separate entities that are drawn with the
    reference, so they are moved with it.
    """
    _mark_one(entity, layer)
    for attrib in getattr(entity, "attribs", []):
        _mark_one(attrib, layer)


# ------------------------------------------------------------------- clone blocks


class _RelayeredBlocks:
    """Clone blocks whose every entity sits on one comparison layer (contract §3).

    The viewer decides visibility and colour **per drawn entity**, and what an
    INSERT draws are the entities of its block *definition*, which keep their
    own layers (``A-DOOR``, ``0``) and their own colours. Moving the reference
    to ``__CMP_ADDED`` therefore does neither of the two things contract §2
    promises: turning ``__CMP_ADDED`` off in "전" view does not hide the added
    door, and the door is not red. A door or window moving is the most common
    revision there is, so the fix has to be in the drawing rather than in the
    viewer (CLAUDE.md rule 4, R1-08 found it).

    So every INSERT and DIMENSION that lands on a comparison layer is pointed
    at a *clone* of its block whose entities are all on that layer with BYLAYER
    colour, linetype and lineweight. Nested INSERTs inside a clone reference
    clones of their own blocks, recursively.

    Two clones at most exist per block -- one per side -- and every reference
    of that block on that side shares it, so the file grows with the number of
    changed block *kinds*, not with the number of changed instances. The
    memo that enforces that (``_names``) is also the cycle guard: the clone's
    name is recorded before its entities are walked, so a block that reaches
    itself finds the name already there instead of recursing forever.

    Blocks that keep their original layer are untouched: an unchanged door is
    still drawn from ``DOOR_900``.
    """

    def __init__(self, doc: Drawing) -> None:
        self._doc = doc
        self._names: dict[tuple[str, str], str] = {}
        self._taken = {block.name for block in doc.blocks}
        self.warnings: list[str] = []

    def clone(self, name: str, layer: str) -> str:
        """The name of ``name``'s clone for ``layer``, creating it on first use."""
        key = (layer, name)
        known = self._names.get(key)
        if known is not None:
            return known
        source = self._doc.blocks.get(name)
        if source is None:
            return name
        clone_name = self._reserve(name, layer)
        # Recorded *before* the walk: a block that references itself, directly
        # or through another block, must find a name rather than recurse.
        self._names[key] = clone_name
        target = self._new_block(clone_name, source)
        for entity in source:
            try:
                copy = entity.copy()
            except DXFError:  # a DXF type ezdxf keeps as raw tags
                self.warnings.append(f"uncopyable_block_entity:{entity.dxftype()}")
                continue
            _mark_layer(copy, layer)
            etype = copy.dxftype()
            if etype == "INSERT":
                copy.dxf.name = self.clone(str(copy.dxf.name), layer)
            elif etype == "DIMENSION":
                geometry = copy.dxf.get("geometry", None)
                if geometry:
                    copy.dxf.geometry = self.clone(str(geometry), layer)
            # The clone's contents are drawing, not hit-test targets: the
            # cluster is found through the reference's handle (contract §7).
            copy.discard_xdata(APPID)
            target.add_entity(copy)
        return clone_name

    def _new_block(self, clone_name: str, source: Any) -> Any:
        """An empty block with ``source``'s base point, flags and units.

        The three flags that say "this block's content lives in another file"
        are dropped: the clone carries copies, and an empty block claiming to
        be an unresolved XREF is a drawing a reader cannot open.
        """
        origin = (0.0, 0.0, 0.0)
        head = getattr(source.block, "dxf", None)
        attribs = {"flags": head.get("flags", 0) & ~_XREF_FLAGS} if head is not None else {}
        base_point = head.get("base_point", origin) if head is not None else origin
        block = self._doc.blocks.new(clone_name, base_point=base_point, dxfattribs=attribs)
        for attribute in ("units", "scale", "explode"):
            value = source.block_record.dxf.get(attribute, None)
            if value is not None:
                block.block_record.dxf.set(attribute, value)
        return block

    def _reserve(self, name: str, layer: str) -> str:
        """A free, deterministic clone name for ``name`` on ``layer``.

        ``*`` is folded to ``_`` the way :func:`prefix_before_blocks` folds it:
        a leading ``*`` is reserved for anonymous blocks and DXF forbids it
        anywhere else in a table name, so ``*D3`` becomes ``__CMPA__D3``.
        """
        prefix = ADDED_BLOCK_PREFIX if layer == LAYER_ADDED else REMOVED_BLOCK_PREFIX
        stem = name.replace("*", "_")
        candidate = f"{prefix}{stem}"
        if len(candidate) > MAX_BLOCK_NAME:
            digest = hashlib.sha1(name.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
            candidate = f"{prefix}{stem[:CLONE_NAME_KEEP]}_{digest}"
        # A drawing that already holds a block of that name (a previous run's
        # output fed back in, say) gets a numbered one instead -- trimmed, so
        # the way out of a collision cannot itself overflow the table.
        unique = candidate
        attempt = 0
        while unique in self._taken:
            attempt += 1
            tail = f"_{attempt}"
            unique = candidate[: MAX_BLOCK_NAME - len(tail)] + tail
        self._taken.add(unique)
        return unique


def relayer_block_references(doc: Drawing) -> _RelayeredBlocks:
    """Point every comparison-layer INSERT and DIMENSION at a relayered clone.

    Runs over the modelspace of the finished compare document, after the
    comparison layers have been assigned and before ``audit()``: what it needs
    to know is exactly "which references ended up on ``__CMP_ADDED`` or
    ``__CMP_REMOVED``", and that is a property of the drawing at that moment.

    The requests are sorted before any clone is made, so the block table order
    is a property of the comparison and not of the order the references happen
    to sit in the modelspace (contract §8).
    """
    relayer = _RelayeredBlocks(doc)
    requests: list[tuple[str, str, Any]] = []
    for entity in doc.modelspace():
        layer = str(entity.dxf.get("layer", "0"))
        if layer not in (LAYER_ADDED, LAYER_REMOVED):
            continue
        etype = entity.dxftype()
        if etype == "INSERT":
            name = str(entity.dxf.get("name", "") or "")
        elif etype == "DIMENSION":
            name = str(entity.dxf.get("geometry", "") or "")
        else:
            continue
        if name and name in doc.blocks:
            requests.append((layer, name, entity))

    for layer, name, entity in sorted(requests, key=lambda item: (item[0], item[1])):
        clone_name = relayer.clone(name, layer)
        if entity.dxftype() == "INSERT":
            entity.dxf.name = clone_name
        else:
            entity.dxf.geometry = clone_name
    return relayer


def _change_sides(changes: list[ChangeRecord]) -> tuple[dict[str, list[int]], dict[str, list[int]]]:
    """``before handle -> change seqs`` and ``after handle -> change seqs``.

    A ``blockdef`` change claims every instance handle, not just the
    representative pair, because every instance is drawn twice in the compare
    DXF -- once with the 전 definition and once with the 후 one (contract §3).
    """
    before: dict[str, list[int]] = {}
    after: dict[str, list[int]] = {}
    for change in changes:
        pairs: list[tuple[str | None, str | None]] = (
            list(change.instance_handles)
            if change.kind == KIND_BLOCKDEF and change.instance_handles
            else [(change.before_handle, change.after_handle)]
        )
        for before_handle, after_handle in pairs:
            if before_handle:
                before.setdefault(before_handle, []).append(change.seq)
            if after_handle:
                after.setdefault(after_handle, []).append(change.seq)
    return before, after


def write_compare_dxf(
    *,
    before_doc: Drawing,
    after_doc: Drawing,
    before_frame: FrameRecord,
    after_frame: FrameRecord,
    changes: list[ChangeRecord],
    clusters: list[ClusterRecord],
    config: CompareConfig,
    run_date: str,
    offset: tuple[float, float],
    out_path: Path,
    allowed_roots: list[Path] | None = None,
) -> CompareDxfResult:
    """Assemble and write one pair's compare DXF (contract §1-§5, §8).

    ``before_doc`` is mutated: its blocks are renamed with the ``__B_`` prefix
    before they are imported. It is the worker's own in-memory copy.
    """
    revision_layer = config.revision_layer(run_date)
    factor = scale_factor(after_frame.scale_denominator)
    warnings: list[str] = []

    before_by_handle, after_by_handle = _change_sides(changes)
    by_seq = {change.seq: change for change in changes}
    cluster_of_seq: dict[int, str] = {}
    for cluster in clusters:
        for seq in cluster.change_seqs:
            cluster_of_seq.setdefault(seq, cluster.id)

    prefix_before_blocks(before_doc)

    target = ezdxf.new(DXF_VERSION, setup=False)
    target.header["$INSUNITS"] = INSUNITS_MM
    target.appids.add(APPID)

    after_importer = Importer(after_doc, target)
    before_importer = Importer(before_doc, target)

    # Tables first, whole and in source order: the importer's own resource
    # collection runs off ``set``s and would otherwise decide the table order
    # by hash seed (module docstring, reason 1).
    after_importer.import_tables()
    before_importer.import_tables()
    for name in sorted(set(_arrow_names(after_doc)) | set(_arrow_names(before_doc))):
        if ARROWS.is_acad_arrow(name):
            target.acquire_arrow(name)
    after_importer.import_blocks(
        [block.name for block in after_doc.blocks if not _is_layout_block(block.name)],
        rename=False,
    )
    _ensure_layers(target, config, revision_layer)

    msp = target.modelspace()
    handle_to_cluster: dict[str, str] = {}
    change_handles: dict[int, dict[str, list[str]]] = {}

    def _record(seq: int, side: str, handle: str) -> None:
        entry = change_handles.setdefault(seq, {"added": [], "removed": []})
        entry[side].append(handle)
        cluster_id = cluster_of_seq.get(seq)
        if cluster_id is not None:
            handle_to_cluster[handle] = cluster_id

    # 1. the 후 sheet, in document order (contract §8).
    after_handles = set(after_frame.entity_handles)
    entity_count = 0
    for entity in after_doc.modelspace():
        handle = str(entity.dxf.handle or "")
        if handle not in after_handles:
            continue
        copy = _import_one(after_importer, entity, msp)
        if copy is None:
            warnings.append(f"unsupported_entity:{entity.dxftype()}")
            continue
        entity_count += 1
        seqs = after_by_handle.get(handle, [])
        if not seqs:
            continue
        seq = seqs[0]
        change = by_seq[seq]
        original_layer = str(entity.dxf.get("layer", "0"))
        if not change.minor:
            _mark_layer(copy, LAYER_ADDED)
            _record(seq, "added", str(copy.dxf.handle))
        _set_xdata(
            copy,
            _xdata_values(
                change=change,
                cluster_id=cluster_of_seq.get(seq),
                side="after",
                original_layer=original_layer,
                original_handle=handle,
            ),
        )

    # 2. the 전 entities the changes need, translated into the 후 sheet's
    #    coordinates (contract §1).
    before_handles = set(before_frame.entity_handles)
    for entity in before_doc.modelspace():
        handle = str(entity.dxf.handle or "")
        if handle not in before_handles:
            continue
        seqs = before_by_handle.get(handle, [])
        if not seqs:
            continue
        seq = seqs[0]
        change = by_seq[seq]
        if change.minor:
            # A minor change is represented by the 후 entity on its own layer
            # (contract §2); drawing the 전 state as well would put a cyan ghost
            # under every re-generated hatch.
            continue
        copy = _import_one(before_importer, entity, msp)
        if copy is None:
            warnings.append(f"unsupported_entity:{entity.dxftype()}")
            continue
        if offset != (0.0, 0.0):
            copy.translate(offset[0], offset[1], 0.0)
        _mark_layer(copy, LAYER_REMOVED)
        _record(seq, "removed", str(copy.dxf.handle))
        _set_xdata(
            copy,
            _xdata_values(
                change=change,
                cluster_id=cluster_of_seq.get(seq),
                side="before",
                original_layer=str(entity.dxf.get("layer", "0")),
                original_handle=handle,
            ),
        )

    after_importer.finalize()
    before_importer.finalize()

    # 3. cloud marks, badges and hit regions, in cluster-number order.
    for cluster in clusters:
        _draw_cluster(msp, cluster, revision_layer=revision_layer)
        handle_to_cluster[str(cluster.cloud["handle"])] = cluster.id
        handle_to_cluster[str(cluster.badge["shape_handle"])] = cluster.id
        handle_to_cluster[str(cluster.badge["text_handle"])] = cluster.id
        label_handle = _draw_label(msp, cluster, config, factor)
        handle_to_cluster[label_handle] = cluster.id

    # 4. block references on a comparison layer are redrawn from a clone of
    #    their block whose contents are on that layer too (contract §3). Last,
    #    so that every modelspace handle -- and therefore ``handle_to_cluster``
    #    -- is exactly what it was before the clones existed.
    warnings.extend(relayer_block_references(target).warnings)

    pin_header_for_determinism(target, run_date)
    audit = target.audit()
    if audit.errors:
        warnings.extend(f"audit:{error.code}" for error in audit.errors)
        logger.warning("compare DXF audit reported %d errors", len(audit.errors))

    payload = serialize(target, run_date)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    assert_writable_path(out_path, allowed_roots=allowed_roots or [out_path.parent])
    out_path.write_bytes(payload)

    return CompareDxfResult(
        path=out_path,
        handle_to_cluster=dict(sorted(handle_to_cluster.items())),
        change_handles={
            seq: {side: sorted(values) for side, values in sides.items() if values}
            for seq, sides in sorted(change_handles.items())
        },
        sha256=hashlib.sha256(payload).hexdigest(),
        warnings=warnings,
    )


def _xdata_values(
    *,
    change: ChangeRecord,
    cluster_id: str | None,
    side: str,
    original_layer: str,
    original_handle: str,
) -> list[tuple[str, Any]]:
    """The ``key=value`` tags of contract §4, in the order the contract lists them."""
    values: list[tuple[str, Any]] = []
    if cluster_id is not None:
        values.append(("cluster", cluster_id.removeprefix("c")))
    values.extend(
        [
            ("change", change.id),
            ("kind", change.kind),
            ("side", side),
            ("orig_layer", original_layer),
            ("orig_handle", original_handle),
            ("minor", 1 if change.minor else 0),
        ]
    )
    return values


def _draw_cluster(layout: Any, cluster: ClusterRecord, *, revision_layer: str) -> None:
    """The cloud LWPOLYLINE and the numbered triangle (contract §5)."""
    cloud = layout.add_lwpolyline(
        [(point[0], point[1], 0.0, 0.0, point[2]) for point in cluster.cloud["points"]],
        format="xyseb",
        close=True,
        dxfattribs={"layer": revision_layer},
    )
    cluster.cloud["handle"] = str(cloud.dxf.handle)
    _set_xdata(cloud, [("cluster", cluster.number), ("role", "cloud")])

    shape = layout.add_lwpolyline(
        [(x, y) for x, y in cluster.badge_points],
        format="xy",
        close=True,
        dxfattribs={"layer": revision_layer},
    )
    cluster.badge["shape_handle"] = str(shape.dxf.handle)
    _set_xdata(shape, [("cluster", cluster.number), ("role", "badge_shape")])

    text = layout.add_text(
        str(cluster.number),
        dxfattribs={
            "layer": revision_layer,
            "height": cluster.badge_text_height,
            "style": "Standard",
        },
    )
    center = (cluster.badge["center"][0], cluster.badge["center"][1])
    text.set_placement(center, align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
    cluster.badge["text_handle"] = str(text.dxf.handle)
    _set_xdata(text, [("cluster", cluster.number), ("role", "badge_text")])


def _draw_label(layout: Any, cluster: ClusterRecord, config: CompareConfig, factor: float) -> str:
    """One invisible closed rectangle per cluster: the viewer's hit region (contract §2)."""
    margin = config.cloud.margin * factor
    x0, y0, x1, y1 = cluster.bbox
    label = layout.add_lwpolyline(
        [
            (round(x0 - margin, 3), round(y0 - margin, 3)),
            (round(x1 + margin, 3), round(y0 - margin, 3)),
            (round(x1 + margin, 3), round(y1 + margin, 3)),
            (round(x0 - margin, 3), round(y1 + margin, 3)),
        ],
        format="xy",
        close=True,
        dxfattribs={"layer": LAYER_LABEL},
    )
    _set_xdata(label, [("cluster", cluster.number), ("role", "label")])
    return str(label.dxf.handle)


# --------------------------------------------------------------------------- sidecar


def build_sidecar(
    *,
    pair_id: str,
    pair_key: str,
    run_date: str,
    layer: str,
    after_frame: FrameRecord,
    offset: tuple[float, float],
    changes: list[ChangeRecord],
    clusters: list[ClusterRecord],
    handle_to_cluster: dict[str, str],
    change_handles: dict[int, dict[str, list[str]]],
    decisions: dict[int, tuple[str, str | None, str | None]] | None = None,
) -> dict[str, Any]:
    """The ``clusters.json`` document (contract §7).

    ``decisions`` carries ``{number: (decision, user_label, note)}`` forward
    from the database when a re-comparison inherited the user's review; the
    file is otherwise written with everything ``pending``.
    """
    verdicts = decisions or {}
    cluster_of_seq: dict[int, str] = {}
    for cluster in clusters:
        for seq in cluster.change_seqs:
            cluster_of_seq.setdefault(seq, cluster.id)

    cluster_items: list[dict[str, Any]] = []
    approved = 0
    ignored = 0
    for cluster in sorted(clusters, key=lambda item: item.number):
        decision, user_label, note = verdicts.get(cluster.number, ("pending", None, None))
        approved += decision == "approved"
        ignored += decision == "ignored"
        cluster_items.append(
            {
                "id": cluster.id,
                "number": cluster.number,
                "signature": cluster.signature,
                "bbox": list(cluster.bbox),
                "kind": cluster.kind,
                "label": cluster.label,
                "user_label": user_label,
                "decision": decision,
                "note": note,
                "change_ids": [f"ch{seq}" for seq in cluster.change_seqs],
                "cloud": dict(cluster.cloud),
                "badge": dict(cluster.badge),
            }
        )

    change_items: list[dict[str, Any]] = []
    for change in sorted(changes, key=lambda item: item.seq):
        item: dict[str, Any] = {
            "id": change.id,
            "seq": change.seq,
            "kind": change.kind,
            "etype": change.etype,
            "layer": change.layer,
            "before_handle": change.before_handle,
            "after_handle": change.after_handle,
            "bbox": list(change.bbox),
            "delta": dict(change.delta) if change.delta is not None else None,
            "minor": change.minor,
            "minor_reason": change.minor_reason,
            "cluster_id": None if change.minor else cluster_of_seq.get(change.seq),
            "provenance": dict(change.provenance),
        }
        handles = change_handles.get(change.seq)
        if handles:
            item["compare_handles"] = {
                side: list(values) for side, values in sorted(handles.items()) if values
            }
        change_items.append(item)

    return {
        "schema_version": SCHEMA_VERSION,
        "pair_id": pair_id,
        "pair_key": pair_key,
        "run_date": run_date,
        "layer": layer,
        "frame": {
            "bbox": [float(value) for value in after_frame.bbox],
            "scale_denominator": after_frame.scale_denominator,
            "scale_factor": scale_factor(after_frame.scale_denominator),
            "offset_before": [offset[0], offset[1]],
        },
        "clusters": cluster_items,
        "changes": change_items,
        "handle_to_cluster": dict(sorted(handle_to_cluster.items())),
        "counts": {
            "clusters": len(cluster_items),
            "changes": len(change_items),
            "minor": sum(1 for change in changes if change.minor),
            "approved": approved,
            "ignored": ignored,
        },
    }


def sidecar_integrity_failures(payload: dict[str, Any]) -> list[str]:
    """Everything JSON Schema cannot say about ``clusters.json`` (contract §7).

    The schema can check that ``handle_to_cluster``'s values look like cluster
    ids; it cannot check that they *are* the ids of clusters in this file. A
    sidecar that fails any of these would put the review screen out of step
    with the drawing it is describing -- a badge that selects nothing, a count
    that disagrees with the list -- so the engine refuses to write it.
    """
    failures: list[str] = []
    clusters = payload.get("clusters") or []
    changes = payload.get("changes") or []
    cluster_ids = {str(cluster["id"]) for cluster in clusters}
    change_ids = {str(change["id"]) for change in changes}

    for index, cluster in enumerate(clusters, start=1):
        if cluster.get("number") != index:
            failures.append(
                f"clusters[{index - 1}].number is {cluster.get('number')}, want {index}"
            )
        if cluster.get("id") != f"c{cluster.get('number')}":
            failures.append(f"clusters[{index - 1}].id does not match its number")
        members = cluster.get("change_ids") or []
        if not members:
            failures.append(f"clusters[{index - 1}] has no change_ids")
        for member in members:
            if member not in change_ids:
                failures.append(f"clusters[{index - 1}].change_ids has unknown {member}")

    for index, change in enumerate(changes, start=1):
        if change.get("seq") != index:
            failures.append(f"changes[{index - 1}].seq is {change.get('seq')}, want {index}")
        if change.get("id") != f"ch{change.get('seq')}":
            failures.append(f"changes[{index - 1}].id does not match its seq")
        cluster_id = change.get("cluster_id")
        if cluster_id is not None and cluster_id not in cluster_ids:
            failures.append(f"changes[{index - 1}].cluster_id {cluster_id} is not a cluster")
        if change.get("minor") and cluster_id is not None:
            failures.append(f"changes[{index - 1}] is minor but belongs to {cluster_id}")

    handles = payload.get("handle_to_cluster") or {}
    for handle, cluster_id in handles.items():
        if cluster_id not in cluster_ids:
            failures.append(f"handle_to_cluster[{handle}] points at unknown {cluster_id}")
    if list(handles) != sorted(handles):
        failures.append("handle_to_cluster keys are not sorted")

    counts = payload.get("counts") or {}
    expected = {
        "clusters": len(clusters),
        "changes": len(changes),
        "minor": sum(1 for change in changes if change.get("minor")),
        "approved": sum(1 for cluster in clusters if cluster.get("decision") == "approved"),
        "ignored": sum(1 for cluster in clusters if cluster.get("decision") == "ignored"),
    }
    for key, value in expected.items():
        if counts.get(key) != value:
            failures.append(f"counts.{key} is {counts.get(key)}, want {value}")
    return failures


def dumps_sidecar(payload: dict[str, Any]) -> bytes:
    """The sidecar's exact bytes: UTF-8, two-space indent, LF, trailing newline."""
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    return (text + "\n").encode("utf-8")


def write_clusters_json(
    payload: dict[str, Any], out_path: Path, *, allowed_roots: list[Path] | None = None
) -> Path:
    """Validate and write ``clusters.json``. Raises rather than write a broken file."""
    failures = sidecar_integrity_failures(payload)
    if failures:
        raise ValueError(f"clusters.json failed its integrity check: {'; '.join(failures)}")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    assert_writable_path(out_path, allowed_roots=allowed_roots or [out_path.parent])
    out_path.write_bytes(dumps_sidecar(payload))
    return out_path


def apply_decisions(
    path: Path, decisions: dict[int, tuple[str, str | None, str | None]]
) -> dict[str, Any]:
    """Rewrite only ``decision``/``user_label``/``note`` (and the two counts).

    The rest of the file is left exactly as the comparison produced it, so the
    byte-for-byte rule of contract §8 still holds for everything the engine
    computed: what a re-run must reproduce is the comparison, not the user's
    review of it.
    """
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    approved = 0
    ignored = 0
    for cluster in payload.get("clusters", []):
        verdict = decisions.get(int(cluster["number"]))
        if verdict is not None:
            cluster["decision"], cluster["user_label"], cluster["note"] = verdict
        approved += cluster.get("decision") == "approved"
        ignored += cluster.get("decision") == "ignored"
    payload.setdefault("counts", {})["approved"] = approved
    payload["counts"]["ignored"] = ignored
    path.write_bytes(dumps_sidecar(payload))
    return payload


def merge_decisions(payload: dict[str, Any], rows: list[Any]) -> dict[str, Any]:
    """Overlay the database's review onto a sidecar read from disk.

    ``GET /compare/pairs/{id}/clusters`` serves this: the file is the record of
    the comparison, the database is the record of the review, and the screen
    needs both in one document.
    """
    by_number = {int(row.number): row for row in rows}
    approved = 0
    ignored = 0
    for cluster in payload.get("clusters", []):
        row = by_number.get(int(cluster["number"]))
        if row is not None:
            cluster["decision"] = row.decision
            cluster["user_label"] = row.user_label
            cluster["note"] = row.note
        approved += cluster.get("decision") == "approved"
        ignored += cluster.get("decision") == "ignored"
    payload.setdefault("counts", {})["approved"] = approved
    payload["counts"]["ignored"] = ignored
    return payload


# --------------------------------------------------------------------------- worker


def compare_pair(task: ComparePairInput, config: CompareConfig) -> ComparePairOutput:
    """Compare one 도곽 짝 end to end. The unit of work the process pool runs.

    Opens both working DXFs, diffs them, clusters the result, writes the
    compare DXF and the sidecar, and returns picklable records. A pair that
    fails comes back with ``error`` set rather than raising: one unreadable
    sheet out of 375 must not fail the run (the same rule the frames job
    follows).
    """
    started = time.perf_counter()
    output = ComparePairOutput(pair_id=task.pair_id)
    try:
        before_doc = ezdxf.readfile(task.before_path)
        after_doc = ezdxf.readfile(task.after_path)

        result = diff_pair(before_doc, after_doc, task.before_frame, task.after_frame, config)
        factor = scale_factor(task.after_frame.scale_denominator)
        clusters = build_clusters(result.changes, task.after_frame, config, factor)

        out_dir = Path(task.out_dir)
        roots = [Path(task.bundle_root)]
        dxf = write_compare_dxf(
            before_doc=before_doc,
            after_doc=after_doc,
            before_frame=task.before_frame,
            after_frame=task.after_frame,
            changes=result.changes,
            clusters=clusters,
            config=config,
            run_date=task.run_date,
            offset=result.offset,
            out_path=out_dir / COMPARE_DXF_NAME,
            allowed_roots=roots,
        )
        payload = build_sidecar(
            pair_id=task.pair_id,
            pair_key=task.pair_key,
            run_date=task.run_date,
            layer=config.revision_layer(task.run_date),
            after_frame=task.after_frame,
            offset=result.offset,
            changes=result.changes,
            clusters=clusters,
            handle_to_cluster=dxf.handle_to_cluster,
            change_handles=dxf.change_handles,
        )
        sidecar = write_clusters_json(payload, out_dir / CLUSTERS_JSON_NAME, allowed_roots=roots)

        output.changes = result.changes
        output.clusters = clusters
        output.status = "changed" if result.has_real_changes else "same"
        output.compare_dxf_path = str(dxf.path)
        output.clusters_json_path = str(sidecar)
        output.warnings = [*result.warnings, *dxf.warnings]
        output.entity_count = len(task.after_frame.entity_handles)
    except Exception as error:  # noqa: BLE001 - one bad sheet must not fail the run
        logger.exception("comparison failed for pair %s", task.pair_id)
        output.error = f"{type(error).__name__}: {error}"
    output.elapsed_s = round(time.perf_counter() - started, 3)
    return output


__all__ = [
    "ADDED_BLOCK_PREFIX",
    "APPID",
    "BEFORE_BLOCK_PREFIX",
    "CLONE_NAME_KEEP",
    "CLUSTERS_JSON_NAME",
    "COMPARE_DXF_NAME",
    "COLOR_ADDED",
    "COLOR_LABEL",
    "COLOR_REMOVED",
    "DXF_VERSION",
    "LAYER_ADDED",
    "LAYER_LABEL",
    "LAYER_REMOVED",
    "MAX_BLOCK_NAME",
    "REMOVED_BLOCK_PREFIX",
    "SCHEMA_VERSION",
    "ZERO_GUID",
    "ComparePairInput",
    "ComparePairOutput",
    "CompareDxfResult",
    "apply_decisions",
    "build_sidecar",
    "compare_pair",
    "dumps_sidecar",
    "merge_decisions",
    "pin_classes_for_determinism",
    "pin_header_for_determinism",
    "prefix_before_blocks",
    "relayer_block_references",
    "serialize",
    "sidecar_integrity_failures",
    "write_clusters_json",
    "write_compare_dxf",
]
