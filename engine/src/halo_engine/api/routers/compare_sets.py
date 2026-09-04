"""``POST /compare/sets``, ``GET /compare/sets``, ``GET /compare/sets/{id}``,
``GET /compare/sets/{id}/files`` (brief R1-03, ``docs/contracts/r1.md`` §7).

Mounted under ``/api/v1/compare`` (``api/main.py``), alongside
``compare_zwcad.py`` (R1-02). Creating a set opens (or creates) the bundle at
``<project_dir>/.halo`` and stores it as ``app.state.bundle`` -- the same
single-open-project rule ``api/routers/projects.py`` documents -- then starts
the ``compare.ingest`` job (``compare/ingest_set.py``) as a background
``asyncio.Task``, the same 202-then-poll pattern as
``api/routers/drawing_sets.py::create_drawing_set``.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status

from halo_engine.api import jobs
from halo_engine.bundle.create import BundleError, BundleHandle, create_bundle, open_bundle
from halo_engine.compare import ingest_set
from halo_engine.compare.config import load_compare_config
from halo_engine.compare.zwcad import detect as zwcad_detect
from halo_engine.db import repos
from halo_engine.db.models import CompareSetRow, DrawingFileRow, DrawingSetRow
from halo_engine.model.compare import (
    CompareFileEntry,
    CompareSetCreateRequest,
    CompareSetCreateResponse,
)
from halo_engine.model.drawing import ImportStatus

logger = logging.getLogger("halo_engine.api.compare_sets")

router = APIRouter()


def _default_project_dir(before_dir: Path, after_dir: Path) -> Path:
    """Contract §1: the two set folders' common parent, or the after folder's
    parent when they are not siblings."""
    if before_dir.parent == after_dir.parent:
        return before_dir.parent
    return after_dir.parent


def _open_or_create_bundle(project_dir: Path) -> BundleHandle:
    bundle_path = project_dir / ".halo"
    if (bundle_path / "project.json").is_file():
        try:
            return open_bundle(bundle_path)
        except BundleError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        return create_bundle(bundle_path, project_dir.name)
    except BundleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


def _create_side(
    session: Any,
    *,
    project_id: str,
    role: str,
    source_dir: Path,
    ignore_patterns: list[str],
) -> DrawingSetRow:
    """One ``drawing_set`` (with its ``drawing_file`` rows) for one side of a compare set.

    ``role``/``source_dir`` are R1 additions to ``DrawingSetRow`` (R1-01) with
    no dedicated ``repos`` setter yet -- set directly on the ORM row
    ``repos.create_drawing_set`` already returned, bound to this same
    session, rather than adding one to ``db/repos.py`` (owned by R1-01).
    """
    drawing_set = repos.create_drawing_set(session, project_id=project_id, label=source_dir.name)
    drawing_set.role = role
    drawing_set.source_dir = str(source_dir)
    session.commit()
    session.refresh(drawing_set)

    for planned in ingest_set.plan_set_files(source_dir, ignore_patterns):
        row = repos.create_drawing_file(
            session,
            drawing_set_id=drawing_set.id,
            original_path=str(planned.path),
            original_name=planned.name,
            sha256="",
            format=planned.format.value,
            import_status=(
                ImportStatus.EXCLUDED.value if planned.excluded else ImportStatus.PENDING.value
            ),
        )
        if planned.excluded:
            repos.update_drawing_file(session, row.id, excluded_reason=planned.excluded_reason)
    return drawing_set


@router.post("/sets", response_model=CompareSetCreateResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_compare_set(
    body: CompareSetCreateRequest, request: Request
) -> CompareSetCreateResponse:
    """Validate the two folders and ``run_date``, open the bundle, plan both
    sides' files, and start ``compare.ingest`` (contract §7 Goal 1)."""
    before_dir = Path(body.before_dir)
    after_dir = Path(body.after_dir)
    if not before_dir.is_dir():
        raise HTTPException(status_code=422, detail=f"before_dir is not a directory: {before_dir}")
    if not after_dir.is_dir():
        raise HTTPException(status_code=422, detail=f"after_dir is not a directory: {after_dir}")

    project_dir = (
        Path(body.project_dir) if body.project_dir else _default_project_dir(before_dir, after_dir)
    )
    if not project_dir.is_dir():
        raise HTTPException(
            status_code=422, detail=f"project_dir is not a directory: {project_dir}"
        )

    bundle = _open_or_create_bundle(project_dir)
    request.app.state.bundle = bundle

    config = load_compare_config(bundle)
    ignore_patterns = list(config.ingest.ignore_patterns)

    with bundle.session_factory() as session:
        before_set = _create_side(
            session,
            project_id=bundle.id,
            role="before",
            source_dir=before_dir,
            ignore_patterns=ignore_patterns,
        )
        after_set = _create_side(
            session,
            project_id=bundle.id,
            role="after",
            source_dir=after_dir,
            ignore_patterns=ignore_patterns,
        )
        compare_set = repos.create_compare_set(
            session,
            project_id=bundle.id,
            before_set_id=before_set.id,
            after_set_id=after_set.id,
            run_date=body.run_date,
            status="ingesting",
            options=dict(body.options),
        )
        compare_set_id = compare_set.id

    job_manager = jobs.get_job_manager(request.app)
    job = job_manager.create(compare_set_id=compare_set_id, kind="compare.ingest")

    with bundle.session_factory() as session:
        repos.update_compare_set(session, compare_set_id, stats={"last_job_id": job.id})

    task = asyncio.create_task(
        ingest_set.run_compare_set_ingest(
            request.app, job=job, bundle=bundle, compare_set_id=compare_set_id
        )
    )
    job_manager.set_task(job.id, task)

    return CompareSetCreateResponse(
        compare_set_id=compare_set_id, project_id=bundle.id, job_id=job.id
    )


def _get_open_bundle_or_404(
    request: Request, compare_set_id: str
) -> tuple[BundleHandle, CompareSetRow]:
    """The open bundle plus this ``compare_set`` row -- every read endpoint needs both.

    Unlike ``api/routers/projects.py::get_open_bundle`` (a 409 for "no
    project open at all"), an unknown ``compare_set_id`` is a 404 -- the
    bundle being open is a precondition of the *engine*, not of this one
    resource, which the renderer only ever reaches after ``POST
    /compare/sets`` opened it for this same process.
    """
    bundle: BundleHandle | None = getattr(request.app.state, "bundle", None)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"compare_set {compare_set_id} not found")
    with bundle.session_factory() as session:
        row = repos.get_compare_set(session, compare_set_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"compare_set {compare_set_id} not found")
    return bundle, row


def _set_side_summary(rows: list[DrawingFileRow], drawing_set: DrawingSetRow) -> dict[str, Any]:
    converted = sum(1 for r in rows if r.import_status == ImportStatus.DONE.value)
    failed = sum(
        1
        for r in rows
        if r.import_status
        in (ImportStatus.FAILED.value, ImportStatus.NEEDS_MANUAL_CONVERSION.value)
    )
    excluded = sum(1 for r in rows if r.import_status == ImportStatus.EXCLUDED.value)
    return {
        "set_id": drawing_set.id,
        "dir": drawing_set.source_dir or "",
        "label": drawing_set.label or "",
        "files": len(rows),
        "converted": converted,
        "failed": failed,
        "excluded": excluded,
    }


def _build_summary(
    bundle: BundleHandle, compare_set: CompareSetRow, job_id: str | None
) -> dict[str, Any]:
    with bundle.session_factory() as session:
        before_set = repos.get_drawing_set(session, compare_set.before_set_id)
        after_set = repos.get_drawing_set(session, compare_set.after_set_id)
        before_rows = repos.list_files_for_set(session, compare_set.before_set_id)
        after_rows = repos.list_files_for_set(session, compare_set.after_set_id)

    stats = compare_set.stats or {}
    converter_stats = stats.get("converter") or {"before": None, "after": None, "mismatch_files": 0}
    crosscheck_stats = stats.get("crosscheck")
    crosscheck = (
        None
        if crosscheck_stats is None
        else {
            "sampled": int(crosscheck_stats.get("sampled", 0)),
            "mismatched": int(crosscheck_stats.get("mismatched", 0)),
        }
    )

    assert before_set is not None and after_set is not None  # FK integrity within one bundle

    return {
        "id": compare_set.id,
        "project_id": compare_set.project_id,
        "project_dir": str(bundle.layout.root.parent),
        "status": compare_set.status,
        "run_date": compare_set.run_date,
        "before": _set_side_summary(before_rows, before_set),
        "after": _set_side_summary(after_rows, after_set),
        "converter": converter_stats,
        "zwcad": zwcad_detect(),
        "fonts_missing": stats.get("fonts_missing", []),
        "crosscheck": crosscheck,
        # R1-04 (frame extraction/matching) has not run yet in this task.
        "frames": None,
        "pairs": None,
        "last_job_id": job_id or stats.get("last_job_id"),
    }


@router.get("/sets/{compare_set_id}")
async def get_compare_set_summary(compare_set_id: str, request: Request) -> dict[str, Any]:
    bundle, compare_set = _get_open_bundle_or_404(request, compare_set_id)
    job_manager = jobs.get_job_manager(request.app)
    latest = job_manager.latest_for_compare_set(compare_set_id)
    return _build_summary(bundle, compare_set, latest.id if latest is not None else None)


@router.get("/sets")
async def list_compare_sets(request: Request) -> list[dict[str, Any]]:
    bundle: BundleHandle | None = getattr(request.app.state, "bundle", None)
    if bundle is None:
        return []
    with bundle.session_factory() as session:
        rows = repos.list_compare_sets(session, project_id=bundle.id)
    job_manager = jobs.get_job_manager(request.app)
    summaries = []
    for row in rows:
        latest = job_manager.latest_for_compare_set(row.id)
        summaries.append(_build_summary(bundle, row, latest.id if latest is not None else None))
    return summaries


@router.get("/sets/{compare_set_id}/files", response_model=list[CompareFileEntry])
async def list_compare_set_files(compare_set_id: str, request: Request) -> list[CompareFileEntry]:
    bundle, compare_set = _get_open_bundle_or_404(request, compare_set_id)
    with bundle.session_factory() as session:
        before_rows = repos.list_files_for_set(session, compare_set.before_set_id)
        after_rows = repos.list_files_for_set(session, compare_set.after_set_id)

    entries: list[CompareFileEntry] = []
    for role, rows in (("before", before_rows), ("after", after_rows)):
        for row in rows:
            entries.append(
                CompareFileEntry(
                    id=row.id,
                    role=role,  # type: ignore[arg-type]
                    original_name=row.original_name,
                    import_status=row.import_status,
                    converter=row.converter,
                    excluded_reason=row.excluded_reason,
                    error_message=row.error_message,
                    entity_count=row.entity_count,
                    parser_crosscheck=row.parser_crosscheck,
                    converter_meta=row.converter_meta,
                )
            )
    return entries


__all__ = ["router"]
