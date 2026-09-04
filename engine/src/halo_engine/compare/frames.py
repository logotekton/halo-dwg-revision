"""도곽 추출: one title-block INSERT becomes one sheet (contract §6, brief R1-04).

The unit of comparison is not a file. The real 실시도서 set has 68 drawings and
375 sheets: every file is model-space only, and one file carries anywhere from
one to a hundred-odd 도곽, each anchored by a title-block INSERT
(``docs/spikes/real-dwg-measurement.md`` §0-1, §12 항목 14). So the first thing
the pipeline has to do with a working DXF is cut it into sheets, and everything
downstream -- matching, diffing, the cloud marks, one markup DWG per sheet --
is defined per frame.

The extraction has four steps, and each one has a fallback because real title
blocks are not uniform:

1. **candidates** -- every model-space INSERT with at least ``min_attribs``
   attributes, plus the same search one and two levels inside block definitions
   so that a title block living in an embedded XREF (``ingest/xref.py``: the
   real set keeps its 표제란 in ``XR/TITLE BLOCK-V.dwg``) is found with its
   transform accumulated;
2. **confirmation** -- a candidate is a title block when one of its tags is in
   ``number_tags`` or ``title_tags``; when *no* candidate in the file matches a
   tag, ``fallback_most_common_block`` takes the block name that repeats most;
3. **boundary** -- the smallest axis-aligned closed rectangle that contains the
   title block, else the file's most common frame size anchored at the title
   block's bottom-right, else A1 (841x594) times the scale denominator. Which
   of the three ran is kept on :attr:`FrameRecord.boundary_source`, because
   "the frame looks wrong" is a question about *which* rule fired;
4. **assignment** -- every top-level model-space entity joins the frame its
   bounding-box centre falls in (``frames.yaml`` ``frame.assign``).

Every rule here is a value in ``frames.yaml`` (``compare/config.py``), never a
constant in this file: a project whose title blocks tag the drawing number
``도면번호`` instead of ``DWG_NO`` is a settings edit, not a code change
(CLAUDE.md rule 7). The one number the module owns is the ISO A1 sheet, which
is a paper size rather than a project preference.

Deterministic by construction (CLAUDE.md rule 6): candidates are visited in
document order, ties are broken by explicit sort keys, and every coordinate is
rounded to three decimals before it leaves the module.
"""

from __future__ import annotations

import fnmatch
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from typing import Any

import ezdxf
import ezdxf.bbox
from ezdxf.document import Drawing
from ezdxf.math import Matrix44

from halo_engine.compare.config import FramesConfig
from halo_engine.ingest.encoding import decode_escapes

#: ISO A1 in millimetres. The last-resort frame size: at 1:100 an A1 sheet is
#: 84,100 x 59,400 model mm, which is exactly what the synthetic fixtures and
#: the real set both use (``fixtures/README.md``, spike §0-1).
A1_WIDTH_MM = 841.0
A1_HEIGHT_MM = 594.0

#: Assumed denominator when the title block's scale could not be read. The
#: ledger's reference scale (``compare/config.py::REFERENCE_SCALE_DENOMINATOR``).
DEFAULT_SCALE_DENOMINATOR = 100

#: How deep the nested-INSERT search goes. 0 is a title block sitting directly
#: in model space, 1 is one inside a block (the embedded-XREF case), 2 is the
#: limit; anything deeper is reported as a warning instead of searched, because
#: a title block nested three blocks down is a drafting accident, not a
#: convention worth paying for on every file (brief: "깊이 2까지만").
MAX_NESTING_DEPTH = 2

#: Millimetres. Two coordinates closer than this are the same coordinate --
#: a title block usually *touches* the frame it sits in, so containment has to
#: be tested inclusively or the outline is never found.
GEOM_EPS = 1e-3

#: Degrees. How far a rectangle's edge may lean and still count as axis
#: aligned. Drawn frames are snapped to ortho; 1 degree only absorbs rounding.
RECT_ANGLE_TOLERANCE_DEG = 1.0

#: Decimal places every coordinate is rounded to before it is stored (contract
#: §12 결정론: the same input must produce byte-identical output).
COORD_DECIMALS = 3

#: :attr:`FrameRecord.boundary_source` values, named after the ``frames.yaml``
#: rules they implement so a support question maps to a settings key.
BOUNDARY_RECT = "smallest_enclosing_rect"
BOUNDARY_MODAL = "modal_size_titleblock_bottom_right"
BOUNDARY_A1 = "a1_titleblock_bottom_right"
BOUNDARY_EXTENTS = "model_extents"

#: :attr:`FrameRecord.kind`, mirroring ``sheet_frame.kind`` (contract §3).
KIND_TITLEBLOCK = "titleblock"
KIND_UNRECOGNIZED = "unrecognized_file"

#: Hyphen-ish characters folded to ASCII ``-`` when ``normalize.unify_hyphen``
#: is on. A drawing number typed with an en dash must match the same number
#: typed with a hyphen, or the two revisions of one sheet never pair up.
_HYPHEN_VARIANTS = "‐‑‒–—―−﹣－_"

#: ``1:100``, ``1/100``, ``1 : 50``. Anchored on the numerator so that a date
#: (``2026-09-04``) or a sheet number (``A-101``) in the same string cannot be
#: mistaken for a scale.
_SCALE_RE = re.compile(r"(?<![0-9])1\s*[:/]\s*([0-9]{1,6})(?![0-9])")


@dataclass
class FrameRecord:
    """One 도곽: a sheet, or a whole file that produced none.

    The serialisation of one ``sheet_frame`` row (contract §3) plus the few
    fields the matcher needs that the table does not store: the file's name and
    hash, its converter, and which boundary rule produced ``bbox``.

    A plain mutable dataclass on purpose. It crosses a process boundary (the
    extraction runs in the job runner's ``ProcessPoolExecutor``, so every field
    is a built-in type and the class is picklable), and
    :func:`assign_entities` fills ``entity_handles`` in afterwards, in the
    parent process, once every frame of the file is known.
    """

    file_id: str
    """``drawing_file`` row the frame was read from."""

    kind: str = KIND_TITLEBLOCK
    """:data:`KIND_TITLEBLOCK` or :data:`KIND_UNRECOGNIZED`."""

    titleblock_handle: str | None = None
    """Handle of the title-block INSERT. ``None`` for an unrecognised file."""

    block_name: str | None = None
    """Block definition name of the title block, NFC-normalised."""

    bbox: list[float] = field(default_factory=list)
    """``[x0, y0, x1, y1]`` of the frame outline, world coordinates, mm."""

    sheet_no: str | None = None
    """Drawing number as printed, raw text."""

    sheet_title: str | None = None
    """Drawing name as printed, raw text."""

    scale_text: str | None = None
    """Scale as printed, raw text."""

    scale_denominator: int | None = None
    """Denominator parsed out of :attr:`scale_text`, or ``None``."""

    date_text: str | None = None
    """Date as printed. Display only -- never the run date (contract §11)."""

    norm_key: str = ""
    """Normalised :attr:`sheet_no`, or ``file:<normalised file name>``."""

    sort_index: int = 0
    """Reading order of the frame inside its file: top row first, then left."""

    entity_handles: list[str] = field(default_factory=list)
    """Handles assigned by :func:`assign_entities`, sorted."""

    provenance: dict[str, Any] = field(default_factory=dict)
    """``{file, handle, path, space}`` (CLAUDE.md rule 5)."""

    attributes: dict[str, str] = field(default_factory=dict)
    """Every ATTRIB of the title block, tag -> value, as read."""

    boundary_source: str = BOUNDARY_RECT
    """Which of the three boundary rules produced :attr:`bbox`."""

    warnings: list[str] = field(default_factory=list)
    """Message codes raised while extracting this frame."""

    role: str = ""
    """``before`` / ``after``. Set by the caller, not by extraction."""

    file_name: str = ""
    """Original file name. Set by the caller; used for matching and search."""

    file_sha256: str = ""
    """Original file's hash. Set by the caller; equal hashes mean equal sheets."""

    converter: str | None = None
    """``drawing_file.converter``. Set by the caller (contract: 짝 converter_mismatch)."""

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0] if len(self.bbox) == 4 else 0.0

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1] if len(self.bbox) == 4 else 0.0

    def to_row(self) -> dict[str, Any]:
        """The ``sheet_frame`` columns ``repos.replace_frames`` inserts.

        ``id``/``compare_set_id``/``role`` are filled in by the repository, and
        the caller-side fields (file name, hash, converter, boundary source)
        are not columns -- they live on the record only for the length of one
        extraction job.
        """
        return {
            "file_id": self.file_id,
            "kind": self.kind,
            "titleblock_handle": self.titleblock_handle,
            "block_name": self.block_name,
            "bbox": list(self.bbox),
            "sheet_no": self.sheet_no,
            "sheet_title": self.sheet_title,
            "scale_text": self.scale_text,
            "scale_denominator": self.scale_denominator,
            "date_text": self.date_text,
            "norm_key": self.norm_key,
            "sort_index": self.sort_index,
            "entity_handles": list(self.entity_handles),
            "provenance": dict(self.provenance),
            "attributes": dict(self.attributes),
        }


@dataclass
class FileFramesResult:
    """What one worker process hands back for one working DXF.

    Picklable, and never an exception: a file that cannot be opened at all
    still has to appear in the sheet list as a skipped file rather than
    failing the whole ``compare.frames`` job (a real set has 68 files and one
    unreadable conversion must not cost the other 67).
    """

    file_id: str
    frames: list[FrameRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    entity_count: int = 0
    assign_seconds: float = 0.0


# --------------------------------------------------------------------------- text


def _nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _fold_fullwidth(text: str) -> str:
    """Full-width ASCII (U+FF01..U+FF5E) and the ideographic space to ASCII.

    Narrower than ``NFKC`` deliberately: NFKC would also rewrite ``㎡`` and
    circled numerals, which appear inside real 도면명 and must survive
    normalisation unchanged so that the same title still matches itself.
    """
    out: list[str] = []
    for char in text:
        code = ord(char)
        if 0xFF01 <= code <= 0xFF5E:
            out.append(chr(code - 0xFEE0))
        elif code == 0x3000:
            out.append(" ")
        else:
            out.append(char)
    return "".join(out)


def normalize_key(text: str | None, config: FramesConfig) -> str:
    """Fold one title-block string down to the form two sheets are compared by.

    ``frames.yaml`` ``normalize`` decides which of the four foldings apply; the
    order is fixed here because they are not commutative (folding full-width
    first is what lets the hyphen rule see a full-width dash, and stripping
    spaces last is what keeps ``A - 101`` and ``A-101`` equal).
    """
    if not text:
        return ""
    value = _nfc(text)
    if config.normalize.fullwidth_to_ascii:
        value = _fold_fullwidth(value)
    if config.normalize.unify_hyphen:
        value = "".join("-" if char in _HYPHEN_VARIANTS else char for char in value)
    if config.normalize.upper:
        value = value.upper()
    if config.normalize.strip_spaces:
        value = "".join(value.split())
    else:
        value = value.strip()
    return value


def parse_scale(text: str | None) -> int | None:
    """Denominator of a printed scale: ``1:50`` -> 50, ``A3 1/100`` -> 100.

    ``None`` when there is no ``1:n`` in the string at all (``NTS``, an empty
    tag, a scale bar). A sheet without a denominator is drawn at the reference
    scale rather than guessed, because a wrong factor puts every cloud mark on
    that sheet at the wrong size (``compare-dxf.md`` §5).
    """
    if not text:
        return None
    match = _SCALE_RE.search(_fold_fullwidth(_nfc(text)))
    if match is None:
        return None
    denominator = int(match.group(1))
    return denominator if denominator > 0 else None


def _round(value: float) -> float:
    return round(float(value), COORD_DECIMALS)


def _round_box(box: tuple[float, float, float, float]) -> list[float]:
    return [_round(box[0]), _round(box[1]), _round(box[2]), _round(box[3])]


# --------------------------------------------------------------------------- candidates


@dataclass(frozen=True)
class _NestedInsert:
    """One INSERT found inside a block definition, with its local transform.

    Cached per block *name*: the contents of a block definition are the same
    for every INSERT of it, so a file with 104 title blocks walks the title
    block's definition once, not 104 times.
    """

    handle: str
    block_name: str
    matrix: Matrix44
    depth: int
    path: tuple[str, ...]


@dataclass
class _Candidate:
    """A title-block candidate before it is confirmed."""

    entity: Any
    handle: str
    block_name: str
    attributes: dict[str, str]
    to_world: Matrix44 | None
    path: list[str]
    depth: int


def _const_attdefs(
    doc: Drawing, block_name: str, cache: dict[str, dict[str, str]]
) -> dict[str, str]:
    """Constant attributes of one block definition, tag -> value, cached by name.

    A constant attribute is stored once in the definition and never repeated on
    the reference, so an INSERT of such a title block has no ATTRIB of its own;
    some drawing offices put the project name (and occasionally the sheet
    number) there. Cached because the lookup would otherwise run once per
    INSERT of every ordinary block in the file.
    """
    cached = cache.get(block_name)
    if cached is not None:
        return cached
    values: dict[str, str] = {}
    block = doc.blocks.get(block_name)
    if block is not None:
        for attdef in block.query("ATTDEF"):
            if not attdef.is_const:
                continue
            tag = _nfc(str(attdef.dxf.get("tag", "") or ""))
            if not tag:
                continue
            values[tag] = decode_escapes(_nfc(str(attdef.dxf.get("text", "") or "")))
    cache[block_name] = values
    return values


def _attribute_map(
    insert: Any, doc: Drawing, const_cache: dict[str, dict[str, str]]
) -> dict[str, str]:
    """Tag -> value for one INSERT, escapes decoded (``ingest/encoding.py``)."""
    values: dict[str, str] = {}
    for attrib in insert.attribs:
        tag = _nfc(str(attrib.dxf.get("tag", "") or ""))
        if not tag:
            continue
        values[tag] = decode_escapes(_nfc(str(attrib.dxf.get("text", "") or "")))
    if values:
        return values
    return dict(_const_attdefs(doc, _nfc(str(insert.dxf.name)), const_cache))


def _nested_inserts(
    doc: Drawing,
    block_name: str,
    *,
    cache: dict[tuple[str, int], list[_NestedInsert]],
    max_depth: int,
    deep_names: set[str],
) -> list[_NestedInsert]:
    """Every INSERT inside ``block_name``, down to ``max_depth`` levels.

    Keyed by ``(name, max_depth)`` so the same block asked for at two different
    remaining depths does not serve a truncated answer, and seeded with an
    empty list before recursing so a block that (indirectly) inserts itself
    terminates instead of recursing forever.

    ``deep_names`` collects the blocks that were truncated, so the caller can
    warn once per file instead of silently ignoring a title block buried three
    levels down (brief Defaults for ambiguity: "더 깊으면 무시하고 경고").
    """
    key = (block_name, max_depth)
    cached = cache.get(key)
    if cached is not None:
        return cached
    cache[key] = []
    found: list[_NestedInsert] = []
    block = doc.blocks.get(block_name)
    if block is None:
        return found
    for entity in block:
        if entity.dxftype() != "INSERT":
            continue
        handle = str(entity.dxf.handle)
        child_name = _nfc(str(entity.dxf.name))
        matrix = entity.matrix44()
        found.append(
            _NestedInsert(
                handle=handle, block_name=child_name, matrix=matrix, depth=1, path=(handle,)
            )
        )
        child_block = doc.blocks.get(child_name)
        if max_depth <= 1:
            if child_block is not None and any(
                child.dxftype() == "INSERT" for child in child_block
            ):
                deep_names.add(child_name)
            continue
        for grandchild in _nested_inserts(
            doc, child_name, cache=cache, max_depth=max_depth - 1, deep_names=deep_names
        ):
            found.append(
                _NestedInsert(
                    handle=grandchild.handle,
                    block_name=grandchild.block_name,
                    # local -> child block -> this block. ezdxf uses the
                    # row-vector convention, so `a * b` applies `a` first.
                    matrix=grandchild.matrix @ matrix,
                    depth=grandchild.depth + 1,
                    path=(handle, *grandchild.path),
                )
            )
    cache[key] = found
    return found


def _iter_candidates(
    doc: Drawing, config: FramesConfig, warnings: list[str]
) -> Iterator[_Candidate]:
    """Every INSERT that could be a title block, in document order.

    Depth 0 is a model-space INSERT; deeper candidates come from block
    definitions with the outer INSERT's transform accumulated, which is how a
    title block that arrived as an embedded XREF (``ingest/xref.py`` turns the
    XREF block into an ordinary block whose content is the referenced drawing)
    is still found.
    """
    patterns = list(config.titleblock.block_name_patterns)
    min_attribs = config.titleblock.min_attribs
    nested_cache: dict[tuple[str, int], list[_NestedInsert]] = {}
    const_cache: dict[str, dict[str, str]] = {}
    attr_cache: dict[str, dict[str, str]] = {}
    deep_names: set[str] = set()

    def _accept(name: str, attributes: dict[str, str]) -> bool:
        if patterns:
            # An explicitly named block *is* the title block: the project said
            # so in `frames.yaml`, so it is not also required to carry
            # attributes (a converted XREF sometimes loses them --
            # docs/spikes/real-dwg-measurement.md §3.2).
            return any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns)
        return len(attributes) >= min_attribs

    for insert in doc.modelspace().query("INSERT"):
        handle = str(insert.dxf.handle)
        block_name = _nfc(str(insert.dxf.name))
        attributes = _attribute_map(insert, doc, const_cache)
        if _accept(block_name, attributes):
            yield _Candidate(
                entity=insert,
                handle=handle,
                block_name=block_name,
                attributes=attributes,
                to_world=None,
                path=[],
                depth=0,
            )
        outer_matrix = insert.matrix44()
        for nested in _nested_inserts(
            doc,
            block_name,
            cache=nested_cache,
            max_depth=MAX_NESTING_DEPTH,
            deep_names=deep_names,
        ):
            entity = doc.entitydb.get(nested.handle)
            if entity is None:
                continue
            nested_attributes = attr_cache.get(nested.handle)
            if nested_attributes is None:
                nested_attributes = _attribute_map(entity, doc, const_cache)
                attr_cache[nested.handle] = nested_attributes
            if not _accept(nested.block_name, nested_attributes):
                continue
            yield _Candidate(
                entity=entity,
                handle=nested.handle,
                block_name=nested.block_name,
                attributes=nested_attributes,
                to_world=nested.matrix @ outer_matrix,
                path=[handle, *nested.path[:-1]],
                depth=nested.depth,
            )

    if deep_names:
        warnings.append(f"titleblock_search_depth_exceeded:{len(deep_names)}")


def _tag_key(tag: str, config: FramesConfig) -> str:
    """The form two ATTRIB tags are compared in.

    :func:`normalize_key` plus dropping the separator itself, so that
    ``DWG_NO``, ``DWG-NO``, ``DWG NO`` and ``DWGNO`` are one tag. Offices write
    the same tag all four ways, and listing every spelling in ``frames.yaml``
    would push that noise onto the person editing the settings file.
    """
    return normalize_key(tag, config).replace("-", "")


def _tag_lookup(
    attributes: dict[str, str], tags: Iterable[str], config: FramesConfig
) -> str | None:
    """First non-empty value whose tag matches one of ``tags``.

    The configured order is the priority order ("best first", ``config.py``).
    """
    folded = {_tag_key(tag, config): value for tag, value in attributes.items()}
    for tag in tags:
        value = folded.get(_tag_key(tag, config))
        if value is not None and value.strip():
            return value.strip()
    return None


def _has_titleblock_tag(attributes: dict[str, str], config: FramesConfig) -> bool:
    tags = [*config.titleblock.number_tags, *config.titleblock.title_tags]
    return _tag_lookup(attributes, tags, config) is not None


def _confirm(candidates: list[_Candidate], config: FramesConfig) -> list[_Candidate]:
    """Decide which candidates are title blocks (brief Goal 1, step 2).

    Tag match first; if not one candidate in the whole file matched a tag,
    ``fallback_most_common_block`` takes every instance of whichever block name
    repeats most (ties by name, so the choice does not depend on dict order).

    ``block_name_patterns`` short-circuits the whole question: the candidate
    list is already only blocks the project named, and naming them *is* the
    decision. Requiring a tag on top would make a correct configuration find
    nothing on exactly the files it was written for (a conversion that dropped
    the ATTRIBs).
    """
    if config.titleblock.block_name_patterns:
        return candidates
    tagged = [c for c in candidates if _has_titleblock_tag(c.attributes, config)]
    if tagged:
        return tagged
    if not config.titleblock.fallback_most_common_block or not candidates:
        return []
    counts = Counter(c.block_name for c in candidates)
    best = max(counts, key=lambda name: (counts[name], name))
    return [c for c in candidates if c.block_name == best]


# --------------------------------------------------------------------------- geometry


def _transformed_box(
    entity: Any, matrix: Matrix44 | None, cache: ezdxf.bbox.Cache
) -> tuple[float, float, float, float] | None:
    box = ezdxf.bbox.extents([entity], cache=cache)
    if not box.has_data:
        return None
    if matrix is None:
        return (
            float(box.extmin.x),
            float(box.extmin.y),
            float(box.extmax.x),
            float(box.extmax.y),
        )
    corners = [
        (box.extmin.x, box.extmin.y, 0.0),
        (box.extmax.x, box.extmin.y, 0.0),
        (box.extmax.x, box.extmax.y, 0.0),
        (box.extmin.x, box.extmax.y, 0.0),
    ]
    moved = [matrix.transform(corner) for corner in corners]
    xs = [float(point.x) for point in moved]
    ys = [float(point.y) for point in moved]
    return (min(xs), min(ys), max(xs), max(ys))


def _is_axis_aligned_rect(entity: Any) -> tuple[float, float, float, float] | None:
    """The bbox of ``entity`` if it is a closed, axis-aligned, 4-corner rectangle.

    Accepts 4 or 5 vertices (a rectangle written with its first point repeated)
    and rejects anything with a bulge, because a bulged "rectangle" is a
    rounded frame whose corners are not where its bbox says they are.
    """
    if entity.dxftype() != "LWPOLYLINE":
        return None
    points = list(entity.get_points("xyb"))
    if len(points) == 5 and abs(points[0][0] - points[4][0]) <= GEOM_EPS:
        if abs(points[0][1] - points[4][1]) <= GEOM_EPS:
            points = points[:4]
    if len(points) != 4:
        return None
    if not entity.closed:
        return None
    if any(abs(float(point[2])) > 1e-9 for point in points):
        return None

    tolerance = RECT_ANGLE_TOLERANCE_DEG / 180.0 * 3.141592653589793
    xs = [float(point[0]) for point in points]
    ys = [float(point[1]) for point in points]
    for index in range(4):
        dx = xs[(index + 1) % 4] - xs[index]
        dy = ys[(index + 1) % 4] - ys[index]
        length = (dx * dx + dy * dy) ** 0.5
        if length <= GEOM_EPS:
            return None
        # sin of the angle to the nearer axis; cheaper and better conditioned
        # than atan2 for the "is this edge ortho" question.
        if min(abs(dy), abs(dx)) / length > tolerance:
            return None
    return (min(xs), min(ys), max(xs), max(ys))


def _contains(outer: tuple[float, float, float, float], inner: list[float]) -> bool:
    return (
        outer[0] <= inner[0] + GEOM_EPS
        and outer[1] <= inner[1] + GEOM_EPS
        and outer[2] >= inner[2] - GEOM_EPS
        and outer[3] >= inner[3] - GEOM_EPS
    )


def _almost_same_box(a: tuple[float, float, float, float], b: list[float]) -> bool:
    return all(abs(a[index] - b[index]) <= 1.0 for index in range(4))


def _model_rectangles(doc: Drawing) -> list[tuple[float, float, float, float]]:
    """Every top-level closed axis-aligned rectangle in model space.

    Only top level: a rectangle drawn *inside* the title block's own definition
    is the title block's border, and picking it as the sheet outline would cut
    the sheet down to its stamp.
    """
    rects: list[tuple[float, float, float, float]] = []
    for entity in doc.modelspace().query("LWPOLYLINE"):
        rect = _is_axis_aligned_rect(entity)
        if rect is not None:
            rects.append(rect)
    return rects


def _smallest_enclosing_rect(
    rects: list[tuple[float, float, float, float]], titleblock_bbox: list[float]
) -> tuple[float, float, float, float] | None:
    best: tuple[float, float, float, float] | None = None
    best_area = 0.0
    for rect in rects:
        if not _contains(rect, titleblock_bbox):
            continue
        if _almost_same_box(rect, titleblock_bbox):
            continue  # the title block's own border, not the sheet outline
        area = (rect[2] - rect[0]) * (rect[3] - rect[1])
        if area <= 0.0:
            continue
        if best is None or area < best_area:
            best, best_area = rect, area
    return best


def _anchored_box(
    titleblock_bbox: list[float], width: float, height: float
) -> tuple[float, float, float, float]:
    """A frame of ``width`` x ``height`` with the title block at its bottom-right.

    The Korean convention every sheet in the real set follows
    (``frames.yaml`` ``frame.fallback``): the stamp sits in the bottom-right
    corner, so the frame grows left and up from it.
    """
    x1 = titleblock_bbox[2]
    y0 = titleblock_bbox[1]
    return (x1 - width, y0, x1, y0 + height)


def _transform_box(
    box: tuple[float, float, float, float], matrix: Matrix44
) -> tuple[float, float, float, float]:
    """The axis-aligned box around ``box``'s four corners after ``matrix``."""
    corners = [
        matrix.transform((box[0], box[1], 0.0)),
        matrix.transform((box[2], box[1], 0.0)),
        matrix.transform((box[2], box[3], 0.0)),
        matrix.transform((box[0], box[3], 0.0)),
    ]
    xs = [float(point.x) for point in corners]
    ys = [float(point.y) for point in corners]
    return (min(xs), min(ys), max(xs), max(ys))


def _union(
    box: tuple[float, float, float, float], other: list[float]
) -> tuple[float, float, float, float]:
    return (
        min(box[0], other[0]),
        min(box[1], other[1]),
        max(box[2], other[2]),
        max(box[3], other[3]),
    )


# --------------------------------------------------------------------------- ordering


def _reading_order(frames: list[FrameRecord]) -> None:
    """Number the frames top row first, then left to right inside a row.

    Rows are found by clustering the frame centres on y with a tolerance of
    half a frame height, which is what makes a sheet grid that is a few
    millimetres out of alignment still read as rows rather than as a diagonal.
    """
    if not frames:
        return
    heights = sorted(frame.height for frame in frames if frame.height > 0)
    band = (heights[len(heights) // 2] / 2.0) if heights else 0.0

    def centre(frame: FrameRecord) -> tuple[float, float]:
        return (
            (frame.bbox[0] + frame.bbox[2]) / 2.0,
            (frame.bbox[1] + frame.bbox[3]) / 2.0,
        )

    ordered = sorted(frames, key=lambda f: (-centre(f)[1], centre(f)[0], f.titleblock_handle or ""))
    rows: list[list[FrameRecord]] = []
    for frame in ordered:
        if rows and abs(centre(rows[-1][0])[1] - centre(frame)[1]) <= band:
            rows[-1].append(frame)
        else:
            rows.append([frame])

    index = 0
    for row in rows:
        for frame in sorted(row, key=lambda f: (centre(f)[0], f.titleblock_handle or "")):
            frame.sort_index = index
            index += 1


# --------------------------------------------------------------------------- extraction


def file_norm_key(file_name: str, config: FramesConfig) -> str:
    """``norm_key`` of an :data:`KIND_UNRECOGNIZED` frame (contract §3).

    Applied by the caller rather than by :func:`extract_frames`, which only
    ever sees the working DXF -- stored under its content hash, so the original
    file name is not in the document.
    """
    return f"file:{normalize_key(file_name, config)}"


def _unrecognized_frame(doc: Drawing, *, file_id: str) -> FrameRecord:
    """The one frame a file with no title block still produces (contract §3).

    Dropping the file would hide it: the user has to see that a drawing was
    read but not understood, and be able to pair it by hand on screen B.
    """
    box = _CentreFinder(doc).model_extents()
    bbox = _round_box(box) if box is not None else [0.0, 0.0, 0.0, 0.0]
    first = next(iter(doc.modelspace()), None)
    handle = str(first.dxf.handle) if first is not None else "0"
    return FrameRecord(
        file_id=file_id,
        kind=KIND_UNRECOGNIZED,
        titleblock_handle=None,
        block_name=None,
        bbox=bbox,
        norm_key="",  # filled in by the caller, which knows the file name
        sort_index=0,
        boundary_source=BOUNDARY_EXTENTS,
        provenance={"file": file_id, "handle": handle, "path": [], "space": "MODEL"},
    )


def extract_frames(doc: Drawing, *, file_id: str, config: FramesConfig) -> list[FrameRecord]:
    """Every 도곽 in one working DXF, in reading order (brief R1-04 Goal 1).

    Returns exactly one :data:`KIND_UNRECOGNIZED` frame when no title block was
    found. ``norm_key`` of that frame is left empty here and completed by the
    caller (``api/routers/compare_pairs.py``), which is the only layer that
    knows the file's *original* name -- the working DXF is stored under its
    content hash.
    """
    warnings: list[str] = []
    candidates = list(_iter_candidates(doc, config, warnings))
    confirmed = _confirm(candidates, config)
    if not confirmed:
        frame = _unrecognized_frame(doc, file_id=file_id)
        frame.warnings = warnings
        return [frame]

    cache = ezdxf.bbox.Cache()
    frames: list[FrameRecord] = []
    boxes: list[list[float]] = []
    for candidate in confirmed:
        box = _transformed_box(candidate.entity, candidate.to_world, cache)
        if box is None:
            warnings.append(f"titleblock_without_extent:{candidate.handle}")
            continue
        titleblock_bbox = _round_box(box)
        attributes = candidate.attributes
        scale_text = _tag_lookup(attributes, config.titleblock.scale_tags, config)
        frames.append(
            FrameRecord(
                file_id=file_id,
                kind=KIND_TITLEBLOCK,
                titleblock_handle=candidate.handle,
                block_name=candidate.block_name,
                bbox=titleblock_bbox,  # replaced by the boundary rules below
                sheet_no=_tag_lookup(attributes, config.titleblock.number_tags, config),
                sheet_title=_tag_lookup(attributes, config.titleblock.title_tags, config),
                scale_text=scale_text,
                scale_denominator=parse_scale(scale_text),
                date_text=_tag_lookup(attributes, config.titleblock.date_tags, config),
                attributes=dict(attributes),
                provenance={
                    "file": file_id,
                    "handle": candidate.handle,
                    "path": list(candidate.path),
                    "space": "MODEL",
                },
            )
        )
        boxes.append(titleblock_bbox)

    _apply_boundaries(doc, frames, boxes)
    for frame in frames:
        frame.norm_key = normalize_key(frame.sheet_no, config)
        frame.warnings = [*warnings, *frame.warnings]
    _reading_order(frames)
    return sorted(frames, key=lambda f: f.sort_index)


def _apply_boundaries(
    doc: Drawing, frames: list[FrameRecord], titleblock_boxes: list[list[float]]
) -> None:
    """Run the three boundary rules over every frame of one file, in order.

    Rule (b) needs the whole file's answer to rule (a), so the three passes are
    done here rather than per frame: find every outline first, take the modal
    size of what was found, then fall back to A1 for whatever is left.
    """
    rects = _model_rectangles(doc)
    resolved: list[tuple[float, float, float, float] | None] = []
    for titleblock_bbox in titleblock_boxes:
        resolved.append(_smallest_enclosing_rect(rects, titleblock_bbox))

    sizes = Counter(
        (_round(rect[2] - rect[0]), _round(rect[3] - rect[1])) for rect in resolved if rect
    )
    modal: tuple[float, float] | None = None
    if sizes:
        modal = max(sizes, key=lambda size: (sizes[size], size[0] * size[1]))

    for frame, titleblock_bbox, rect in zip(frames, titleblock_boxes, resolved, strict=True):
        if rect is not None:
            box, source = rect, BOUNDARY_RECT
        elif modal is not None:
            box = _anchored_box(titleblock_bbox, modal[0], modal[1])
            source = BOUNDARY_MODAL
        else:
            denominator = frame.scale_denominator or DEFAULT_SCALE_DENOMINATOR
            box = _anchored_box(
                titleblock_bbox, A1_WIDTH_MM * denominator, A1_HEIGHT_MM * denominator
            )
            source = BOUNDARY_A1
        if not _contains(box, titleblock_bbox):
            # Defaults for ambiguity: a title block drawn outside its frame
            # widens the frame rather than losing its own stamp.
            box = _union(box, titleblock_bbox)
            frame.warnings.append("frame_widened_for_titleblock")
        frame.bbox = _round_box(box)
        frame.boundary_source = source


# --------------------------------------------------------------------------- assignment


class _FrameGrid:
    """Uniform spatial hash over the frames of one file.

    A file can hold a hundred frames and a third of a million entities, so the
    naive "test every entity against every frame" is 35 million rectangle tests
    and misses the 30-second budget (brief Constraints). Hashing the frame
    rectangles into cells the size of a sheet turns each lookup into one dict
    hit plus a handful of comparisons.
    """

    def __init__(self, frames: list[FrameRecord]) -> None:
        self._frames = frames
        # One cell is at least as big as the largest frame, so no frame can
        # span more than 2x2 cells however the sheets are laid out. Sizing the
        # cell to the *smallest* frame instead would make a file that mixes one
        # tiny frame with A1 sheets allocate millions of cells.
        spans = [f.width for f in frames] + [f.height for f in frames]
        self._cell = max([*spans, 1.0])
        self._cells: dict[tuple[int, int], list[int]] = {}
        for index, frame in enumerate(frames):
            x0, y0, x1, y1 = frame.bbox
            for cx in range(int(x0 // self._cell), int(x1 // self._cell) + 1):
                for cy in range(int(y0 // self._cell), int(y1 // self._cell) + 1):
                    self._cells.setdefault((cx, cy), []).append(index)

    def find(self, x: float, y: float) -> int | None:
        """Index of the frame containing ``(x, y)``, lowest ``sort_index`` on a tie."""
        bucket = self._cells.get((int(x // self._cell), int(y // self._cell)))
        if not bucket:
            return None
        for index in bucket:
            box = self._frames[index].bbox
            if box[0] <= x <= box[2] and box[1] <= y <= box[3]:
                return index
        return None


class _CentreFinder:
    """The bounding-box centre of one top-level entity, as cheaply as possible.

    Assignment only ever asks one question of an entity -- where is its centre
    -- and on a real drawing the honest answer is expensive: ``ezdxf.bbox``
    expands an INSERT's whole block, recursively, every single time. A file
    with 70,000 entities spends most of its assignment re-expanding the same
    handful of block definitions.

    So INSERTs are answered from a per-block memo instead: a definition is
    measured once, and every reference to it costs four point transforms
    (:meth:`_block_box`). On the real 기계 drawing that is 12.4 seconds down to
    3.2 for 128,000 entities. Attributes attached to a reference are not
    counted -- a title block's stamp text cannot move its centre onto another
    sheet.

    Everything else goes through ``ezdxf.bbox.extents(fast=True)``: control
    points rather than the exact curve envelope, off by a bulge on an arc and
    by nothing that matters when the question is which of two sheets metres
    apart the entity is on.
    """

    def __init__(self, doc: Drawing) -> None:
        self._doc = doc
        self._cache = ezdxf.bbox.Cache()
        self._block_boxes: dict[str, tuple[float, float, float, float] | None] = {}

    def _block_box(self, name: str) -> tuple[float, float, float, float] | None:
        """The extents of one block definition, in its own coordinates.

        Written as an explicit recursion with a per-name memo instead of one
        ``ezdxf.bbox.extents(block)`` call, because ezdxf re-expands every
        nested block on every visit. In the real set's 기계 drawing the four
        floor-plan blocks cost 2.5 seconds each that way, and they share most
        of their content; memoised, each definition is measured once and a
        nested reference costs four point transforms.

        A nested reference contributes the axis-aligned box of its transformed
        box, which for a *rotated* nested block is slightly larger than its
        true extents. That is deliberate: it is conservative, it is bounded by
        the block's own size, and the only use of the result is deciding which
        metre-wide sheet an entity sits on.
        """
        if name in self._block_boxes:
            return self._block_boxes[name]
        self._block_boxes[name] = None  # cycle guard: a block that inserts itself
        block = self._doc.blocks.get(name)
        if block is None:
            return None

        box: tuple[float, float, float, float] | None = None
        for entity in block:
            part: tuple[float, float, float, float] | None
            if entity.dxftype() == "INSERT":
                child = self._block_box(_nfc(str(entity.dxf.name)))
                part = None if child is None else _transform_box(child, entity.matrix44())
            else:
                measured = ezdxf.bbox.extents([entity], fast=True, cache=self._cache)
                part = (
                    (
                        float(measured.extmin.x),
                        float(measured.extmin.y),
                        float(measured.extmax.x),
                        float(measured.extmax.y),
                    )
                    if measured.has_data
                    else None
                )
            if part is None:
                continue
            box = part if box is None else _union(box, list(part))

        self._block_boxes[name] = box
        return box

    def box(self, entity: Any) -> tuple[float, float, float, float] | None:
        """World-space ``(x0, y0, x1, y1)`` of one top-level entity."""
        if entity.dxftype() == "INSERT":
            local = self._block_box(_nfc(str(entity.dxf.name)))
            return None if local is None else _transform_box(local, entity.matrix44())
        measured = ezdxf.bbox.extents([entity], fast=True, cache=self._cache)
        if not measured.has_data:
            return None
        return (
            float(measured.extmin.x),
            float(measured.extmin.y),
            float(measured.extmax.x),
            float(measured.extmax.y),
        )

    def centre(self, entity: Any) -> tuple[float, float] | None:
        """Centre of :meth:`box`.

        Exact for an INSERT even though the box is a transformed box: an affine
        map sends a rectangle's four corners to a parallelogram symmetric about
        the mapped centre, so the midpoint of its axis-aligned hull *is* the
        mapped centre (``test_insert_centres_match_the_full_bounding_box``).
        """
        box = self.box(entity)
        if box is None:
            return None
        return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)

    def model_extents(self) -> tuple[float, float, float, float] | None:
        """The whole model space, through the same memo.

        This is what an unrecognised file's frame covers, and going through the
        memo rather than ``ezdxf.bbox.extents(modelspace())`` is the difference
        between 3 seconds and 20 on the real 통신 drawing.
        """
        box: tuple[float, float, float, float] | None = None
        for entity in self._doc.modelspace():
            part = self.box(entity)
            if part is None:
                continue
            box = part if box is None else _union(box, list(part))
        return box


def assign_entities(doc: Drawing, frames: list[FrameRecord]) -> None:
    """Give every top-level model-space entity to the frame it sits in.

    ``frames.yaml`` ``frame.assign = bbox_center``: an entity that straddles
    two sheets belongs to the one its centre is in, and an entity whose centre
    is on no sheet (a note in the margin, a stray construction line) belongs to
    none -- it is simply not compared. Handles come back sorted, so two runs
    over the same file produce the same list.

    Budget: under 30 seconds for a 350,000-entity file (brief Constraints).
    :class:`_CentreFinder` is where that is won; :class:`_FrameGrid` is what
    keeps the "which of a hundred sheets" lookup off the critical path.
    """
    title_index = {
        frame.titleblock_handle: index
        for index, frame in enumerate(frames)
        if frame.titleblock_handle
    }
    if len(frames) == 1 and frames[0].kind == KIND_UNRECOGNIZED:
        frames[0].entity_handles = sorted(
            str(entity.dxf.handle) for entity in doc.modelspace() if entity.dxf.hasattr("handle")
        )
        return

    grid = _FrameGrid(frames)
    finder = _CentreFinder(doc)
    buckets: list[list[str]] = [[] for _ in frames]
    for entity in doc.modelspace():
        handle = str(entity.dxf.get("handle", "") or "")
        if not handle:
            continue
        index = title_index.get(handle)
        if index is None:
            centre = finder.centre(entity)
            if centre is None:
                continue
            index = grid.find(centre[0], centre[1])
        if index is not None:
            buckets[index].append(handle)

    for frame, handles in zip(frames, buckets, strict=True):
        frame.entity_handles = sorted(handles)


# --------------------------------------------------------------------------- worker entry


def extract_file_frames(
    working_dxf_path: str, file_id: str, config: FramesConfig
) -> FileFramesResult:
    """Open one working DXF and return its frames. Runs in a worker process.

    Module level and built-in arguments only, because the job runner's pool is
    a spawning :class:`~concurrent.futures.ProcessPoolExecutor` (``api/jobs.py``)
    -- the ezdxf document never crosses the boundary, only the dataclasses.
    Any failure comes back as :attr:`FileFramesResult.error` rather than an
    exception, so one unreadable conversion costs one file and not the job.
    """
    try:
        doc = ezdxf.readfile(working_dxf_path)
    except Exception as exc:  # noqa: BLE001 - reported per file, see docstring
        return FileFramesResult(file_id=file_id, error=f"{type(exc).__name__}: {exc}")

    try:
        frames = extract_frames(doc, file_id=file_id, config=config)
        started = time.perf_counter()
        assign_entities(doc, frames)
        elapsed = time.perf_counter() - started
    except Exception as exc:  # noqa: BLE001 - same reason
        return FileFramesResult(file_id=file_id, error=f"{type(exc).__name__}: {exc}")

    return FileFramesResult(
        file_id=file_id,
        frames=frames,
        warnings=sorted({w for frame in frames for w in frame.warnings}),
        entity_count=len(doc.modelspace()),
        assign_seconds=round(elapsed, 3),
    )


__all__ = [
    "A1_HEIGHT_MM",
    "A1_WIDTH_MM",
    "BOUNDARY_A1",
    "BOUNDARY_EXTENTS",
    "BOUNDARY_MODAL",
    "BOUNDARY_RECT",
    "DEFAULT_SCALE_DENOMINATOR",
    "KIND_TITLEBLOCK",
    "KIND_UNRECOGNIZED",
    "MAX_NESTING_DEPTH",
    "FileFramesResult",
    "FrameRecord",
    "assign_entities",
    "extract_file_frames",
    "extract_frames",
    "file_norm_key",
    "normalize_key",
    "parse_scale",
]
