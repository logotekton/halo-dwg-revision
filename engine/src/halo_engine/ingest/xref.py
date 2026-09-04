"""XREF path resolution and embedding (brief W2-03, W3-06; ADR-0002 "working DXF").

Resolution order (brief Constraints, "ADR-0002 §XREF"):

1. the stored path, if it is absolute and exists;
2. the same folder as the host document, using the declared path's basename;
3. the declared path resolved relative to the host document's folder;
4. each ``--search-path`` directory, in order given;
5. a case-insensitive, extension-insensitive basename match under the host
   folder and every search path.

**W3-06 amendment (addenda 1-2, "실도면 확인"/"W3-09 실측"):** the real
drawing set stores every XREF path as a Windows relative path
(``..\\XR\\파일.dwg``, 133/133 in the sample set) and macOS directory
listings are NFD-normalised while the DXF's path strings are NFC --
:func:`resolve_xref_path` now normalises both (backslash -> ``/``, NFC) and
treats an empty declared path or a resolved directory as unresolved instead
of raising ``IsADirectoryError`` (the ``host_dir / ""`` bug the spike
found). It also recurses: an XREF target that turns out to be a ``.dwg``
(the real set's XR/ folder is DWG-only) is converted to DXF by an injected
``dwg_converter`` callable before being loaded, and *that* document's own
XREF definitions are embedded depth-first before it is spliced into the
host -- with cycle detection so a circular XREF graph terminates instead of
recursing forever. A single unresolved definition no longer aborts the
whole host: :func:`embed_all_xrefs` collects it into ``EmbedOutcome.unresolved``
and keeps going, so the caller (``ingest/working_dxf.py`` -> ``api/jobs.py``)
can still finish the import and surface the remainder to the UI dialog
(``api/routers/xrefs.py``).

Embedding uses :class:`ezdxf.xref.Loader` (the same building block
``ezdxf.xref.embed`` is written on top of) rather than ``embed`` itself,
because we need our own path resolution (``embed``'s built-in
:func:`ezdxf.xref.find_xref` only covers tiers 1-4 above) and a bound
handle map, which the public ``embed()`` wrapper does not return. Loading
the XREF file both standalone (for its original handles, in modelspace
order) and via ``Loader`` (whose ``LoadEntities`` command appends copies to
the target block in that same source order -- verified against ezdxf
1.4.4's ``xref.py``) lets us zip the two into an ``{xref_file,
original_handle, bound_handle}`` map using only public ezdxf API.
"""

from __future__ import annotations

import fnmatch
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import ezdxf.xref as ezdxf_xref
from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout
from ezdxf.math import Vec3

from halo_engine.ingest.dxf_loader import load_dxf

#: Same default as ezdxf.xref.embed.
DEFAULT_CONFLICT_POLICY = ezdxf_xref.ConflictPolicy.XREF_PREFIX

#: brief addendum 3 / G1 답변: project setting ``import.ignore_patterns`` default.
DEFAULT_IGNORE_PATTERNS: tuple[str, ...] = ("*_recover.dwg", "*.bak")

#: Given a resolved XREF target's path that turns out to be a ``.dwg``,
#: converts it to DXF (its own cache-backed pipeline) and returns the DXF
#: path. Supplied by ``ingest/pipeline.py`` (the only module that can reach
#: a converter -- acad-ts subprocess today, the desktop's ``convert.request``
#: once wired), never constructed here.
DwgXrefConverter = Callable[[Path], Path]


def is_ignored_name(name: str, patterns: Sequence[str] | None) -> bool:
    """``import.ignore_patterns`` glob match, case-insensitive (brief addendum 3)."""
    if not patterns:
        return False
    lowered = name.lower()
    return any(fnmatch.fnmatch(lowered, pattern.lower()) for pattern in patterns)


@dataclass(frozen=True)
class XrefDefinition:
    """One XREF block definition found in a host document."""

    block_name: str
    xref_path: str


@dataclass(frozen=True)
class HandleMapEntry:
    xref_file: str
    original_handle: str
    bound_handle: str

    def to_dict(self) -> dict[str, str]:
        return {
            "xref_file": self.xref_file,
            "original_handle": self.original_handle,
            "bound_handle": self.bound_handle,
        }


@dataclass(frozen=True)
class ResolvedXrefLink:
    """One XREF definition that was found and embedded (``xref_link`` table row shape)."""

    block_name: str
    declared_path: str
    resolved_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "block_name": self.block_name,
            "declared_path": self.declared_path,
            "resolved_path": self.resolved_path,
        }


@dataclass(frozen=True)
class UnresolvedXref:
    """One XREF definition that could not be embedded, and why."""

    block_name: str
    declared_path: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "block_name": self.block_name,
            "declared_path": self.declared_path,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ConvertedXrefDwg:
    """One XREF target that was itself a DWG and had to be converted first."""

    block_name: str
    source_dwg: str
    dxf_path: str

    def to_dict(self) -> dict[str, str]:
        return {
            "block_name": self.block_name,
            "source_dwg": self.source_dwg,
            "dxf_path": self.dxf_path,
        }


@dataclass(frozen=True)
class EmbedOutcome:
    """Result of embedding one or every XREF definition in a document."""

    handle_map: list[HandleMapEntry] = field(default_factory=list)
    resolved: list[ResolvedXrefLink] = field(default_factory=list)
    unresolved: list[UnresolvedXref] = field(default_factory=list)
    converted: list[ConvertedXrefDwg] = field(default_factory=list)


class XrefUnresolvedError(RuntimeError):
    """One XREF definition could not be resolved, converted, or embedded."""

    def __init__(self, xref_def: XrefDefinition, reason: str) -> None:
        super().__init__(f"xref {xref_def.xref_path!r} (block {xref_def.block_name!r}): {reason}")
        self.xref_def = xref_def
        self.reason = reason


def find_xref_definitions(doc: Drawing) -> list[XrefDefinition]:
    """Every XREF block definition in ``doc`` (attached or overlaid)."""
    defs: list[XrefDefinition] = []
    for block in doc.blocks:
        if block.block.is_xref:
            path = block.block.dxf.get("xref_path", "")
            defs.append(XrefDefinition(block_name=block.name, xref_path=path))
    return defs


def _nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def _existing_file(candidate: Path) -> Path | None:
    """``candidate.resolve()`` if it exists and is a file -- ``None`` for missing
    *or a directory* (W3-06 addendum 2: a resolved directory is unresolved,
    not a crash). Resolved (``..`` segments collapsed, symlinks followed) so
    the return value is stable regardless of how many ``../`` hops the
    declared path used to get there -- real-set paths are all ``..\\XR\\...``."""
    try:
        if candidate.exists() and not candidate.is_dir():
            return candidate.resolve()
    except OSError:
        return None
    return None


def resolve_xref_path(
    xref_path: str,
    *,
    host_dir: Path,
    search_paths: list[Path] | None = None,
    ignore_patterns: Sequence[str] | None = None,
) -> Path | None:
    """Resolve a declared XREF path to an existing file, or ``None``.

    Implements the 5-tier order documented at module level, plus the W3-06
    normalisation amendment: the declared path is backslash-normalised and
    NFC-normalised before any comparison (real-set paths are all
    ``..\\XR\\파일.dwg``-shaped Windows relative paths; macOS directory
    listings are NFD for Hangul names), an empty declared path resolves to
    ``None`` immediately, and tier 5's directory scan skips any entry
    matching ``ignore_patterns`` (default ``["*_recover.dwg", "*.bak"]``) so
    a same-stem backup file is never picked over a missing real target.
    """
    search_paths = search_paths or []
    stripped = xref_path.strip()
    if not stripped:
        return None

    normalized = _nfc(stripped.replace("\\", "/"))
    declared = Path(normalized)
    basename = PurePosixPath(normalized).name

    # 1. stored absolute path (a Windows drive-letter path like "C:/xicad/x.shx"
    #    is not POSIX-absolute after normalisation, so it falls through to the
    #    basename tiers below instead -- consistent with the real set, whose
    #    133 XREF paths are all relative).
    if declared.is_absolute():
        found = _existing_file(declared)
        if found is not None:
            return found

    # 2. host's same folder, by basename
    found = _existing_file(host_dir / basename)
    if found is not None:
        return found

    # 3. declared (relative) path, resolved against the host folder
    found = _existing_file(host_dir / declared)
    if found is not None:
        return found

    # 4. each configured search path
    for sp in search_paths:
        found = _existing_file(sp / declared)
        if found is not None:
            return found
        found = _existing_file(sp / basename)
        if found is not None:
            return found

    # 5. extension/case-insensitive basename search, NFC on both sides
    target = basename.casefold()
    target_stem = PurePosixPath(basename).stem.casefold()
    for directory in [host_dir, *search_paths]:
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            if is_ignored_name(entry.name, ignore_patterns):
                continue
            entry_name = _nfc(entry.name).casefold()
            entry_stem = _nfc(PurePosixPath(entry.name).stem).casefold()
            if entry_name == target or entry_stem == target_stem:
                return entry.resolve()

    return None


def embed_xref(
    doc: Drawing,
    xref_def: XrefDefinition,
    *,
    host_dir: Path,
    search_paths: list[Path] | None = None,
    conflict_policy: Any = DEFAULT_CONFLICT_POLICY,
    dwg_converter: DwgXrefConverter | None = None,
    ignore_patterns: Sequence[str] | None = None,
    _visited: frozenset[Path] | None = None,
) -> EmbedOutcome:
    """Embed one XREF definition into ``doc`` in place, returning its outcome.

    Raises :class:`XrefUnresolvedError` if the XREF cannot be resolved, its
    target is a ``.dwg`` with no ``dwg_converter`` configured, or that
    conversion fails -- callers that want a "keep going" import (everything
    from :func:`embed_all_xrefs` up) catch this; callers that want the old
    "abort on the first miss" behaviour can let it propagate.
    """
    search_paths = search_paths or []
    visited = _visited or frozenset()

    resolved = resolve_xref_path(
        xref_def.xref_path,
        host_dir=host_dir,
        search_paths=search_paths,
        ignore_patterns=ignore_patterns,
    )
    if resolved is None:
        raise XrefUnresolvedError(
            xref_def,
            f"not found in {host_dir} or search paths {[str(p) for p in search_paths]}",
        )
    resolved = resolved.resolve()

    if resolved in visited:
        # Circular XREF graph: this file is already being embedded further
        # up the recursion stack. Record it as resolved (it is not an
        # error) without re-entering the loader for it a second time.
        return EmbedOutcome(
            resolved=[ResolvedXrefLink(xref_def.block_name, xref_def.xref_path, str(resolved))]
        )

    converted: list[ConvertedXrefDwg] = []
    if resolved.suffix.lower() == ".dwg":
        if dwg_converter is None:
            raise XrefUnresolvedError(
                xref_def, f"xref target is a DWG and no converter is configured: {resolved}"
            )
        try:
            dxf_path = dwg_converter(resolved)
        except Exception as exc:  # noqa: BLE001 - surfaced as unresolved, not a crash
            raise XrefUnresolvedError(
                xref_def, f"could not convert DWG xref target: {exc}"
            ) from exc
        converted.append(ConvertedXrefDwg(xref_def.block_name, str(resolved), str(dxf_path)))
        source_path = Path(dxf_path)
    else:
        source_path = resolved

    try:
        load_result = load_dxf(str(source_path))
        source_doc = load_result.doc
        source_entities = list(source_doc.modelspace())

        # Depth-first: embed the target's own XREFs (if any) into it before
        # it is spliced into the host, so nested references resolve
        # relative to *their* file's folder, not the top-level host's.
        nested = embed_all_xrefs(
            source_doc,
            host_dir=resolved.parent,
            search_paths=search_paths,
            conflict_policy=conflict_policy,
            dwg_converter=dwg_converter,
            ignore_patterns=ignore_patterns,
            _visited=visited | {resolved},
        )
        converted.extend(nested.converted)

        block_layout: BlockLayout = doc.blocks[xref_def.block_name]
        if source_doc.dxfversion > doc.dxfversion:
            raise ezdxf_xref.const.DXFVersionError(
                "cannot embed a XREF with a newer DXF version than the host document"
            )

        loader = ezdxf_xref.Loader(source_doc, doc, conflict_policy=conflict_policy)
        loader.load_modelspace(block_layout)
        loader.execute(xref_prefix=block_layout.name)

        block = block_layout.block
        block.set_flag_state(ezdxf_xref.const.BLK_XREF | ezdxf_xref.const.BLK_EXTERNAL, state=False)
        origin = source_doc.header.get("$INSBASE")
        if origin:
            block.dxf.base_point = Vec3(origin)

        target_entities = list(block_layout)
        xref_file = resolved.name
        handle_map = [
            HandleMapEntry(
                xref_file=xref_file,
                original_handle=src.dxf.handle,
                bound_handle=tgt.dxf.handle,
            )
            for src, tgt in zip(source_entities, target_entities, strict=False)
        ]
    except XrefUnresolvedError:
        raise
    except Exception as exc:
        # A malformed target file (most often a known acad-ts DXF-writer
        # gap -- ATTRIB sub-entities ezdxf's own xref.Loader cannot clone,
        # the same class of bug ADR-0002's amendment already documents for
        # top-level hosts) must not take the *whole* import down with it.
        # One bad XREF becomes one unresolved entry the UI dialog can show
        # and let the user work around, not a FAILED host.
        raise XrefUnresolvedError(xref_def, f"could not embed {source_path.name}: {exc}") from exc

    return EmbedOutcome(
        handle_map=handle_map,
        resolved=[
            ResolvedXrefLink(xref_def.block_name, xref_def.xref_path, str(resolved)),
            *nested.resolved,
        ],
        unresolved=list(nested.unresolved),
        converted=converted,
    )


def embed_all_xrefs(
    doc: Drawing,
    *,
    host_dir: Path,
    search_paths: list[Path] | None = None,
    conflict_policy: Any = DEFAULT_CONFLICT_POLICY,
    dwg_converter: DwgXrefConverter | None = None,
    ignore_patterns: Sequence[str] | None = None,
    _visited: frozenset[Path] | None = None,
) -> EmbedOutcome:
    """Embed every XREF definition found in ``doc``, in block-table order.

    Unlike :func:`embed_xref`, a single unresolved (or unconvertible)
    definition does not abort the rest -- it is collected into the
    returned :class:`EmbedOutcome`'s ``unresolved`` list so the caller can
    still finish the import and let the UI dialog (brief Goal) offer a
    search path or a manual match for just that one.
    """
    handle_map: list[HandleMapEntry] = []
    resolved: list[ResolvedXrefLink] = []
    unresolved: list[UnresolvedXref] = []
    converted: list[ConvertedXrefDwg] = []
    for xref_def in find_xref_definitions(doc):
        try:
            outcome = embed_xref(
                doc,
                xref_def,
                host_dir=host_dir,
                search_paths=search_paths,
                conflict_policy=conflict_policy,
                dwg_converter=dwg_converter,
                ignore_patterns=ignore_patterns,
                _visited=_visited,
            )
        except XrefUnresolvedError as exc:
            unresolved.append(UnresolvedXref(xref_def.block_name, xref_def.xref_path, exc.reason))
            continue
        handle_map.extend(outcome.handle_map)
        resolved.extend(outcome.resolved)
        unresolved.extend(outcome.unresolved)
        converted.extend(outcome.converted)
    return EmbedOutcome(
        handle_map=handle_map, resolved=resolved, unresolved=unresolved, converted=converted
    )


__all__ = [
    "DEFAULT_CONFLICT_POLICY",
    "DEFAULT_IGNORE_PATTERNS",
    "ConvertedXrefDwg",
    "DwgXrefConverter",
    "EmbedOutcome",
    "HandleMapEntry",
    "ResolvedXrefLink",
    "UnresolvedXref",
    "XrefDefinition",
    "XrefUnresolvedError",
    "embed_all_xrefs",
    "embed_xref",
    "find_xref_definitions",
    "is_ignored_name",
    "resolve_xref_path",
]
