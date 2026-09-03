"""Create or open a ``<name>.halo`` project bundle (``docs/PLAN.md`` §4).

Exactly one bundle is open in the engine's workspace at a time (brief
W3-03 Decisions -- mirrors the renderer's single-project ``workspace``
Zustand store, W3-01): :class:`BundleHandle` is what ``api/routers/projects.py``
stores on ``app.state`` once opened.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker

from halo_engine.bundle.layout import BundleLayout, default_bundle_path
from halo_engine.db import repos
from halo_engine.db.migrate import upgrade_to_head
from halo_engine.db.models import ProjectRow
from halo_engine.db.session import make_engine, make_session_factory

_PROJECT_JSON_SCHEMA_VERSION = "0.1"


class BundleError(Exception):
    """A bundle create/open operation could not proceed."""


@dataclass
class BundleHandle:
    """An open bundle: its identity, paths, and a ready-to-use DB session factory."""

    id: str
    name: str
    layout: BundleLayout
    engine: Engine
    session_factory: sessionmaker[Session]

    @property
    def bundle_path(self) -> Path:
        return self.layout.root


def _write_project_json(
    layout: BundleLayout, *, project_id: str, name: str, created_at: datetime
) -> None:
    layout.project_json.write_text(
        json.dumps(
            {
                "schema_version": _PROJECT_JSON_SCHEMA_VERSION,
                "id": project_id,
                "name": name,
                "created_at": created_at.isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def create_bundle(path: Path | None, name: str) -> BundleHandle:
    """Create a new bundle at ``path`` (``default_bundle_path(name)`` if omitted) and open it."""
    root = path if path is not None else default_bundle_path(name)
    if root.exists() and any(root.iterdir()):
        raise BundleError(f"{root} already exists and is not empty")

    layout = BundleLayout(root)
    layout.ensure_dirs()
    upgrade_to_head(layout.project_sqlite)

    engine = make_engine(layout.project_sqlite)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        row = repos.create_project(session, name=name, bundle_path=str(root))
    _write_project_json(layout, project_id=row.id, name=name, created_at=row.created_at)

    return BundleHandle(
        id=row.id, name=name, layout=layout, engine=engine, session_factory=session_factory
    )


def open_bundle(path: Path) -> BundleHandle:
    """Open an existing bundle at ``path``, migrating its ``project.sqlite`` to head first."""
    layout = BundleLayout(path)
    if not layout.project_json.is_file():
        raise BundleError(f"{path} is not a Halo CAD bundle (missing project.json)")

    layout.ensure_dirs()
    upgrade_to_head(layout.project_sqlite)

    engine = make_engine(layout.project_sqlite)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        row = session.scalars(select(ProjectRow)).first()
        if row is None:
            # A bundle whose project.sqlite was migrated but never got its
            # project row (shouldn't happen via create_bundle, but keeps
            # open_bundle robust for a hand-assembled/older bundle).
            meta = json.loads(layout.project_json.read_text(encoding="utf-8"))
            row = repos.create_project(session, name=str(meta["name"]), bundle_path=str(path))

    return BundleHandle(
        id=row.id, name=row.name, layout=layout, engine=engine, session_factory=session_factory
    )


__all__ = ["BundleError", "BundleHandle", "create_bundle", "open_bundle"]
