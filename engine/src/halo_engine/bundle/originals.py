"""Copy a user's original drawing into ``originals/<sha256><ext>`` (0444, never written again).

The source file is only ever opened ``"rb"``. ``guard.assert_writable_path``
runs right before the one write this module performs, naming
``originals_dir`` as the only allowed root -- the concrete "code guard
refuses" CLAUDE.md rule 1 asks for.
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

from halo_engine.bundle.guard import assert_writable_path
from halo_engine.bundle.layout import BundleLayout

_CHUNK_SIZE = 1 << 20
_READ_ONLY_MODE = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH  # 0444


@dataclass(frozen=True)
class OriginalCopyResult:
    sha256: str
    dest_path: Path
    already_present: bool


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def copy_original(source_path: Path, layout: BundleLayout) -> OriginalCopyResult:
    """Copy ``source_path`` into ``layout.originals_dir`` as ``<sha256><ext>``, then chmod 0444.

    Idempotent: re-importing the same bytes reuses the existing read-only
    copy instead of writing again. Raises :class:`FileNotFoundError` if
    ``source_path`` does not exist, and never opens it in a write mode.
    """
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    sha256 = sha256_file(source_path)
    dest_path = layout.originals_dir / f"{sha256}{source_path.suffix.lower()}"

    if dest_path.exists():
        return OriginalCopyResult(sha256=sha256, dest_path=dest_path, already_present=True)

    layout.originals_dir.mkdir(parents=True, exist_ok=True)
    assert_writable_path(dest_path, allowed_roots=[layout.originals_dir])

    tmp_path = dest_path.with_name(dest_path.name + ".tmp")
    with source_path.open("rb") as src, tmp_path.open("wb") as dst:
        for chunk in iter(lambda: src.read(_CHUNK_SIZE), b""):
            dst.write(chunk)
    os.replace(tmp_path, dest_path)
    os.chmod(dest_path, _READ_ONLY_MODE)

    return OriginalCopyResult(sha256=sha256, dest_path=dest_path, already_present=False)


__all__ = ["OriginalCopyResult", "copy_original", "sha256_file"]
