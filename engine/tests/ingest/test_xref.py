from __future__ import annotations

import unicodedata
from pathlib import Path

import ezdxf
import pytest

from halo_engine.ingest.xref import (
    XrefDefinition,
    embed_all_xrefs,
    embed_xref,
    find_xref_definitions,
    is_ignored_name,
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


# --- W3-06 addendum 2: backslash / NFC / empty / directory-result amendments -------------


def test_resolve_xref_path_normalizes_windows_backslash_relative_path(tmp_path: Path) -> None:
    """The real set's 133 XREF paths are all ``..\\XR\\파일.dwg``-shaped."""
    host_dir = tmp_path / "host" / "01_건축"
    host_dir.mkdir(parents=True)
    xr_dir = tmp_path / "host" / "XR"
    xr_dir.mkdir()
    (xr_dir / "TITLE BLOCK-V.dwg").write_bytes(b"x")

    resolved = resolve_xref_path(r"..\XR\TITLE BLOCK-V.dwg", host_dir=host_dir)
    assert resolved == xr_dir / "TITLE BLOCK-V.dwg"


def test_resolve_xref_path_empty_string_is_immediately_unresolved(tmp_path: Path) -> None:
    """Previously ``host_dir / ""`` == ``host_dir`` -- an existing directory --
    which made the old resolver return a directory and blow up downstream
    with ``IsADirectoryError``. An empty declared path is just unresolved."""
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    assert resolve_xref_path("", host_dir=host_dir) is None
    assert resolve_xref_path("   ", host_dir=host_dir) is None


def test_resolve_xref_path_directory_result_is_unresolved(tmp_path: Path) -> None:
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "grid.dxf").mkdir()  # a directory that happens to share the target's name

    assert resolve_xref_path("grid.dxf", host_dir=host_dir) is None


def test_resolve_xref_path_nfc_normalizes_declared_and_directory_entries(tmp_path: Path) -> None:
    """macOS directory listings are NFD for Hangul filenames; the DXF's
    stored path string is NFC (W3-09 실측: 김화중공업고등학교 등 3종이
    정규화 없이는 "없는 파일"로 보였다)."""
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    nfc_name = unicodedata.normalize("NFC", "현황도_김화중공업고등학교.dwg")
    nfd_name = unicodedata.normalize("NFD", nfc_name)
    assert nfc_name != nfd_name, "fixture precondition: the name must actually decompose"
    (host_dir / nfd_name).write_bytes(b"x")  # simulate an NFD filesystem entry

    resolved = resolve_xref_path(nfc_name, host_dir=host_dir)
    assert resolved is not None
    assert unicodedata.normalize("NFC", resolved.name) == nfc_name


def test_resolve_xref_path_skips_ignored_names_in_tier5(tmp_path: Path) -> None:
    """A same-stem ``.bak``/``_recover.dwg`` sibling must never win tier 5's
    stem fallback over a missing real target (brief addendum 3)."""
    host_dir = tmp_path / "host"
    host_dir.mkdir()
    (host_dir / "PLAN.bak").write_bytes(b"x")

    from halo_engine.ingest.xref import DEFAULT_IGNORE_PATTERNS

    # Without an ignore list, tier 5's stem fallback matches PLAN.bak (the
    # bug this addendum guards against); with it, PLAN.bak is skipped and
    # the target is correctly reported unresolved instead.
    assert resolve_xref_path("PLAN.dwg", host_dir=host_dir) == host_dir / "PLAN.bak"
    assert (
        resolve_xref_path("PLAN.dwg", host_dir=host_dir, ignore_patterns=DEFAULT_IGNORE_PATTERNS)
        is None
    )


def test_is_ignored_name() -> None:
    from halo_engine.ingest.xref import DEFAULT_IGNORE_PATTERNS

    assert is_ignored_name("A-520 부분확대 상세도_recover.dwg", DEFAULT_IGNORE_PATTERNS)
    assert is_ignored_name("PLAN.BAK", DEFAULT_IGNORE_PATTERNS)
    assert not is_ignored_name("PLAN.dwg", DEFAULT_IGNORE_PATTERNS)
    assert not is_ignored_name("PLAN.dwg", None)


def test_find_xref_definitions_on_f10_host(generated_dir: Path) -> None:
    doc = ezdxf.readfile(str(generated_dir / "F10_host.dxf"))
    defs = find_xref_definitions(doc)
    assert len(defs) == 1
    assert defs[0].block_name == "F10_GRID"
    assert defs[0].xref_path == "F10_grid.dxf"


def test_embed_all_xrefs_on_f10_host(generated_dir: Path) -> None:
    host_path = generated_dir / "F10_host.dxf"
    doc = ezdxf.readfile(str(host_path))

    outcome = embed_all_xrefs(doc, host_dir=host_path.parent)
    handle_map = outcome.handle_map

    assert len(handle_map) > 0
    assert not outcome.unresolved
    assert all(e.xref_file == "F10_grid.dxf" for e in handle_map)
    bound_handles = {e.bound_handle for e in handle_map}
    assert len(bound_handles) == len(handle_map), "bound handles must be unique"
    assert [r.block_name for r in outcome.resolved] == ["F10_GRID"]

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


def test_embed_all_xrefs_collects_unresolved_instead_of_raising(tmp_path: Path) -> None:
    """A missing XREF target must not abort the whole document -- the brief's
    UI dialog needs the list of what is still missing, not a stack trace."""
    doc = ezdxf.new("R2018")
    doc.blocks.new(name="MISSING", dxfattribs={"flags": 4})
    block = doc.blocks["MISSING"]
    block.block.dxf.xref_path = "nope.dxf"
    doc.modelspace().add_blockref("MISSING", (0, 0))

    outcome = embed_all_xrefs(doc, host_dir=tmp_path)

    assert outcome.handle_map == []
    assert outcome.resolved == []
    assert len(outcome.unresolved) == 1
    assert outcome.unresolved[0].block_name == "MISSING"
    assert outcome.unresolved[0].declared_path == "nope.dxf"


def test_embed_xref_raises_when_target_is_dwg_and_no_converter_configured(tmp_path: Path) -> None:
    doc = ezdxf.new("R2018")
    doc.blocks.new(name="MISSING", dxfattribs={"flags": 4})
    doc.blocks["MISSING"].block.dxf.xref_path = "target.dwg"
    (tmp_path / "target.dwg").write_bytes(b"not a real dwg")

    xref_def = XrefDefinition(block_name="MISSING", xref_path="target.dwg")
    with pytest.raises(Exception) as excinfo:
        embed_xref(doc, xref_def, host_dir=tmp_path)
    assert "converter" in str(excinfo.value)


def test_embed_xref_converts_a_dwg_target_via_the_injected_converter(
    tmp_path: Path, generated_dir: Path
) -> None:
    """W3-06 addendum 1: a ``.dwg`` xref target is converted via the caller's
    ``dwg_converter`` hook before being embedded -- exercised here with a
    trivial converter that just points at the already-generated F10_grid.dxf
    (the real acad-ts conversion path is covered by ``tests/api/test_xref_import.py``).
    """
    doc = ezdxf.new("R2018")
    doc.blocks.new(name="F10_GRID", dxfattribs={"flags": 4})
    doc.blocks["F10_GRID"].block.dxf.xref_path = "grid.dwg"
    fake_dwg = tmp_path / "grid.dwg"
    fake_dwg.write_bytes(b"placeholder -- never actually read by ezdxf")

    calls: list[Path] = []

    def fake_converter(dwg_path: Path) -> Path:
        calls.append(dwg_path)
        return generated_dir / "F10_grid.dxf"

    outcome = embed_all_xrefs(doc, host_dir=tmp_path, dwg_converter=fake_converter)

    assert calls == [fake_dwg.resolve()]
    assert not outcome.unresolved
    assert len(outcome.converted) == 1
    assert outcome.converted[0].block_name == "F10_GRID"
    assert outcome.converted[0].source_dwg == str(fake_dwg.resolve())
    assert len(outcome.handle_map) > 0


def test_embed_all_xrefs_detects_circular_reference(tmp_path: Path) -> None:
    """A -> B -> A must terminate, not recurse forever."""
    doc_a = ezdxf.new("R2018")
    doc_a.blocks.new(name="B_REF", dxfattribs={"flags": 4})
    doc_a.blocks["B_REF"].block.dxf.xref_path = "b.dxf"
    doc_a.modelspace().add_blockref("B_REF", (0, 0))
    doc_a.saveas(str(tmp_path / "a.dxf"))

    doc_b = ezdxf.new("R2018")
    doc_b.blocks.new(name="A_REF", dxfattribs={"flags": 4})
    doc_b.blocks["A_REF"].block.dxf.xref_path = "a.dxf"
    doc_b.modelspace().add_blockref("A_REF", (0, 0))
    doc_b.saveas(str(tmp_path / "b.dxf"))

    doc = ezdxf.readfile(str(tmp_path / "a.dxf"))
    # Should complete without a RecursionError / infinite loop.
    outcome = embed_all_xrefs(doc, host_dir=tmp_path)
    assert not outcome.unresolved


def test_ignore_patterns_default_matches_brief_addendum_3() -> None:
    from halo_engine.ingest.xref import DEFAULT_IGNORE_PATTERNS

    assert DEFAULT_IGNORE_PATTERNS == ("*_recover.dwg", "*.bak")
