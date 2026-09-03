"""Run this package's Alembic migrations against one bundle's ``project.sqlite``.

Called once per bundle open (``bundle.create.create_bundle`` /
``bundle.create.open_bundle``), not once per process -- every project bundle
carries its own SQLite file and its own migration state (``alembic_version``
table inside it).
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_SCRIPT_LOCATION = Path(__file__).with_name("alembic")


def _config_for(sqlite_path: Path) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(_SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{sqlite_path}")
    return cfg


def upgrade_to_head(sqlite_path: Path) -> None:
    """Create ``sqlite_path`` (if new) and bring it to the latest schema revision."""
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    command.upgrade(_config_for(sqlite_path), "head")


__all__ = ["upgrade_to_head"]
