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

R1 adds the revision-comparison family (``docs/contracts/r1.md`` §3, migration
``0003_compare_records``): ``compare_set`` -> ``sheet_frame`` -> ``sheet_pair``
-> ``change``/``cluster``, plus ``run`` for one export. Those rows hang off the
existing file family: a ``compare_set`` points at two ``drawing_set`` rows (one
per ``role``) and every frame names the ``drawing_file`` it was read from. The
JSON columns hold what is a list or a mapping in the contract (``bbox``,
``entity_handles``, ``provenance``, ``cloud``, ``badge``, ...); the shapes are
the ones ``packages/schema/src/compare/*.schema.json`` defines, and the sidecar
writer validates against those schemas rather than the ORM.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
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

    #: W3-06: extra XREF-resolution search directories, persisted so a
    #: dialog-driven folder pick (brief Goal) survives past the one import
    #: request that triggered it. ``PUT /projects/{id}/search-paths``.
    search_paths: Mapped[list[str]] = mapped_column(JSON, default=list)
    #: W3-06 addendum 3 / G1 답변: ``import.ignore_patterns``, default
    #: ``["*_recover.dwg", "*.bak"]`` (set at project creation, see
    #: ``bundle/create.py``) -- files matching these are excluded from
    #: import instead of being copied in.
    ignore_patterns: Mapped[list[str]] = mapped_column(JSON, default=list)

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

    #: R1: which side of a revision this set is, ``before`` or ``after``
    #: (``docs/contracts/r1.md`` §3). ``None`` for the plain W3 import path,
    #: which has no notion of sides.
    role: Mapped[str | None] = mapped_column(String(8), default=None)
    #: R1: the folder the user picked for this side. Read-only for the whole
    #: app (CLAUDE.md rule 1); kept so a re-open can show it without the job.
    source_dir: Mapped[str | None] = mapped_column(Text, default=None)

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
    #: W3-06 addendum 1: set when this row is a recursively-converted XREF
    #: target rather than a file the user picked directly (brief: "변환된
    #: XREF는 drawing_file(is_xref=1)로 등록").
    is_xref: Mapped[bool] = mapped_column(default=False)
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

    #: R1 (``docs/contracts/r1.md`` §3): what the ZWCAD conversion reported --
    #: ``{zwcad_version, elapsed_s, warnings[]}``. Null for a file converted by
    #: any other path.
    converter_meta: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    #: R1: set instead of converting when the file matched
    #: ``compare.yaml`` ``ingest.ignore_patterns``. The row is kept so the set
    #: summary can say how many files were skipped and why.
    excluded_reason: Mapped[str | None] = mapped_column(String(64), default=None)
    #: R1: font names read from the DXF STYLE table. Collected per set into
    #: ``CompareSetSummary.fonts_missing`` so the user learns before exporting
    #: that the markup DWG will not look like the original.
    font_names: Mapped[list[str] | None] = mapped_column(JSON, default=None)

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


class CompareSetRow(Base):
    """One before/after pair of drawing sets and how far its pipeline has got.

    Status walks ``ingesting`` -> ``ingested`` -> ``extracting`` -> ``matched``
    -> ``comparing`` -> ``compared`` (and ``exporting`` back to ``compared``),
    with ``failed`` as the one terminal error state
    (``docs/contracts/r1.md`` §3).

    ``run_date`` is a string, not a date: it is an explicit input the renderer
    supplies, it is written verbatim into the layer name and the revision table,
    and the engine must never derive it from the clock (§11).
    """

    __tablename__ = "compare_set"

    id: Mapped[str] = _id_column()
    project_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("project.id"))
    before_set_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("drawing_set.id"))
    after_set_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("drawing_set.id"))
    run_date: Mapped[str] = mapped_column(String(10), doc="`YYYY-MM-DD`, an explicit input.")
    status: Mapped[str] = mapped_column(String(16), doc="CompareSetStatus.")
    options: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, doc="Per-run overrides from POST /compare/sets."
    )
    stats: Mapped[dict[str, Any] | None] = mapped_column(
        JSON, default=None, doc="Counters the summary endpoint serves (files, fonts, crosscheck)."
    )
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class SheetFrameRow(Base):
    """One title block = one sheet, or a whole file that produced none.

    ``kind = "unrecognized_file"`` still gets a row: dropping the file would
    hide it from the sheet list, and the user has to be able to see that it was
    not understood (``docs/contracts/r1.md`` §3).
    """

    __tablename__ = "sheet_frame"

    id: Mapped[str] = _id_column()
    compare_set_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("compare_set.id"))
    role: Mapped[str] = mapped_column(String(8), doc="before | after.")
    file_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("drawing_file.id"))
    kind: Mapped[str] = mapped_column(String(24), doc="titleblock | unrecognized_file.")
    titleblock_handle: Mapped[str | None] = mapped_column(String(32), default=None)
    block_name: Mapped[str | None] = mapped_column(String(255), default=None)
    bbox: Mapped[list[float]] = mapped_column(JSON, default=list, doc="[x0, y0, x1, y1] in mm.")
    sheet_no: Mapped[str | None] = mapped_column(Text, default=None)
    sheet_title: Mapped[str | None] = mapped_column(Text, default=None)
    scale_text: Mapped[str | None] = mapped_column(String(64), default=None)
    scale_denominator: Mapped[int | None] = mapped_column(Integer, default=None)
    date_text: Mapped[str | None] = mapped_column(String(64), default=None)
    norm_key: Mapped[str] = mapped_column(
        Text, default="", doc="Normalised sheet_no, for matching."
    )
    sort_index: Mapped[int] = mapped_column(Integer, default=0)
    entity_handles: Mapped[list[str]] = mapped_column(
        JSON, default=list, doc="Working-DXF handles assigned to this frame, in document order."
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    attributes: Mapped[dict[str, str]] = mapped_column(
        JSON, default=dict, doc="Every title-block ATTRIB, tag -> value, as read."
    )


class SheetPairRow(Base):
    """One before frame matched to one after frame; either side may be null."""

    __tablename__ = "sheet_pair"

    id: Mapped[str] = _id_column()
    compare_set_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("compare_set.id"))
    before_frame_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN), ForeignKey("sheet_frame.id"), default=None
    )
    after_frame_id: Mapped[str | None] = mapped_column(
        String(_ID_LEN), ForeignKey("sheet_frame.id"), default=None
    )
    status: Mapped[str] = mapped_column(String(24), doc="PairStatus.")
    match_method: Mapped[str | None] = mapped_column(
        String(16), default=None, doc="number | title | position | manual."
    )
    score: Mapped[float | None] = mapped_column(Float, default=None)
    sort_key: Mapped[str] = mapped_column(Text, default="")
    change_count: Mapped[int] = mapped_column(Integer, default=0)
    minor_count: Mapped[int] = mapped_column(Integer, default=0)
    cluster_count: Mapped[int] = mapped_column(Integer, default=0)
    compare_dxf_path: Mapped[str | None] = mapped_column(Text, default=None)
    clusters_json_path: Mapped[str | None] = mapped_column(Text, default=None)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ChangeRow(Base):
    """One entity-level difference inside a pair.

    ``seq`` is the deterministic order the comparison produced; the sidecar's
    ``ch<seq>`` id is derived from it, so the file never carries a ULID.
    """

    __tablename__ = "change"

    id: Mapped[str] = _id_column()
    pair_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("sheet_pair.id"))
    seq: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16), doc="ChangeKind.")
    etype: Mapped[str] = mapped_column(String(32))
    layer: Mapped[str] = mapped_column(String(255))
    before_handle: Mapped[str | None] = mapped_column(String(32), default=None)
    after_handle: Mapped[str | None] = mapped_column(String(32), default=None)
    bbox: Mapped[list[float]] = mapped_column(JSON, default=list)
    delta: Mapped[dict[str, Any] | None] = mapped_column(JSON, default=None)
    minor: Mapped[bool] = mapped_column(Boolean, default=False)
    minor_reason: Mapped[str | None] = mapped_column(
        String(64), default=None, doc="Fold reasons joined with `+`."
    )
    provenance: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, doc="{before?, after?} (CLAUDE.md rule 5)."
    )


class ClusterRow(Base):
    """A group of changes drawn as one numbered cloud mark.

    ``signature`` is what survives a re-comparison: the same set of underlying
    changes hashes to the same value, so ``repos.replace_clusters`` can carry
    ``decision``/``user_label``/``note`` over to the freshly computed cluster
    (``docs/contracts/compare-dxf.md`` §7).
    """

    __tablename__ = "cluster"

    id: Mapped[str] = _id_column()
    pair_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("sheet_pair.id"))
    number: Mapped[int] = mapped_column(Integer, doc="1-based cloud-mark number.")
    signature: Mapped[str] = mapped_column(String(64))
    bbox: Mapped[list[float]] = mapped_column(JSON, default=list)
    kind: Mapped[str] = mapped_column(String(16), doc="ClusterKind.")
    label: Mapped[str] = mapped_column(Text, default="", doc="Automatic Korean label.")
    user_label: Mapped[str | None] = mapped_column(Text, default=None)
    decision: Mapped[str] = mapped_column(
        String(16), default="pending", doc="pending | approved | ignored."
    )
    note: Mapped[str | None] = mapped_column(Text, default=None)
    change_seqs: Mapped[list[int]] = mapped_column(
        JSON, default=list, doc="Member `change.seq` values; the sidecar writes them as `ch<seq>`."
    )
    cloud: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    badge: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class RunRow(Base):
    """One export: the markup drawings, the change list and ``run.json``."""

    __tablename__ = "run"

    id: Mapped[str] = _id_column()
    compare_set_id: Mapped[str] = mapped_column(String(_ID_LEN), ForeignKey("compare_set.id"))
    run_date: Mapped[str] = mapped_column(String(10))
    layer_name: Mapped[str] = mapped_column(String(32), doc="REV-<YYYYMMDD>[-n].")
    output_dir: Mapped[str] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(16), default="all")
    method: Mapped[str] = mapped_column(String(16), doc="auto | zwcad | acad-ts | dxf-only.")
    pair_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    approved_count: Mapped[int] = mapped_column(Integer, default=0)
    ignored_count: Mapped[int] = mapped_column(Integer, default=0)
    files: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, doc="{pair_id, sheet_no, path, format, writer} per written drawing."
    )
    status: Mapped[str] = mapped_column(String(16), default="running")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime)


__all__ = [
    "ChangeRow",
    "ClusterRow",
    "CompareSetRow",
    "DrawingFileRow",
    "DrawingSetRow",
    "EntityIndexRow",
    "ProjectRow",
    "RunRow",
    "SheetFrameRow",
    "SheetPairRow",
    "XrefLinkRow",
]
