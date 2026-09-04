"""W3-06: project XREF-resolution settings and the ``is_xref`` DWG-target flag.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-03

Adds ``project.search_paths``/``project.ignore_patterns`` (brief Goal /
addendum 3: ``PUT /projects/{id}/search-paths``, ``import.ignore_patterns``)
and ``drawing_file.is_xref`` (addendum 1: "변환된 XREF는 drawing_file(is_xref=1)로
등록"). Unlike ``0001_initial.py`` (a from-scratch ``create_all``), this is a
real ``ALTER TABLE`` against a bundle that may already have data in it, so
it uses ``op`` calls with an explicit server default rather than relying on
``Base.metadata`` reflecting the current models.

Every ``add_column`` here is guarded by an existence check: because
``0001_initial.py`` builds its tables from *live* ``Base.metadata``
(module docstring) rather than a frozen historical snapshot, a bundle
created after this task's ``db/models.py`` changes lands already has these
three columns from ``0001`` alone -- only a bundle created *before* this
task (already at revision 0001 under the old model) is actually missing
them when this revision runs. Both must end up at the same schema.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Same default as halo_engine.ingest.xref.DEFAULT_IGNORE_PATTERNS, duplicated
#: (not imported) because a migration must stay correct even if that
#: module's default changes later -- see Alembic's own guidance against
#: importing application code into migrations.
_DEFAULT_IGNORE_PATTERNS_JSON = '["*_recover.dwg", "*.bak"]'


def _add_column_if_missing(table: str, column: sa.Column[object]) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {c["name"] for c in inspector.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def upgrade() -> None:
    _add_column_if_missing(
        "project", sa.Column("search_paths", sa.JSON(), nullable=False, server_default="[]")
    )
    _add_column_if_missing(
        "project",
        sa.Column(
            "ignore_patterns",
            sa.JSON(),
            nullable=False,
            server_default=_DEFAULT_IGNORE_PATTERNS_JSON,
        ),
    )
    _add_column_if_missing(
        "drawing_file",
        sa.Column("is_xref", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("drawing_file", "is_xref")
    op.drop_column("project", "ignore_patterns")
    op.drop_column("project", "search_paths")
