"""``db/ids.py`` and ``db/repos.py`` -- exercised directly against a bundle's own DB.

Lives under ``tests/bundle`` (not a ``tests/db``) because the brief's owned
test globs are ``tests/{bundle,api}/**`` and a bundle is what stands the DB
up in the first place (``bundle.create.create_bundle`` runs the migration).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from halo_engine.bundle.create import create_bundle
from halo_engine.db import repos
from halo_engine.db.ids import new_ulid

_ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def test_new_ulid_shape_and_uniqueness() -> None:
    ids = {new_ulid() for _ in range(1000)}
    assert len(ids) == 1000
    for value in ids:
        assert _ULID_RE.match(value), value


def test_new_ulid_is_lexically_sortable_by_time() -> None:
    early = new_ulid(_now_ms=1_000_000, _random_bytes=b"\x00" * 10)
    late = new_ulid(_now_ms=2_000_000, _random_bytes=b"\x00" * 10)
    assert early < late


def test_new_ulid_rejects_wrong_length_randomness() -> None:
    with pytest.raises(ValueError):
        new_ulid(_random_bytes=b"\x00")


def _bundle(tmp_path: Path) -> Path:
    root = tmp_path / "demo.halo"
    create_bundle(root, "demo")
    return root


def test_drawing_set_and_file_crud(tmp_path: Path) -> None:
    from halo_engine.bundle.create import open_bundle

    handle = open_bundle(_bundle(tmp_path))

    with handle.session_factory() as session:
        drawing_set = repos.create_drawing_set(session, project_id=handle.id)
        assert drawing_set.project_id == handle.id

        file_row = repos.create_drawing_file(
            session,
            drawing_set_id=drawing_set.id,
            original_path="/abs/path/plan.dxf",
            original_name="plan.dxf",
            sha256="a" * 64,
            format="DXF",
            import_status="PENDING",
        )
        assert file_row.import_status == "PENDING"

        updated = repos.update_drawing_file(
            session, file_row.id, import_status="DONE", entity_count=42
        )
        assert updated.import_status == "DONE"
        assert updated.entity_count == 42

        files = repos.list_files_for_set(session, drawing_set.id)
        assert [f.id for f in files] == [file_row.id]

        fetched = repos.get_drawing_file(session, file_row.id)
        assert fetched is not None
        assert fetched.entity_count == 42

        assert repos.get_drawing_file(session, "nonexistent") is None
        assert repos.get_drawing_set(session, "nonexistent") is None


def test_update_drawing_file_unknown_id_raises_key_error(tmp_path: Path) -> None:
    from halo_engine.bundle.create import open_bundle

    handle = open_bundle(_bundle(tmp_path))
    with handle.session_factory() as session:
        with pytest.raises(KeyError):
            repos.update_drawing_file(session, "nonexistent", import_status="DONE")


def test_xref_link_crud(tmp_path: Path) -> None:
    from halo_engine.bundle.create import open_bundle

    handle = open_bundle(_bundle(tmp_path))
    with handle.session_factory() as session:
        drawing_set = repos.create_drawing_set(session, project_id=handle.id)
        file_row = repos.create_drawing_file(
            session,
            drawing_set_id=drawing_set.id,
            original_path="/abs/host.dxf",
            original_name="host.dxf",
            sha256="b" * 64,
            format="DXF",
            import_status="DONE",
        )

        link = repos.add_xref_link(
            session,
            host_file_id=file_row.id,
            block_name="GRID",
            declared_path="grid.dxf",
            resolved_path="/abs/grid.dxf",
            status="RESOLVED",
        )
        assert link.host_file_id == file_row.id
        assert link.status == "RESOLVED"
