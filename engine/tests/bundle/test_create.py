"""``bundle/create.py`` -- create_bundle / open_bundle."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from halo_engine.bundle.create import BundleError, create_bundle, open_bundle
from halo_engine.db import repos


def test_create_bundle_writes_the_full_layout_and_a_project_row(tmp_path: Path) -> None:
    root = tmp_path / "demo.halo"
    handle = create_bundle(root, "demo")

    assert handle.bundle_path == root
    assert handle.name == "demo"
    assert root.is_dir()
    assert (root / "project.json").is_file()
    assert (root / "project.sqlite").is_file()
    assert (root / "originals").is_dir()

    meta = json.loads((root / "project.json").read_text(encoding="utf-8"))
    assert meta["id"] == handle.id
    assert meta["name"] == "demo"

    with handle.session_factory() as session:
        row = repos.get_project(session, handle.id)
        assert row is not None
        assert row.name == "demo"
        assert row.bundle_path == str(root)


def test_create_bundle_refuses_a_nonempty_existing_directory(tmp_path: Path) -> None:
    root = tmp_path / "occupied.halo"
    root.mkdir()
    (root / "junk.txt").write_text("x")

    with pytest.raises(BundleError):
        create_bundle(root, "occupied")


def test_open_bundle_reopens_the_same_project(tmp_path: Path) -> None:
    root = tmp_path / "demo.halo"
    created = create_bundle(root, "demo")

    opened = open_bundle(root)

    assert opened.id == created.id
    assert opened.name == created.name
    assert opened.bundle_path == created.bundle_path


def test_open_bundle_rejects_a_directory_without_project_json(tmp_path: Path) -> None:
    root = tmp_path / "not-a-bundle"
    root.mkdir()

    with pytest.raises(BundleError):
        open_bundle(root)


def test_open_bundle_is_idempotent_across_migrations(tmp_path: Path) -> None:
    root = tmp_path / "demo.halo"
    create_bundle(root, "demo")

    # Opening twice must not fail or duplicate the project row (Alembic
    # upgrade to an already-current head is a no-op).
    first = open_bundle(root)
    second = open_bundle(root)
    assert first.id == second.id

    with second.session_factory() as session:
        from sqlalchemy import func, select

        from halo_engine.db.models import ProjectRow

        count = session.scalar(select(func.count()).select_from(ProjectRow))
        assert count == 1
