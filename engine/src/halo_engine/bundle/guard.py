"""Write-path guard for the original-drawing-immutability rule (``CLAUDE.md`` rule 1).

"원본 도면은 불변... 원본 경로 쓰기는 코드 가드가 거부해야 한다." This is that
guard: every place in the ingest pipeline that is about to open a path in a
write mode calls :func:`assert_writable_path` first, naming the roots that
*are* allowed (typically just a bundle's ``originals/`` directory for the
one-time copy-in). A user-provided source path is never among them.
"""

from __future__ import annotations

from pathlib import Path


class OriginalWriteGuardError(PermissionError):
    """Raised when code would open a write-mode handle outside every allowed root."""


def assert_writable_path(path: Path, *, allowed_roots: list[Path]) -> None:
    """Raise :class:`OriginalWriteGuardError` unless ``path`` resolves under an allowed root."""
    resolved = path.resolve()
    for root in allowed_roots:
        resolved_root = root.resolve()
        if resolved == resolved_root or resolved_root in resolved.parents:
            return
    roots_text = ", ".join(str(r) for r in allowed_roots) or "(none)"
    raise OriginalWriteGuardError(
        f"refusing to write to {path} -- outside every allowed root ({roots_text}); "
        "original drawings are immutable (CLAUDE.md rule 1)"
    )


__all__ = ["OriginalWriteGuardError", "assert_writable_path"]
