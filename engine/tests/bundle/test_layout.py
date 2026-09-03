from __future__ import annotations

from pathlib import Path

import pytest

from halo_engine.bundle.layout import BundleLayout, default_bundle_path


def test_default_bundle_path_is_documents_halo_cad(monkeypatch: pytest.MonkeyPatch) -> None:
    import halo_engine.bundle.layout as layout_mod

    fake_root = Path("/home/fake-user") / "Documents" / "Halo CAD"
    monkeypatch.setattr(layout_mod, "DEFAULT_PROJECTS_ROOT", fake_root)
    assert default_bundle_path("Apartment A") == fake_root / "Apartment A.halo"


def test_layout_paths_are_relative_to_root(tmp_path: Path) -> None:
    root = tmp_path / "demo.halo"
    layout = BundleLayout(root)

    assert layout.project_json == root / "project.json"
    assert layout.project_sqlite == root / "project.sqlite"
    assert layout.originals_dir == root / "originals"
    assert layout.cache_dxf_dir == root / "cache" / "dxf"
    assert layout.cache_mesh_dir == root / "cache" / "mesh"
    assert layout.derivatives_dir == root / "derivatives"
    assert layout.sidecars_dir == root / "sidecars"
    assert layout.exports_dir == root / "exports"


def test_ensure_dirs_creates_every_subdirectory(tmp_path: Path) -> None:
    layout = BundleLayout(tmp_path / "demo.halo")
    layout.ensure_dirs()

    assert layout.originals_dir.is_dir()
    assert layout.cache_dxf_dir.is_dir()
    assert layout.cache_mesh_dir.is_dir()
    assert layout.derivatives_dir.is_dir()
    assert layout.sidecars_dir.is_dir()
    assert layout.exports_dir.is_dir()
