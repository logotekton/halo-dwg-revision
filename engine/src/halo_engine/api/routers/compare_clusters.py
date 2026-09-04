"""``/compare/sets/{id}/run`` and the cluster endpoints (contract §7, brief R1-06 §5).

Screen C of the app is one sheet with its cloud marks, and this router is what
fills it: one ``POST`` compares every matched 도곽 짝 and writes the two files
per pair, one ``GET`` serves the sidecar, one ``PATCH`` records the user's
승인·무시, and one ``GET`` streams the compare DXF the viewer draws.

The comparison itself is a ``compare.run`` job over the job manager's
``ProcessPoolExecutor`` (contract §6.2): opening two 350,000-entity drawings
and diffing them is tens of seconds of CPU per sheet, and the renderer must
stay responsive while a 375-sheet set is compared. What crosses the process
boundary is a :class:`~halo_engine.compare.compare_dxf.ComparePairInput` -- two
paths, two picklable frame records and the settings -- and what comes back is a
:class:`~halo_engine.compare.compare_dxf.ComparePairOutput`. No ezdxf document
ever does.

Two decisions worth knowing when reading the job body:

* **A failed sheet costs one sheet.** ``compare_pair`` returns its error rather
  than raising, and the failures are counted into ``compare_set.stats`` so the
  summary can name them. A set where one drawing was converted badly must still
  produce the other 374 sheets.
* **The user's review survives a re-run.** ``repos.replace_clusters`` carries
  ``decision``/``user_label``/``note`` over by cluster signature, and this
  router then writes those three fields -- and only those three -- back into
  ``clusters.json``. Everything the *comparison* computed stays byte-for-byte
  what the worker wrote, which is what contract §8 requires.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status

from halo_engine.api import jobs
from halo_engine.bundle.create import BundleHandle
from halo_engine.compare import compare_dxf as compare_dxf_mod
from halo_engine.compare import match as match_mod
from halo_engine.compare.compare_dxf import ComparePairInput, ComparePairOutput
from halo_engine.compare.config import load_compare_config
from halo_engine.compare.frames import FrameRecord
from halo_engine.db import repos
from halo_engine.db.models import CompareSetRow, SheetFrameRow, SheetPairRow
from halo_engine.model.compare import (
    ClusterDecisionRequest,
    ClusterView,
    CompareRunRequest,
    JobAcceptedResponse,
)

logger = logging.getLogger("halo_engine.api.compare_clusters")

router = APIRouter()

#: ``compare_set.status`` values a comparison may start from. Before ``matched``
#: there are no 도곽 짝 to compare; ``compared`` re-runs, which is what the user
#: asking again means (contract §7: 409 for anything else).
COMPARABLE_STATUSES = frozenset({"matched", "compared"})

#: ``sheet_pair.status`` values the run skips. A sheet that exists on one side
#: only, a file with no title block and a pair whose two files came from
#: different converters have nothing to diff (brief §5).
SKIPPED_PAIR_STATUSES = frozenset(
    {
        match_mod.STATUS_ADDED,
        match_mod.STATUS_REMOVED,
        match_mod.STATUS_UNRECOGNIZED,
        match_mod.STATUS_CONVERTER_MISMATCH,
    }
)

#: ``Content-Type`` of ``GET .../compare-dxf`` (contract §7).
DXF_MEDIA_TYPE = "application/dxf"


# --------------------------------------------------------------------------- lookup


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


def _pair_or_404(request: Request, pair_id: str) -> tuple[BundleHandle, SheetPairRow]:
    bundle = _bundle_or_404(request, "sheet_pair", pair_id)
    with bundle.session_factory() as session:
        row = repos.get_pair(session, pair_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"sheet_pair {pair_id} not found")
    return bundle, row


def _frame_record(row: SheetFrameRow) -> FrameRecord:
    """A ``sheet_frame`` row back as the picklable record the engine works with."""
    return FrameRecord(
        file_id=row.file_id,
        kind=row.kind,
        titleblock_handle=row.titleblock_handle,
        block_name=row.block_name,
        bbox=list(row.bbox or []),
        sheet_no=row.sheet_no,
        sheet_title=row.sheet_title,
        scale_text=row.scale_text,
        scale_denominator=row.scale_denominator,
        date_text=row.date_text,
        norm_key=row.norm_key,
        sort_index=row.sort_index,
        entity_handles=list(row.entity_handles or []),
        provenance=dict(row.provenance or {}),
        attributes=dict(row.attributes or {}),
        role=row.role,
    )


def _sidecar_path(bundle: BundleHandle, pair: SheetPairRow) -> Path:
    if pair.clusters_json_path:
        return Path(pair.clusters_json_path)
    return bundle.layout.compare_pair_dir(pair.id) / compare_dxf_mod.CLUSTERS_JSON_NAME


def _compare_dxf_path(bundle: BundleHandle, pair: SheetPairRow) -> Path:
    if pair.compare_dxf_path:
        return Path(pair.compare_dxf_path)
    return bundle.layout.compare_pair_dir(pair.id) / compare_dxf_mod.COMPARE_DXF_NAME


# --------------------------------------------------------------------------- the job


def _plan(
    bundle: BundleHandle, compare_set: CompareSetRow, pair_ids: list[str] | None
) -> tuple[list[ComparePairInput], list[dict[str, str]]]:
    """The pairs this run will compare, and the ones it is skipping and why."""
    layout = bundle.layout
    with bundle.session_factory() as session:
        pairs = repos.list_pairs(session, compare_set.id)
        frames = {row.id: row for row in repos.list_frames(session, compare_set.id)}
        working = {
            frame.file_id: repos.get_drawing_file(session, frame.file_id)
            for frame in frames.values()
        }

    wanted = set(pair_ids) if pair_ids is not None else None
    tasks: list[ComparePairInput] = []
    skipped: list[dict[str, str]] = []
    for pair in sorted(pairs, key=lambda row: (row.sort_key, row.id)):
        if wanted is not None and pair.id not in wanted:
            continue
        if pair.status in SKIPPED_PAIR_STATUSES:
            skipped.append({"pair_id": pair.id, "reason": pair.status})
            continue
        before = frames.get(pair.before_frame_id or "")
        after = frames.get(pair.after_frame_id or "")
        if before is None or after is None:
            skipped.append({"pair_id": pair.id, "reason": "one_sided"})
            continue
        before_file = working.get(before.file_id)
        after_file = working.get(after.file_id)
        if (
            before_file is None
            or after_file is None
            or not before_file.working_dxf_path
            or not after_file.working_dxf_path
        ):
            skipped.append({"pair_id": pair.id, "reason": "no_working_dxf"})
            continue
        tasks.append(
            ComparePairInput(
                pair_id=pair.id,
                pair_key=after.norm_key or before.norm_key or pair.sort_key,
                before_path=str(before_file.working_dxf_path),
                after_path=str(after_file.working_dxf_path),
                before_frame=_frame_record(before),
                after_frame=_frame_record(after),
                run_date=compare_set.run_date,
                out_dir=str(layout.compare_pair_dir(pair.id)),
                bundle_root=str(layout.root),
            )
        )
    return tasks, skipped


def _store(bundle: BundleHandle, result: ComparePairOutput) -> None:
    """Write one pair's comparison into the database and reconcile the sidecar.

    The order matters. ``replace_clusters`` is what carries a previous review
    forward, so the rows it returns -- not the ones the worker computed -- are
    the truth about ``decision``/``user_label``/``note``, and the sidecar is
    brought into line with them afterwards.
    """
    with bundle.session_factory() as session:
        repos.replace_changes(session, result.pair_id, [c.to_row() for c in result.changes])
        rows = repos.replace_clusters(
            session, result.pair_id, [c.to_row() for c in result.clusters], keep_decisions=True
        )
        decisions = {
            int(row.number): (row.decision, row.user_label, row.note)
            for row in rows
            if row.decision != "pending" or row.user_label is not None or row.note is not None
        }
        repos.update_pair(
            session,
            result.pair_id,
            status=result.status,
            compare_dxf_path=result.compare_dxf_path,
            clusters_json_path=result.clusters_json_path,
            warnings=result.warnings or None,
        )
    if decisions and result.clusters_json_path:
        compare_dxf_mod.apply_decisions(Path(result.clusters_json_path), decisions)


async def run_comparison(
    app: Any,
    *,
    job: jobs.JobRecord,
    bundle: BundleHandle,
    compare_set_id: str,
    pair_ids: list[str] | None,
) -> None:
    """The ``compare.run`` job body: diff every pair, ending in status ``compared``."""

    async def _work(reporter: jobs.ProgressReporter) -> None:
        await _do_run(
            app,
            job=job,
            bundle=bundle,
            compare_set_id=compare_set_id,
            pair_ids=pair_ids,
            reporter=reporter,
        )

    await jobs.run_job(app, job, _work)


async def _do_run(
    app: Any,
    *,
    job: jobs.JobRecord,
    bundle: BundleHandle,
    compare_set_id: str,
    pair_ids: list[str] | None,
    reporter: jobs.ProgressReporter,
) -> None:
    loop = asyncio.get_running_loop()
    job_manager = jobs.get_job_manager(app)
    executor = job_manager.executor
    config = load_compare_config(bundle)

    with bundle.session_factory() as session:
        compare_set = repos.get_compare_set(session, compare_set_id)
        if compare_set is None:
            raise KeyError(f"compare_set {compare_set_id!r} not found")

    tasks, skipped = _plan(bundle, compare_set, pair_ids)

    with bundle.session_factory() as session:
        repos.update_compare_set(session, compare_set_id, status="comparing")

    counts = {"compared": 0, "changed": 0, "same": 0, "failed": 0}
    failures: list[dict[str, str]] = []
    total = len(tasks) or 1
    for index, task in enumerate(tasks, start=1):
        current = job_manager.get(job.id)
        if current is not None and current.cancel_requested:
            raise jobs.JobCancelled

        result: ComparePairOutput = await loop.run_in_executor(
            executor, compare_dxf_mod.compare_pair, task, config
        )
        if result.error:
            counts["failed"] += 1
            failures.append({"pair_id": task.pair_id, "error": result.error})
            logger.warning("comparison failed for pair %s: %s", task.pair_id, result.error)
        else:
            _store(bundle, result)
            counts["compared"] += 1
            counts[result.status] = counts.get(result.status, 0) + 1

        await reporter(
            index / total,
            f"{index}/{len(tasks)}",
            stage="compare",
            extra={
                "pair_id": task.pair_id,
                "pair_key": task.pair_key,
                "status": result.status if not result.error else "failed",
                "changes": len(result.changes),
                "clusters": len(result.clusters),
                "elapsed_s": result.elapsed_s,
            },
        )

    with bundle.session_factory() as session:
        row = repos.get_compare_set(session, compare_set_id)
        merged: dict[str, Any] = dict((row.stats if row is not None else None) or {})
        merged.update(
            {
                "last_job_id": job.id,
                "compare": {**counts, "skipped": len(skipped)},
                "compare_skipped": skipped,
                "compare_failed": failures,
            }
        )
        repos.update_compare_set(session, compare_set_id, status="compared", stats=merged)


# --------------------------------------------------------------------------- endpoints


@router.post(
    "/sets/{compare_set_id}/run",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_comparison(
    compare_set_id: str, request: Request, body: CompareRunRequest | None = None
) -> JobAcceptedResponse:
    """Start ``compare.run``: diff every matched 도곽 짝 (contract §7)."""
    bundle, compare_set = _compare_set_or_404(request, compare_set_id)
    if compare_set.status not in COMPARABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"compare_set {compare_set_id} is {compare_set.status}; "
                f"comparison needs one of {sorted(COMPARABLE_STATUSES)}"
            ),
        )

    pair_ids = body.pair_ids if body is not None else None
    if pair_ids is not None:
        with bundle.session_factory() as session:
            known = {row.id for row in repos.list_pairs(session, compare_set_id)}
        unknown = sorted(set(pair_ids) - known)
        if unknown:
            raise HTTPException(
                status_code=404,
                detail=f"sheet_pair {unknown[0]} is not in compare_set {compare_set_id}",
            )

    job_manager = jobs.get_job_manager(request.app)
    job = job_manager.create(compare_set_id=compare_set_id, kind="compare.run")

    with bundle.session_factory() as session:
        row = repos.get_compare_set(session, compare_set_id)
        merged = dict((row.stats if row is not None else None) or {})
        merged["last_job_id"] = job.id
        repos.update_compare_set(session, compare_set_id, stats=merged)

    task = asyncio.create_task(
        run_comparison(
            request.app,
            job=job,
            bundle=bundle,
            compare_set_id=compare_set_id,
            pair_ids=pair_ids,
        )
    )
    job_manager.set_task(job.id, task)
    return JobAcceptedResponse(job_id=job.id)


@router.get("/pairs/{pair_id}/clusters")
async def get_clusters(pair_id: str, request: Request) -> dict[str, Any]:
    """``clusters.json`` with the database's review merged in (contract §7).

    The file is the record of the comparison and the ``cluster`` table is the
    record of the review; the screen needs one document with both, and the
    merge happens here rather than in the file so a re-read never disagrees
    with what the user just clicked.
    """
    bundle, pair = _pair_or_404(request, pair_id)
    path = _sidecar_path(bundle, pair)
    if not path.is_file():
        raise HTTPException(
            status_code=409,
            detail=f"sheet_pair {pair_id} has not been compared yet ({pair.status})",
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    with bundle.session_factory() as session:
        rows = repos.list_clusters(session, pair_id)
    return compare_dxf_mod.merge_decisions(payload, rows)


@router.patch("/pairs/{pair_id}/clusters/{number}", response_model=ClusterView)
async def decide_cluster(
    pair_id: str, number: int, body: ClusterDecisionRequest, request: Request
) -> ClusterView:
    """Record 승인·무시, a hand-written label or a memo (contract §7).

    ``model_dump(exclude_unset=True)``: an absent key leaves the column alone,
    an explicit ``null`` clears it. Clearing a note and not mentioning it are
    different requests.
    """
    bundle, pair = _pair_or_404(request, pair_id)
    fields = body.model_dump(exclude_unset=True)
    with bundle.session_factory() as session:
        if repos.get_cluster_by_number(session, pair_id, number) is None:
            raise HTTPException(
                status_code=404, detail=f"cluster {number} of sheet_pair {pair_id} not found"
            )
        row = repos.update_cluster(session, pair_id, number, **fields) if fields else None
        if row is None:
            row = repos.get_cluster_by_number(session, pair_id, number)
        assert row is not None  # looked up above, inside the same session
        view = _cluster_view(row)
        rows = repos.list_clusters(session, pair_id)

    path = _sidecar_path(bundle, pair)
    if path.is_file():
        compare_dxf_mod.apply_decisions(
            path,
            {int(item.number): (item.decision, item.user_label, item.note) for item in rows},
        )
    return view


def _cluster_view(row: Any) -> ClusterView:
    return ClusterView.model_validate(
        {
            "id": f"c{row.number}",
            "number": row.number,
            "signature": row.signature,
            "bbox": list(row.bbox or []),
            "kind": row.kind,
            "label": row.label,
            "user_label": row.user_label,
            "decision": row.decision,
            "note": row.note,
            "change_ids": [f"ch{seq}" for seq in (row.change_seqs or [])],
            "cloud": dict(row.cloud or {}),
            "badge": dict(row.badge or {}),
        }
    )


@router.get("/pairs/{pair_id}/compare-dxf")
async def get_compare_dxf(pair_id: str, request: Request) -> Response:
    """The compare DXF's bytes, with the file's sha256 as its ETag (contract §7).

    The viewer opens this with the same CAD host it opens any drawing with, and
    the ETag is what lets it keep a rendered sheet across a screen change: the
    comparison is deterministic, so identical bytes really do mean an identical
    drawing.
    """
    bundle, pair = _pair_or_404(request, pair_id)
    path = _compare_dxf_path(bundle, pair)
    if not path.is_file():
        raise HTTPException(
            status_code=409,
            detail=f"sheet_pair {pair_id} has not been compared yet ({pair.status})",
        )
    payload = path.read_bytes()
    etag = f'"{hashlib.sha256(payload).hexdigest()}"'
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers={"ETag": etag})
    return Response(
        content=payload,
        media_type=DXF_MEDIA_TYPE,
        headers={"ETag": etag, "Content-Disposition": f'inline; filename="{path.name}"'},
    )


__all__ = ["router", "run_comparison"]
