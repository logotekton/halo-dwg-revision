"""Initial file-family schema: project, drawing_set, drawing_file, xref_link, entity_index.

Revision ID: 0001
Revises:
Create Date: 2026-09-03

Creates tables from ``halo_engine.db.models.Base.metadata`` directly
(``checkfirst=True``) rather than hand-duplicated ``op.create_table`` calls:
for a from-scratch initial migration this is equivalent and cannot drift
from the ORM models it mirrors. Later migrations should use ``op`` calls as
usual -- this shortcut is specific to "table doesn't exist yet".
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from halo_engine.db import models  # noqa: F401  (registers every table on Base.metadata)
from halo_engine.db.base import Base

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
