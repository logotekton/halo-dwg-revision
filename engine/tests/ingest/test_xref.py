from __future__ import annotations

from pathlib import Path

import ezdxf

from halo_engine.ingest.xref import (
    embed_all_xrefs,
    find_xref_definitions,
    resolve_xref_path,
)


def test_resolve_xref_path_tier1_stored_absolute(tmp_path: Path) -> None:
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    absolute_target = tmp_path / "elsewhere" / "grid.dxf"
    absolute_target.parent.mkdir()
    absolute_target.write_text("x", encoding="utf-8")

    resolved = resolve_xref_path(str(absolute_target), host_dir=host_dir)
    assert resolved == absolute_target


def test_resolve_xref_path_tier2_host_same_folder(tmp_path: Path) -> None:
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "grid.dxf").write_text("x", encoding="utf-8")

    resolved = resolve_xref_path("grid.dxf", host_dir=host_dir)
    assert resolved == host_dir / "grid.dxf"


def test_resolve_xref_path_tier3_relative_to_host(tmp_path: Path) -> None:
    host_dir = tmp_path / "host"
    (host_dir / "sub").mkdir(parents=True)
    (host_dir / "sub" / "grid.dxf").write_text("x", encoding="utf-8")

    resolved = resolve_xref_path("sub/grid.dxf", host_dir=host_dir)
    assert resolved == host_dir / "sub" / "grid.dxf"


def test_resolve_xref_path_tier4_search_paths(tmp_path: Path) -> None:
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    search_dir = tmp_path / "shared"
    search_dir.mkdir()
    (search_dir / "grid.dxf").write_text("x", encoding="utf-8")

    resolved = resolve_xref_path("grid.dxf", host_dir=host_dir, search_paths=[search_dir])
    assert resolved == search_dir / "grid.dxf"


def test_resolve_xref_path_tier5_case_and_extension_insensitive_basename(tmp_path: Path) -> None:
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    # Different extension (not just different case) so tiers 1-4's exact
    # existence checks cannot accidentally succeed even on a case-insensitive
    # filesystem (macOS APFS default) -- only the tier-5 stem fallback finds it.
    (host_dir / "GRID.dxf").write_text("x", encoding="utf-8")

    resolved = resolve_xref_path("grid.DWG", host_dir=host_dir)
    assert resolved == host_dir / "GRID.dxf"


def test_resolve_xref_path_returns_none_when_not_found(tmp_path: Path) -> None:
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    assert resolve_xref_path("nope.dxf", host_dir=host_dir) is None


def test_find_xref_definitions_on_f10_host(generated_dir: Path) -> None:
    doc = ezdxf.readfile(str(generated_dir / "F10_host.dxf"))
    defs = find_xref_definitions(doc)
    assert len(defs) == 1
    assert defs[0].block_name == "F10_GRID"
    assert defs[0].xref_path == "F10_grid.dxf"


def test_embed_all_xrefs_on_f10_host(generated_dir: Path) -> None:
    host_path = generated_dir / "F10_host.dxf"
    doc = ezdxf.readfile(str(host_path))

    handle_map = embed_all_xrefs(doc, host_dir=host_path.parent)

    assert len(handle_map) > 0
    assert all(e.xref_file == "F10_grid.dxf" for e in handle_map)
    bound_handles = {e.bound_handle for e in handle_map}
    assert len(bound_handles) == len(handle_map), "bound handles must be unique"

    block = doc.blocks["F10_GRID"]
    assert block.block.is_xref is False, "embedding must clear the XREF flag"
    types = {}
    for e in block:
        types[e.dxftype()] = types.get(e.dxftype(), 0) + 1
    assert types == {"LINE": 5, "INSERT": 6}

    # top-level host content is unaffected by embedding (contract: block
    # definitions, xref or not, are never counted at the top level).
    top_level_types = {}
    for e in doc.modelspace():
        top_level_types[e.dxftype()] = top_level_types.get(e.dxftype(), 0) + 1
    assert top_level_types == {"INSERT": 1, "LWPOLYLINE": 6, "TEXT": 6}
