"""``/compare/sets/{id}/export`` and the run endpoints (contract §7, brief R1-09 §3).

Screen D is "출력하고, 무엇이 나왔는지 보여준다", and these three endpoints are
all of it: one ``POST`` starts the ``compare.export`` job and answers with the
``run`` row it just opened, one ``GET`` reports what that run produced, and one
``GET`` hands back the change list as a TSV the user can drop into Excel.

The 202 carries ``run_id`` as well as ``job_id`` (contract §7) because the run
row -- and with it the output folder and the revision layer name, including the
``-2`` suffix of a second export on the same date -- is decided before the job
starts. The renderer can therefore show "출력/2026-09-04-2 에 쓰는 중" while the
job is still on its first sheet, instead of guessing.

Exporting is only offered from ``compared``: there is nothing to approve before
the comparison has run, so anything else is a 409 rather than an empty output
folder.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from halo_engine.api import jobs
from halo_engine.bundle.create import BundleHandle
from halo_engine.compare import export as export_mod
from halo_engine.compare.config import load_compare_config
from halo_engine.db import repos
from halo_engine.db.models import CompareSetRow, RunRow
from halo_engine.model.compare import ExportAcceptedResponse, ExportRequest

logger = logging.getLogger("halo_engine.api.compare_export")

router = APIRouter()

#: The only ``compare_set.status`` an export may start from (contract §3).
#: ``exporting`` is excluded on purpose: two exports of one set at the same time
#: would race for the output folder's suffix.
EXPORTABLE_STATUSES = frozenset({"compared"})

#: ``Content-Type`` of ``GET .../tsv`` (contract §7). The charset is spelled out
#: because the file is UTF-8 without a BOM and a browser that guesses would
#: guess Latin-1 and mangle every Korean 도면명.
TSV_MEDIA_TYPE = "text/tab-separated-values; charset=utf-8"


def _bundle_or_404(request: Request, what: str, identifier: str) -> BundleHandle:
    bundle: BundleHandle | None = getattr(request.app.state, "bundle", None)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"{what} {identifier} not found")
    return bundle


def _compare_set_or_404(
    request: Request, compare_set_id: str
) -> tuple[BundleHandle, CompareSetRow]:
    bundle = _bundle_or_404(request, "compare_set", compare_set_id)
    with bundle.session_factory() as session:
        row = repos.get_compare_set(session, compare_set_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"compare_set {compare_set_id} not found")
    return bundle, row


def _run_or_404(request: Request, run_id: str) -> tuple[BundleHandle, RunRow]:
    bundle = _bundle_or_404(request, "run", run_id)
    with bundle.session_factory() as session:
        row = repos.get_run(session, run_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"run {run_id} not found")
        session.expunge(row)
    return bundle, row


@router.post(
    "/sets/{compare_set_id}/export",
    response_model=ExportAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_export(
    compare_set_id: str, body: ExportRequest, request: Request
) -> ExportAcceptedResponse:
    """Start ``compare.export``: markup drawings, ``changes.tsv``, ``run.json``."""
    bundle, compare_set = _compare_set_or_404(request, compare_set_id)
    if compare_set.status not in EXPORTABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"compare_set {compare_set_id} is {compare_set.status}; "
                f"export needs one of {sorted(EXPORTABLE_STATUSES)}"
            ),
        )

    config = load_compare_config(bundle)
    run = export_mod.open_run(
        bundle,
        compare_set_id=compare_set_id,
        run_date=body.run_date,
        scope=body.scope,
        method=body.method,
        config=config,
    )

    job_manager = jobs.get_job_manager(request.app)
    job = job_manager.create(compare_set_id=compare_set_id, kind="compare.export")

    with bundle.session_factory() as session:
        row = repos.get_compare_set(session, compare_set_id)
        stats = dict((row.stats if row is not None else None) or {})
        stats["last_job_id"] = job.id
        repos.update_compare_set(session, compare_set_id, stats=stats)

    async def _export() -> None:
        # ``run_export`` hands the finished row back to a direct caller; the
        # job registry only tracks tasks that return nothing, and the row is
        # already reachable through ``GET /compare/runs/{run_id}``.
        await export_mod.run_export(
            request.app,
            job=job,
            bundle=bundle,
            compare_set_id=compare_set_id,
            run_date=body.run_date,
            scope=body.scope,
            method=body.method,
            run_id=run.id,
        )

    job_manager.set_task(job.id, asyncio.create_task(_export()))
    return ExportAcceptedResponse(job_id=job.id, run_id=run.id)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, request: Request) -> dict[str, Any]:
    """One export, as ``compare/run.schema.json`` describes it (contract §7).

    Served as the schema's own document rather than through a hand-written
    pydantic mirror -- the same choice ``GET /compare/pairs/{id}/clusters``
    made, and ``tests/compare/test_export.py`` validates the payload against
    the schema file so the two cannot drift.
    """
    _bundle, row = _run_or_404(request, run_id)
    return export_mod.run_payload(row, for_disk=False)


@router.get("/runs/{run_id}/tsv")
async def get_run_tsv(run_id: str, request: Request) -> Response:
    """The run's ``changes.tsv``, byte for byte as it was written (contract §7).

    Served from the file rather than rebuilt from the database: what the user
    sees in the browser and what they find in the output folder have to be the
    same list, including the rows for clusters that were 무시.
    """
    _bundle, row = _run_or_404(request, run_id)
    path = Path(row.output_dir) / export_mod.CHANGES_TSV_NAME
    if not path.is_file():
        raise HTTPException(
            status_code=409,
            detail=f"run {run_id} has not written its change list yet ({row.status})",
        )
    return Response(
        content=path.read_bytes(),
        media_type=TSV_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="{export_mod.CHANGES_TSV_NAME}"'},
    )


__all__ = ["EXPORTABLE_STATUSES", "TSV_MEDIA_TYPE", "router"]
