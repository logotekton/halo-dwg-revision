"""R1: the revision-comparison family plus the columns it needs on the file tables.

Revision ID: 0003_compare_records
Revises: 0002
Create Date: 2026-09-04

Adds ``compare_set``, ``sheet_frame``, ``sheet_pair``, ``change``, ``cluster``
and ``run`` (``docs/contracts/r1.md`` §3), and the three sets of columns the
comparison needs on the existing file tables: which side a ``drawing_set`` is
and where it came from, and per ``drawing_file`` what the converter reported,
why it was excluded, and which fonts it references.

Every statement is guarded by an existence check, for the same reason
``0002_xref_settings.py`` guards its own: ``0001_initial.py`` builds its tables
from *live* ``Base.metadata`` rather than a frozen snapshot, so a bundle created
after this task's ``db/models.py`` landed already has all six tables and all
five columns from revision 0001 alone. Only a bundle created before it -- one
sitting at 0002 under the old models -- actually needs the work. Both have to
end up at the same schema, and running this revision on either must succeed.

The column list is spelled out here instead of being read from
``db.models``: a migration has to keep describing the schema *as of this
revision* even after the models move on.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_compare_records"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ID = sa.String(26)


def _added_columns() -> list[tuple[str, sa.Column[object]]]:
    """Columns added to tables that already exist, as ``(table, Column)``.

    Built fresh on every call: ``op.add_column`` binds the ``Column`` to a
    ``Table``, and one test process opens several bundles, so a module-level
    list would hand the second migration an already-attached object.
    """
    return [
        ("drawing_set", sa.Column("role", sa.String(8), nullable=True)),
        ("drawing_set", sa.Column("source_dir", sa.Text(), nullable=True)),
        ("drawing_file", sa.Column("converter_meta", sa.JSON(), nullable=True)),
        ("drawing_file", sa.Column("excluded_reason", sa.String(64), nullable=True)),
        ("drawing_file", sa.Column("font_names", sa.JSON(), nullable=True)),
    ]


#: Tables created by this revision, newest dependency last so a drop in reverse
#: order never trips a foreign key.
_NEW_TABLES = ["compare_set", "sheet_frame", "sheet_pair", "change", "cluster", "run"]


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _column_names(table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    existing_tables = _table_names()

    for table, column in _added_columns():
        if column.name not in _column_names(table):
            op.add_column(table, column)

    if "compare_set" not in existing_tables:
        op.create_table(
            "compare_set",
            sa.Column("id", _ID, primary_key=True),
            sa.Column("project_id", _ID, sa.ForeignKey("project.id"), nullable=False),
            sa.Column("before_set_id", _ID, sa.ForeignKey("drawing_set.id"), nullable=False),
            sa.Column("after_set_id", _ID, sa.ForeignKey("drawing_set.id"), nullable=False),
            sa.Column("run_date", sa.String(10), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("options", sa.JSON(), nullable=False),
            sa.Column("stats", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if "sheet_frame" not in existing_tables:
        op.create_table(
            "sheet_frame",
            sa.Column("id", _ID, primary_key=True),
            sa.Column("compare_set_id", _ID, sa.ForeignKey("compare_set.id"), nullable=False),
            sa.Column("role", sa.String(8), nullable=False),
            sa.Column("file_id", _ID, sa.ForeignKey("drawing_file.id"), nullable=False),
            sa.Column("kind", sa.String(24), nullable=False),
            sa.Column("titleblock_handle", sa.String(32), nullable=True),
            sa.Column("block_name", sa.String(255), nullable=True),
            sa.Column("bbox", sa.JSON(), nullable=False),
            sa.Column("sheet_no", sa.Text(), nullable=True),
            sa.Column("sheet_title", sa.Text(), nullable=True),
            sa.Column("scale_text", sa.String(64), nullable=True),
            sa.Column("scale_denominator", sa.Integer(), nullable=True),
            sa.Column("date_text", sa.String(64), nullable=True),
            sa.Column("norm_key", sa.Text(), nullable=False),
            sa.Column("sort_index", sa.Integer(), nullable=False),
            sa.Column("entity_handles", sa.JSON(), nullable=False),
            sa.Column("provenance", sa.JSON(), nullable=False),
            sa.Column("attributes", sa.JSON(), nullable=False),
        )

    if "sheet_pair" not in existing_tables:
        op.create_table(
            "sheet_pair",
            sa.Column("id", _ID, primary_key=True),
            sa.Column("compare_set_id", _ID, sa.ForeignKey("compare_set.id"), nullable=False),
            sa.Column("before_frame_id", _ID, sa.ForeignKey("sheet_frame.id"), nullable=True),
            sa.Column("after_frame_id", _ID, sa.ForeignKey("sheet_frame.id"), nullable=True),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("match_method", sa.String(16), nullable=True),
            sa.Column("score", sa.Float(), nullable=True),
            sa.Column("sort_key", sa.Text(), nullable=False),
            sa.Column("change_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("minor_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("cluster_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("compare_dxf_path", sa.Text(), nullable=True),
            sa.Column("clusters_json_path", sa.Text(), nullable=True),
            sa.Column("warnings", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if "change" not in existing_tables:
        op.create_table(
            "change",
            sa.Column("id", _ID, primary_key=True),
            sa.Column("pair_id", _ID, sa.ForeignKey("sheet_pair.id"), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("etype", sa.String(32), nullable=False),
            sa.Column("layer", sa.String(255), nullable=False),
            sa.Column("before_handle", sa.String(32), nullable=True),
            sa.Column("after_handle", sa.String(32), nullable=True),
            sa.Column("bbox", sa.JSON(), nullable=False),
            sa.Column("delta", sa.JSON(), nullable=True),
            sa.Column("minor", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("minor_reason", sa.String(64), nullable=True),
            sa.Column("provenance", sa.JSON(), nullable=False),
        )

    if "cluster" not in existing_tables:
        op.create_table(
            "cluster",
            sa.Column("id", _ID, primary_key=True),
            sa.Column("pair_id", _ID, sa.ForeignKey("sheet_pair.id"), nullable=False),
            sa.Column("number", sa.Integer(), nullable=False),
            sa.Column("signature", sa.String(64), nullable=False),
            sa.Column("bbox", sa.JSON(), nullable=False),
            sa.Column("kind", sa.String(16), nullable=False),
            sa.Column("label", sa.Text(), nullable=False),
            sa.Column("user_label", sa.Text(), nullable=True),
            sa.Column("decision", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("change_seqs", sa.JSON(), nullable=False),
            sa.Column("cloud", sa.JSON(), nullable=False),
            sa.Column("badge", sa.JSON(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    if "run" not in existing_tables:
        op.create_table(
            "run",
            sa.Column("id", _ID, primary_key=True),
            sa.Column("compare_set_id", _ID, sa.ForeignKey("compare_set.id"), nullable=False),
            sa.Column("run_date", sa.String(10), nullable=False),
            sa.Column("layer_name", sa.String(32), nullable=False),
            sa.Column("output_dir", sa.Text(), nullable=False),
            sa.Column("scope", sa.String(16), nullable=False, server_default="all"),
            sa.Column("method", sa.String(16), nullable=False),
            sa.Column("pair_ids", sa.JSON(), nullable=False),
            sa.Column("approved_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("ignored_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("files", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="running"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )


def downgrade() -> None:
    existing_tables = _table_names()
    for table in reversed(_NEW_TABLES):
        if table in existing_tables:
            op.drop_table(table)

    for table, column in reversed(_added_columns()):
        if column.name in _column_names(table):
            op.drop_column(table, column.name)
