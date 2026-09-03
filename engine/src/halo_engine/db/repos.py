"""Thin repository functions over :mod:`halo_engine.db.models` (plain SQLAlchemy 2 Sessions).

Every function takes an already-open :class:`~sqlalchemy.orm.Session` and
commits its own unit of work -- callers (``api/routers/*.py``, ``api/jobs.py``)
never touch the ORM directly, only these functions and the pydantic view
models in :mod:`halo_engine.model`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from halo_engine.db.ids import new_ulid
from halo_engine.db.models import DrawingFileRow, DrawingSetRow, ProjectRow, XrefLinkRow


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def create_project(session: Session, *, name: str, bundle_path: str) -> ProjectRow:
    now = _now()
    row = ProjectRow(
        id=new_ulid(), name=name, bundle_path=bundle_path, created_at=now, updated_at=now
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_project(session: Session, project_id: str) -> ProjectRow | None:
    return session.get(ProjectRow, project_id)


def create_drawing_set(
    session: Session, *, project_id: str, label: str | None = None
) -> DrawingSetRow:
    row = DrawingSetRow(id=new_ulid(), project_id=project_id, label=label, created_at=_now())
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_drawing_set(session: Session, drawing_set_id: str) -> DrawingSetRow | None:
    return session.get(DrawingSetRow, drawing_set_id)


def create_drawing_file(
    session: Session,
    *,
    drawing_set_id: str,
    original_path: str,
    original_name: str,
    sha256: str,
    format: str,
    import_status: str,
) -> DrawingFileRow:
    now = _now()
    row = DrawingFileRow(
        id=new_ulid(),
        drawing_set_id=drawing_set_id,
        original_path=original_path,
        original_name=original_name,
        sha256=sha256,
        format=format,
        import_status=import_status,
        created_at=now,
        updated_at=now,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_drawing_file(session: Session, file_id: str) -> DrawingFileRow | None:
    return session.get(DrawingFileRow, file_id)


def list_files_for_set(session: Session, drawing_set_id: str) -> list[DrawingFileRow]:
    stmt = (
        select(DrawingFileRow)
        .where(DrawingFileRow.drawing_set_id == drawing_set_id)
        .order_by(DrawingFileRow.created_at)
    )
    return list(session.scalars(stmt))


def update_drawing_file(session: Session, file_id: str, **fields: Any) -> DrawingFileRow:
    row = session.get(DrawingFileRow, file_id)
    if row is None:
        raise KeyError(f"drawing_file {file_id!r} not found")
    for key, value in fields.items():
        setattr(row, key, value)
    row.updated_at = _now()
    session.commit()
    session.refresh(row)
    return row


def add_xref_link(
    session: Session,
    *,
    host_file_id: str,
    block_name: str,
    declared_path: str,
    resolved_path: str | None,
    status: str,
) -> XrefLinkRow:
    row = XrefLinkRow(
        id=new_ulid(),
        host_file_id=host_file_id,
        block_name=block_name,
        declared_path=declared_path,
        resolved_path=resolved_path,
        status=status,
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


__all__ = [
    "add_xref_link",
    "create_drawing_file",
    "create_drawing_set",
    "create_project",
    "get_drawing_file",
    "get_drawing_set",
    "get_project",
    "list_files_for_set",
    "update_drawing_file",
]
