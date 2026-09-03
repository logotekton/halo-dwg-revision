"""``POST /projects``, ``POST /projects/open``, ``GET /projects/recent``,
``GET /projects/{id}`` (``docs/contracts/wave-3.md``).

Exactly one bundle is open in the engine's workspace at a time (brief W3-03
Decisions, mirroring the renderer's single-project `workspace` Zustand
store, W3-01): the currently open :class:`~halo_engine.bundle.create.BundleHandle`
lives on ``app.state.bundle``, set by this router and read by every other one
via :func:`get_open_bundle`. "Recent projects" is a small JSON file under the
engine's own ``data_dir`` (``<data_dir>/recent-projects.json``) -- separate
from any one bundle, since the whole point is listing bundles that are not
currently open.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from halo_engine.bundle.create import BundleError, BundleHandle, create_bundle, open_bundle
from halo_engine.db import repos
from halo_engine.model.project import (
    ProjectCreateRequest,
    ProjectCreateResponse,
    ProjectOpenRequest,
    ProjectSummary,
    RecentProjectEntry,
)

logger = logging.getLogger("halo_engine.api.projects")

router = APIRouter()

_RECENTS_FILENAME = "recent-projects.json"


def get_open_bundle(request: Request) -> BundleHandle:
    """The currently open project, or a 409 -- every other router depends on this."""
    bundle = getattr(request.app.state, "bundle", None)
    if bundle is None:
        raise HTTPException(
            status_code=409, detail="no project open -- POST /projects or /projects/open first"
        )
    return bundle  # type: ignore[no-any-return]


def _recents_path(request: Request) -> Path:
    settings = request.app.state.settings
    return Path(settings.data_dir) / _RECENTS_FILENAME


def _load_recents(request: Request) -> dict[str, dict[str, str]]:
    path = _recents_path(request)
    if not path.is_file():
        return {}
    try:
        return dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        logger.warning("could not read %s, starting fresh", path)
        return {}


def _remember_recent(request: Request, bundle: BundleHandle) -> None:
    recents = _load_recents(request)
    recents[bundle.id] = {
        "id": bundle.id,
        "name": bundle.name,
        "bundle_path": str(bundle.bundle_path),
        "last_opened_at": datetime.now(UTC).replace(tzinfo=None).isoformat(),
    }
    path = _recents_path(request)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(recents, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _open_and_remember(request: Request, bundle: BundleHandle) -> None:
    request.app.state.bundle = bundle
    _remember_recent(request, bundle)


@router.post("", response_model=ProjectCreateResponse, status_code=201)
async def create_project(body: ProjectCreateRequest, request: Request) -> ProjectCreateResponse:
    try:
        bundle = create_bundle(Path(body.path) if body.path else None, body.name)
    except BundleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    _open_and_remember(request, bundle)
    logger.info("created project %s (%s) at %s", bundle.name, bundle.id, bundle.bundle_path)
    return ProjectCreateResponse(id=bundle.id, bundle_path=str(bundle.bundle_path))


@router.post("/open", response_model=ProjectCreateResponse)
async def open_project(body: ProjectOpenRequest, request: Request) -> ProjectCreateResponse:
    try:
        bundle = open_bundle(Path(body.bundle_path))
    except BundleError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    _open_and_remember(request, bundle)
    logger.info("opened project %s (%s) at %s", bundle.name, bundle.id, bundle.bundle_path)
    return ProjectCreateResponse(id=bundle.id, bundle_path=str(bundle.bundle_path))


@router.get("/recent", response_model=list[RecentProjectEntry])
async def recent_projects(request: Request) -> list[RecentProjectEntry]:
    recents: dict[str, dict[str, Any]] = _load_recents(request)
    entries = [RecentProjectEntry.model_validate(value) for value in recents.values()]
    return sorted(entries, key=lambda entry: entry.last_opened_at, reverse=True)


@router.get("/{project_id}", response_model=ProjectSummary)
async def get_project(project_id: str, request: Request) -> ProjectSummary:
    bundle = get_open_bundle(request)
    if bundle.id != project_id:
        raise HTTPException(status_code=404, detail=f"project {project_id} is not open")
    with bundle.session_factory() as session:
        row = repos.get_project(session, project_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"project {project_id} not found")
        return ProjectSummary(
            id=row.id,
            name=row.name,
            bundle_path=row.bundle_path,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


__all__ = ["get_open_bundle", "router"]
