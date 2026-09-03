"""``bundle/guard.py`` -- the concrete "code guard refuses" CLAUDE.md rule 1 asks for."""

from __future__ import annotations

from pathlib import Path

import pytest

from halo_engine.bundle.guard import OriginalWriteGuardError, assert_writable_path


def test_allows_a_path_under_an_allowed_root(tmp_path: Path) -> None:
    root = tmp_path / "originals"
    root.mkdir()
    assert_writable_path(root / "abc123.dxf", allowed_roots=[root])  # must not raise


def test_allows_the_root_itself(tmp_path: Path) -> None:
    root = tmp_path / "originals"
    root.mkdir()
    assert_writable_path(root, allowed_roots=[root])


def test_refuses_a_path_outside_every_allowed_root(tmp_path: Path) -> None:
    root = tmp_path / "originals"
    root.mkdir()
    outside = tmp_path / "user-drawings" / "plan.dwg"

    with pytest.raises(OriginalWriteGuardError):
        assert_writable_path(outside, allowed_roots=[root])


def test_refuses_a_sibling_directory_that_merely_shares_a_prefix(tmp_path: Path) -> None:
    """`originals-backup/` must not be treated as inside `originals/` by string prefix alone."""
    root = tmp_path / "originals"
    root.mkdir()
    sneaky = tmp_path / "originals-backup" / "x.dxf"

    with pytest.raises(OriginalWriteGuardError):
        assert_writable_path(sneaky, allowed_roots=[root])


def test_refuses_with_no_allowed_roots_at_all(tmp_path: Path) -> None:
    with pytest.raises(OriginalWriteGuardError):
        assert_writable_path(tmp_path / "anything.dxf", allowed_roots=[])
