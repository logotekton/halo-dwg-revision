"""``POST /projects/{id}/drawing-sets`` (import) and ``GET /drawing-sets/{id}/files``
(``docs/contracts/wave-3.md``).

Mounted at bare ``/api/v1`` (see ``api/main.py``) because the two paths don't
share one REST-nested prefix: creation nests under ``/projects/{project_id}``,
the read nests under ``/drawing-sets/{drawing_set_id}``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status

from halo_engine.api import jobs
from halo_engine.api.routers.projects import get_open_bundle
from halo_engine.db import repos
from halo_engine.ingest.pipeline import detect_format
from halo_engine.model.drawing import (
    DrawingFileSummary,
    DrawingFormat,
    DrawingSetCreateRequest,
    DrawingSetCreateResponse,
    ImportStatus,
)

logger = logging.getLogger("halo_engine.api.drawing_sets")

router = APIRouter()


@router.post(
    "/projects/{project_id}/drawing-sets",
    response_model=DrawingSetCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_drawing_set(
    project_id: str, body: DrawingSetCreateRequest, request: Request
) -> DrawingSetCreateResponse:
    """Copy-in + convert + build-working-DXF + stats for every file in ``body.files``.

    Returns immediately with a ``job_id`` -- the actual work runs as a
    background ``asyncio.Task`` (``api/jobs.py``), reported over
    ``/api/v1/ws`` and pollable via ``GET /jobs/{job_id}``. Existence of
    each source path is checked while the job runs, not here (a missing
    file fails just that one row, not the whole request).
    """
    bundle = get_open_bundle(request)
    if bundle.id != project_id:
        raise HTTPException(status_code=404, detail=f"project {project_id} is not open")

    with bundle.session_factory() as session:
        drawing_set = repos.create_drawing_set(session, project_id=project_id)
        file_rows = [
            repos.create_drawing_file(
                session,
                drawing_set_id=drawing_set.id,
                original_path=path,
                original_name=Path(path).name,
                sha256="",  # filled in once copy_original_step runs
                format=_best_effort_format(path).value,
                import_status=ImportStatus.PENDING.value,
            )
            for path in body.files
        ]
        drawing_set_id = drawing_set.id
        files_for_job = [(row.id, row.original_path) for row in file_rows]

    job_manager = jobs.get_job_manager(request.app)
    job = job_manager.create(drawing_set_id=drawing_set_id)

    task = asyncio.create_task(
        jobs.run_drawing_set_import(
            request.app,
            job_id=job.id,
            bundle=bundle,
            drawing_set_id=drawing_set_id,
            files=files_for_job,
            search_paths=body.search_paths,
            converter_fallback=body.converter_fallback,
        )
    )
    job_manager.set_task(job.id, task)

    return DrawingSetCreateResponse(job_id=job.id, drawing_set_id=drawing_set_id)


def _best_effort_format(path: str) -> DrawingFormat:
    """Format guess from the extension alone, for the row FastAPI returns before the job runs.

    ``ingest/pipeline.py``'s ``copy_original_step`` re-derives and persists
    this from the same rule once the job actually opens the file; an
    unrecognised extension defaults to DXF so the placeholder row still
    validates -- the job's own error handling reports the real problem.
    """
    try:
        return detect_format(Path(path))
    except ValueError:
        return DrawingFormat.DXF


@router.get("/drawing-sets/{drawing_set_id}/files", response_model=list[DrawingFileSummary])
async def list_drawing_set_files(drawing_set_id: str, request: Request) -> list[DrawingFileSummary]:
    bundle = get_open_bundle(request)
    with bundle.session_factory() as session:
        if repos.get_drawing_set(session, drawing_set_id) is None:
            raise HTTPException(status_code=404, detail=f"drawing_set {drawing_set_id} not found")
        rows = repos.list_files_for_set(session, drawing_set_id)
        return [
            DrawingFileSummary(
                id=row.id,
                original_name=row.original_name,
                format=DrawingFormat(row.format),
                dwg_version=row.dwg_version,
                entity_count=row.entity_count,
                codepage_effective=row.codepage_effective,
                import_status=ImportStatus(row.import_status),
                error_message=row.error_message,
                working_dxf_path=row.working_dxf_path,
                parser_crosscheck=row.parser_crosscheck,
            )
            for row in rows
        ]


__all__ = ["router"]
