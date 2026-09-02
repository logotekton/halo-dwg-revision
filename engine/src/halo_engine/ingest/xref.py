"""XREF path resolution and embedding (brief W2-03, ADR-0002 "working DXF").

Resolution order (brief Constraints, "ADR-0002 §XREF"):

1. the stored path, if it is absolute and exists;
2. the same folder as the host document, using the declared path's basename;
3. the declared path resolved relative to the host document's folder;
4. each ``--search-path`` directory, in order given;
5. a case-insensitive, extension-insensitive basename match under the host
   folder and every search path.

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

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ezdxf.xref as ezdxf_xref
from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout
from ezdxf.math import Vec3

from halo_engine.ingest.dxf_loader import load_dxf

#: Same default as ezdxf.xref.embed.
DEFAULT_CONFLICT_POLICY = ezdxf_xref.ConflictPolicy.XREF_PREFIX


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


def find_xref_definitions(doc: Drawing) -> list[XrefDefinition]:
    """Every XREF block definition in ``doc`` (attached or overlaid)."""
    defs: list[XrefDefinition] = []
    for block in doc.blocks:
        if block.block.is_xref:
            path = block.block.dxf.get("xref_path", "")
            defs.append(XrefDefinition(block_name=block.name, xref_path=path))
    return defs


def resolve_xref_path(
    xref_path: str, *, host_dir: Path, search_paths: list[Path] | None = None
) -> Path | None:
    """Resolve a declared XREF path to an existing file, or ``None``.

    Implements the 5-tier order documented at module level.
    """
    search_paths = search_paths or []
    declared = Path(xref_path)
    basename = declared.name

    # 1. stored absolute path
    if declared.is_absolute() and declared.exists():
        return declared

    # 2. host's same folder, by basename
    candidate = host_dir / basename
    if candidate.exists():
        return candidate

    # 3. declared (relative) path, resolved against the host folder
    candidate = host_dir / declared
    if candidate.exists():
        return candidate

    # 4. each configured search path
    for sp in search_paths:
        candidate = sp / declared
        if candidate.exists():
            return candidate
        candidate = sp / basename
        if candidate.exists():
            return candidate

    # 5. extension/case-insensitive basename search
    target = basename.casefold()
    target_stem = declared.stem.casefold()
    for directory in [host_dir, *search_paths]:
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            if not entry.is_file():
                continue
            if entry.name.casefold() == target or entry.stem.casefold() == target_stem:
                return entry

    return None


def embed_xref(
    doc: Drawing,
    xref_def: XrefDefinition,
    *,
    host_dir: Path,
    search_paths: list[Path] | None = None,
    conflict_policy: Any = DEFAULT_CONFLICT_POLICY,
) -> list[HandleMapEntry]:
    """Embed one XREF definition into ``doc`` in place, returning its handle map.

    Raises :class:`FileNotFoundError` if the XREF file cannot be resolved.
    """
    resolved = resolve_xref_path(xref_def.xref_path, host_dir=host_dir, search_paths=search_paths)
    if resolved is None:
        raise FileNotFoundError(
            f"xref '{xref_def.xref_path}' (block {xref_def.block_name!r}) not found "
            f"in {host_dir} or search paths {search_paths or []}"
        )

    load_result = load_dxf(str(resolved))
    source_doc = load_result.doc
    source_entities = list(source_doc.modelspace())

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
    return [
        HandleMapEntry(
            xref_file=xref_file,
            original_handle=src.dxf.handle,
            bound_handle=tgt.dxf.handle,
        )
        for src, tgt in zip(source_entities, target_entities, strict=False)
    ]


def embed_all_xrefs(
    doc: Drawing,
    *,
    host_dir: Path,
    search_paths: list[Path] | None = None,
    conflict_policy: Any = DEFAULT_CONFLICT_POLICY,
) -> list[HandleMapEntry]:
    """Embed every XREF definition found in ``doc``, in block-table order."""
    handle_map: list[HandleMapEntry] = []
    for xref_def in find_xref_definitions(doc):
        handle_map.extend(
            embed_xref(
                doc,
                xref_def,
                host_dir=host_dir,
                search_paths=search_paths,
                conflict_policy=conflict_policy,
            )
        )
    return handle_map


__all__ = [
    "DEFAULT_CONFLICT_POLICY",
    "HandleMapEntry",
    "XrefDefinition",
    "embed_all_xrefs",
    "embed_xref",
    "find_xref_definitions",
    "resolve_xref_path",
]
