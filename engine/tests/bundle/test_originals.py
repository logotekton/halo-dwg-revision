"""``bundle/originals.py`` -- the source file is read-only, the bundle's copy becomes 0444.

CLAUDE.md rule 1: "원본 도면은 불변... 원본 경로 쓰기는 코드 가드가 거부해야 한다."
"""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

from halo_engine.bundle.layout import BundleLayout
from halo_engine.bundle.originals import copy_original, sha256_file


def _make_source(tmp_path: Path, name: str = "source.dxf", content: bytes = b"hello dxf") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_copy_original_writes_a_read_only_hash_named_copy(tmp_path: Path) -> None:
    layout = BundleLayout(tmp_path / "b.halo")
    layout.ensure_dirs()
    src = _make_source(tmp_path)

    result = copy_original(src, layout)

    assert result.sha256 == hashlib.sha256(src.read_bytes()).hexdigest()
    assert result.dest_path == layout.originals_dir / f"{result.sha256}.dxf"
    assert result.dest_path.read_bytes() == src.read_bytes()
    assert result.already_present is False

    mode = result.dest_path.stat().st_mode
    assert stat.S_IMODE(mode) == 0o444


def test_original_source_file_is_never_modified(tmp_path: Path) -> None:
    layout = BundleLayout(tmp_path / "b.halo")
    layout.ensure_dirs()
    src = _make_source(tmp_path)

    before_bytes = src.read_bytes()
    before_mtime = src.stat().st_mtime_ns
    before_mode = src.stat().st_mode

    copy_original(src, layout)

    assert src.read_bytes() == before_bytes
    assert src.stat().st_mtime_ns == before_mtime
    assert src.stat().st_mode == before_mode
    # still writable -- copy_original never touched the source's own permissions.
    assert before_mode & stat.S_IWUSR


def test_reimporting_the_same_bytes_is_idempotent_and_does_not_rewrite(tmp_path: Path) -> None:
    layout = BundleLayout(tmp_path / "b.halo")
    layout.ensure_dirs()
    src = _make_source(tmp_path)

    first = copy_original(src, layout)
    dest_mtime_after_first = first.dest_path.stat().st_mtime_ns

    second = copy_original(src, layout)

    assert second.dest_path == first.dest_path
    assert second.already_present is True
    assert second.dest_path.stat().st_mtime_ns == dest_mtime_after_first


def test_sha256_file_matches_hashlib(tmp_path: Path) -> None:
    src = _make_source(tmp_path, content=b"some bytes to hash")
    assert sha256_file(src) == hashlib.sha256(b"some bytes to hash").hexdigest()


def test_missing_source_raises_file_not_found(tmp_path: Path) -> None:
    layout = BundleLayout(tmp_path / "b.halo")
    layout.ensure_dirs()

    import pytest

    with pytest.raises(FileNotFoundError):
        copy_original(tmp_path / "nope.dxf", layout)
