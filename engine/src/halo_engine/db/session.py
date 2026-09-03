"""Per-bundle SQLite engine/session factory.

One :class:`~sqlalchemy.Engine` per open project bundle (``<name>.halo/project.sqlite``,
``docs/PLAN.md`` §4). SQLite's default is to reject foreign keys unless
``PRAGMA foreign_keys=ON`` is issued on every connection, so that is wired
through a ``connect`` event listener rather than left to chance.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def make_engine(sqlite_path: Path) -> Engine:
    """A SQLite engine over ``sqlite_path`` with foreign keys enforced."""
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{sqlite_path}", future=True)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
        if isinstance(dbapi_connection, sqlite3.Connection):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


__all__ = ["make_engine", "make_session_factory"]
