"""``GET /files/{id}/xrefs``, ``POST /files/{id}/xrefs/{name}/resolve``,
``PUT /projects/{id}/search-paths``, ``GET``/``PUT /projects/{id}/import-settings``
(brief W3-06 Goal / addendum 3, ``docs/contracts/wave-3.md`` "W3-03 라우터 패턴").

Resolution order itself stays the engine's (``ingest/xref.py``) -- this
router only ever adds search paths / ignore patterns and re-runs the
existing import job machinery (``api/jobs.py``) against them, per the
brief's Constraints: "해석 순서는 엔진이 소유. UI는 검색 경로만 더한다."
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from halo_engine.api import jobs
from halo_engine.api.routers.projects import get_open_bundle
from halo_engine.db import repos
from halo_engine.db.models import DrawingFileRow
from halo_engine.model.xref import (
    ImportSettings,
    SearchPathsUpdateRequest,
    SearchPathsUpdateResponse,
    XrefLinkStatus,
    XrefLinkSummary,
    XrefResolveRequest,
    XrefResolveResponse,
)

logger = logging.getLogger("halo_engine.api.xrefs")

router = APIRouter()


def _get_file_row(request: Request, file_id: str) -> DrawingFileRow:
    bundle = get_open_bundle(request)
    with bundle.session_factory() as session:
        row = repos.get_drawing_file(session, file_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"file {file_id} not found")
        session.expunge(row)
        return row


def _dedup(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for path in paths:
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _start_reimport(
    request: Request, *, drawing_set_id: str, file_id: str, source_path: str
) -> str:
    """Re-runs the import for exactly one already-known file, over the same
    job machinery a fresh ``POST .../drawing-sets`` uses (``api/jobs.py``
    reads the project's persisted search paths itself -- see that module's
    docstring -- so nothing XREF-specific needs to be passed here beyond
    the file itself)."""
    bundle = get_open_bundle(request)
    job_manager = jobs.get_job_manager(request.app)
    job = job_manager.create(drawing_set_id=drawing_set_id)
    task = asyncio.create_task(
        jobs.run_drawing_set_import(
            request.app,
            job_id=job.id,
            bundle=bundle,
            drawing_set_id=drawing_set_id,
            files=[(file_id, source_path)],
            search_paths=[],
            converter_fallback=None,
        )
    )
    job_manager.set_task(job.id, task)
    return job.id


@router.get("/files/{file_id}/xrefs", response_model=list[XrefLinkSummary])
async def get_file_xrefs(file_id: str, request: Request) -> list[XrefLinkSummary]:
    """The XREF tree for one host file (brief Goal: "파일 패널에 XREF
    트리(호스트 -> 참조, 상태 아이콘)"), from the most recent import's
    ``xref_link`` rows (``ingest/working_dxf.py``'s ``resolved_xrefs``/
    ``unresolved_xrefs``, persisted by ``api/jobs.py`` after each build)."""
    _get_file_row(request, file_id)  # 404s if unknown
    bundle = get_open_bundle(request)
    with bundle.session_factory() as session:
        links = repos.list_xref_links_for_file(session, file_id)
        return [
            XrefLinkSummary(
                block_name=link.block_name,
                declared_path=link.declared_path,
                resolved_path=link.resolved_path,
                status=XrefLinkStatus(link.status),
            )
            for link in links
        ]


@router.post("/files/{file_id}/xrefs/{block_name}/resolve", response_model=XrefResolveResponse)
async def resolve_file_xref(
    file_id: str, block_name: str, body: XrefResolveRequest, request: Request
) -> XrefResolveResponse:
    """Brief Goal: "파일을 개별 매칭하면 프로젝트 검색 경로에 저장되고
    재임포트가 실행된다". ``resolved_path``'s parent directory is added to
    the project's search paths (same mechanism a folder pick uses via
    ``PUT .../search-paths``) and this one host is re-imported."""
    row = _get_file_row(request, file_id)
    resolved = Path(body.resolved_path)
    if not resolved.is_file():
        raise HTTPException(status_code=422, detail=f"not a file: {body.resolved_path}")

    bundle = get_open_bundle(request)
    with bundle.session_factory() as session:
        project = repos.get_project(session, bundle.id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"project {bundle.id} not found")
        updated_paths = _dedup([*project.search_paths, str(resolved.parent)])
        repos.update_project_settings(session, bundle.id, search_paths=updated_paths)

    job_id = _start_reimport(
        request, drawing_set_id=row.drawing_set_id, file_id=file_id, source_path=row.original_path
    )
    logger.info(
        "xref %r on file %s manually matched to %s -- re-import job %s",
        block_name,
        file_id,
        resolved,
        job_id,
    )
    return XrefResolveResponse(job_id=job_id, file_id=file_id)


@router.put("/projects/{project_id}/search-paths", response_model=SearchPathsUpdateResponse)
async def update_search_paths(
    project_id: str, body: SearchPathsUpdateRequest, request: Request
) -> SearchPathsUpdateResponse:
    """Brief Goal: 폴더 지정 dialog flow -- replaces the project's search-path
    list and optionally re-imports the files named in ``reimport_file_ids``
    (typically every file that currently has an unresolved XREF)."""
    bundle = get_open_bundle(request)
    if bundle.id != project_id:
        raise HTTPException(status_code=404, detail=f"project {project_id} is not open")

    with bundle.session_factory() as session:
        project = repos.update_project_settings(
            session, project_id, search_paths=_dedup(body.search_paths)
        )
        search_paths = list(project.search_paths)
        reimport_rows = [repos.get_drawing_file(session, fid) for fid in body.reimport_file_ids]

    job_ids: list[str] = []
    for file_id, row in zip(body.reimport_file_ids, reimport_rows, strict=True):
        if row is None:
            raise HTTPException(status_code=404, detail=f"file {file_id} not found")
        job_ids.append(
            _start_reimport(
                request,
                drawing_set_id=row.drawing_set_id,
                file_id=file_id,
                source_path=row.original_path,
            )
        )

    return SearchPathsUpdateResponse(search_paths=search_paths, job_ids=job_ids)


@router.get("/projects/{project_id}/import-settings", response_model=ImportSettings)
async def get_import_settings(project_id: str, request: Request) -> ImportSettings:
    """Brief addendum 3: "설정 UI는 단순 텍스트 목록" -- search paths and
    ``import.ignore_patterns`` together, for the project settings panel."""
    bundle = get_open_bundle(request)
    if bundle.id != project_id:
        raise HTTPException(status_code=404, detail=f"project {project_id} is not open")
    with bundle.session_factory() as session:
        project = repos.get_project(session, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail=f"project {project_id} not found")
        return ImportSettings(
            search_paths=list(project.search_paths), ignore_patterns=list(project.ignore_patterns)
        )


@router.put("/projects/{project_id}/import-settings", response_model=ImportSettings)
async def update_import_settings(
    project_id: str, body: ImportSettings, request: Request
) -> ImportSettings:
    bundle = get_open_bundle(request)
    if bundle.id != project_id:
        raise HTTPException(status_code=404, detail=f"project {project_id} is not open")
    with bundle.session_factory() as session:
        project = repos.update_project_settings(
            session,
            project_id,
            search_paths=_dedup(body.search_paths),
            ignore_patterns=list(body.ignore_patterns),
        )
        return ImportSettings(
            search_paths=list(project.search_paths), ignore_patterns=list(project.ignore_patterns)
        )


__all__ = ["router"]
