"""SQLAlchemy 2 ORM models for the file-family tables (``docs/PLAN.md`` §4).

Scope for W3-03 is the "파일 계열" tables only -- sheet/level/member tables are
P3 (``docs/briefs/W3-03.md`` Constraints). One physical SQLite database per
project bundle (``<name>.halo/project.sqlite``); columns avoid SQLite-only
types (``CLAUDE.md`` rule: "SQLite 전용 타입 회피(PostgreSQL 공용)") so the same
schema can later back the P2 server's PostgreSQL store.

``entity_index`` is defined here (so Alembic creates the table) but is not
populated by this task's ingest pipeline -- SQLite storage for it is W6-01
(``engine/README.md``: "entity_index.py(최상위 엔티티 레코드 생성기, SQLite
저장은 W6-01)").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from halo_engine.db.base import Base
from halo_engine.db.ids import new_ulid

_ID_LEN = 26


def _id_column() -> Mapped[str]:
    return mapped_column(String(_ID_LEN), primary_key=True, default=new_ulid)


class ProjectRow(Base):
    """A single row: the bundle this ``project.sqlite`` belongs to.

    Kept alongside ``project.json`` (human-readable, PLAN §4) rather than
    instead of it -- the DB row is what the API actually queries.
    """

    __tablename__ = "project"

    id: Mapped[str] = _id_column()
    name: Mapped[str] = mapped_column(String(255))
    bundle_path: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    drawing_sets: Mapped[list[DrawingSetRow]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class DrawingSetRow(Base):
    """One import batch -- "=DMS 리비전 단위" per PLAN §4 (DMS revision plumbing is P2)."""

    __tablename__ = "drawing_set"

    id: Mapped[str] = _id_column()
    project_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("project.id"))
    label: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime)

    project: Mapped[ProjectRow] = relationship(back_populates="drawing_sets")
    files: Mapped[list[DrawingFileRow]] = relationship(
        back_populates="drawing_set",
        cascade="all, delete-orphan",
        order_by="DrawingFileRow.created_at",
    )


class DrawingFileRow(Base):
    """One imported file and where its import pipeline (``ingest/pipeline.py``) left off."""

    __tablename__ = "drawing_file"

    id: Mapped[str] = _id_column()
    drawing_set_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("drawing_set.id"))

    original_path: Mapped[str] = mapped_column(Text, doc="Absolute source path, read-only.")
    original_name: Mapped[str] = mapped_column(String(255))
    sha256: Mapped[str] = mapped_column(String(64), doc="Of the original file's bytes.")
    format: Mapped[str] = mapped_column(String(8), doc="DrawingFormat: DWG | DXF.")
    dwg_version: Mapped[str | None] = mapped_column(String(16), default=None)
    fingerprint_guid: Mapped[str | None] = mapped_column(String(64), default=None)
    codepage_declared: Mapped[str | None] = mapped_column(String(32), default=None)
    codepage_effective: Mapped[str | None] = mapped_column(String(32), default=None)
    entity_count: Mapped[int | None] = mapped_column(Integer, default=None)

    import_status: Mapped[str] = mapped_column(String(32), doc="ImportStatus.")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)

    converter: Mapped[str | None] = mapped_column(
        String(32), default=None, doc='"mlightcad-dxfout" | "acad-ts", set only for DWG sources.'
    )
    original_originals_path: Mapped[str | None] = mapped_column(
        Text, default=None, doc="originals/<sha256><ext> inside the bundle (0444)."
    )
    working_dxf_path: Mapped[str | None] = mapped_column(Text, default=None)
    stats_json_path: Mapped[str | None] = mapped_column(
        Text, default=None, doc="LayerStatsDocument written by ingest/working_dxf.py."
    )
    parser_crosscheck: Mapped[dict[str, Any] | None] = mapped_column(
        JSON,
        default=None,
        doc="CrosscheckReport (ADR-0002 6); refreshed by POST /files/{id}/crosscheck.",
    )

    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    drawing_set: Mapped[DrawingSetRow] = relationship(back_populates="files")
    xref_links: Mapped[list[XrefLinkRow]] = relationship(
        back_populates="host_file", cascade="all, delete-orphan"
    )
    entities: Mapped[list[EntityIndexRow]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class XrefLinkRow(Base):
    """One XREF block definition found in a host file (full resolution UI is W3-06)."""

    __tablename__ = "xref_link"

    id: Mapped[str] = _id_column()
    host_file_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("drawing_file.id"))
    block_name: Mapped[str] = mapped_column(String(255))
    declared_path: Mapped[str] = mapped_column(Text)
    resolved_path: Mapped[str | None] = mapped_column(Text, default=None)
    status: Mapped[str] = mapped_column(String(16), doc="RESOLVED | UNRESOLVED.")

    host_file: Mapped[DrawingFileRow] = relationship(back_populates="xref_links")


class EntityIndexRow(Base):
    """Top-level entity record. Schema only in W3-03 -- population is W6-01 (module docstring)."""

    __tablename__ = "entity_index"

    id: Mapped[str] = _id_column()
    file_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("drawing_file.id"))
    handle: Mapped[str] = mapped_column(String(32))
    etype: Mapped[str] = mapped_column(String(32))
    layer: Mapped[str] = mapped_column(String(255))
    space: Mapped[str] = mapped_column(String(64))
    block_name: Mapped[str | None] = mapped_column(String(255), default=None)
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    length_mm: Mapped[float | None] = mapped_column(default=None)
    area_mm2: Mapped[float | None] = mapped_column(default=None)
    text: Mapped[str | None] = mapped_column(Text, default=None)
    fingerprint: Mapped[str | None] = mapped_column(String(64), default=None)

    file: Mapped[DrawingFileRow] = relationship(back_populates="entities")


__all__ = [
    "DrawingFileRow",
    "DrawingSetRow",
    "EntityIndexRow",
    "ProjectRow",
    "XrefLinkRow",
]
