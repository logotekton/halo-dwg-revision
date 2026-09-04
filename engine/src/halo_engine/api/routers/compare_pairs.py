"""``/compare/sets/{id}/frames`` and ``/compare/.../pairs`` (contract §7, brief R1-04).

Screen B of the app is a list of sheets, and this router is what fills it: one
``POST`` turns two folders of working DXFs into 도곽 and 도곽 짝, one ``GET``
serves the list with the filters the screen offers, and two more endpoints let
the user correct a pairing the matcher got wrong.

The extraction runs as a ``compare.frames`` job (``api/jobs.py``: the same
202-then-poll envelope as ``compare.ingest``), because opening a 350,000-entity
DXF and assigning every entity to a sheet is tens of seconds of CPU per file.
That work goes to the job manager's spawning ``ProcessPoolExecutor``, so what
crosses the boundary is a path and a settings object in, and a list of
picklable :class:`~halo_engine.compare.frames.FrameRecord` out -- never an
ezdxf document.

Two decisions worth knowing about when reading the job body:

* **Manual pairs survive re-extraction.** ``repos.replace_frames`` deletes
  every pair of the compare set (it has to -- a pair is two frame ids), so the
  job snapshots the user's manual pairings by ``(file, position in file)``
  before it starts and re-applies them to the freshly extracted frames
  afterwards. Losing a user's hand-pairing because a file was re-converted
  would be the worst kind of silent data loss here.
* **One unreadable file costs one file.** ``extract_file_frames`` returns its
  error instead of raising, and the skipped files are listed in
  ``compare_set.stats`` so the summary can show them.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request, status

from halo_engine.api import jobs
from halo_engine.bundle.create import BundleHandle
from halo_engine.compare import frames as frames_mod
from halo_engine.compare import match as match_mod
from halo_engine.compare.config import (
    FramesConfig,
    load_compare_config,
    load_frames_config,
)
from halo_engine.compare.frames import FrameRecord
from halo_engine.db import repos
from halo_engine.db.ids import new_ulid
from halo_engine.db.models import CompareSetRow, DrawingFileRow, SheetFrameRow, SheetPairRow
from halo_engine.model.compare import (
    JobAcceptedResponse,
    ManualPairRequest,
    SheetFrameView,
    SheetPairView,
)
from halo_engine.model.drawing import ImportStatus

logger = logging.getLogger("halo_engine.api.compare_pairs")

router = APIRouter()

#: ``compare_set.status`` values a frame extraction may start from. Before
#: ``ingested`` there are no working DXFs to read; ``matched``/``compared``
#: re-run the extraction, which is what the user asking for it again means.
EXTRACTABLE_STATUSES = frozenset({"ingested", "matched", "compared"})

#: ``sheet_pair.status`` values a frame may be in and still be paired by hand.
#: Pairing two frames that are already matched to *other* sheets would silently
#: unmake those matches (contract §7).
MANUAL_PAIRABLE_STATUSES = frozenset(
    {match_mod.STATUS_REMOVED, match_mod.STATUS_ADDED, match_mod.STATUS_UNPAIRED}
)

#: ``GET .../pairs?sort=``. ``sheet_no`` is the sheet list's own order.
SortField = Literal["sheet_no", "status", "changes"]

# Module-level singletons because ruff (B008) refuses a call in a default, and
# because these three are the query contract of `GET .../pairs` in one place.
_STATUS_QUERY = Query(default=None, alias="status")
_Q_QUERY = Query(default=None)
_SORT_QUERY = Query(default="sheet_no")


# --------------------------------------------------------------------------- lookup


def _get_open_bundle_or_404(
    request: Request, compare_set_id: str
) -> tuple[BundleHandle, CompareSetRow]:
    """The open bundle and this compare set, or a 404.

    Same rule as ``api/routers/compare_sets.py``: the renderer only reaches
    these paths after ``POST /compare/sets`` opened the bundle in this process,
    so "no bundle" and "no such id" are the same answer to the caller.
    """
    bundle: BundleHandle | None = getattr(request.app.state, "bundle", None)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"compare_set {compare_set_id} not found")
    with bundle.session_factory() as session:
        row = repos.get_compare_set(session, compare_set_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"compare_set {compare_set_id} not found")
    return bundle, row


def _frames_by_id(bundle: BundleHandle, compare_set_id: str) -> dict[str, SheetFrameRow]:
    with bundle.session_factory() as session:
        return {row.id: row for row in repos.list_frames(session, compare_set_id)}


def _file_names(bundle: BundleHandle, compare_set: CompareSetRow) -> dict[str, str]:
    with bundle.session_factory() as session:
        rows = [
            *repos.list_files_for_set(session, compare_set.before_set_id),
            *repos.list_files_for_set(session, compare_set.after_set_id),
        ]
    return {row.id: row.original_name for row in rows}


# --------------------------------------------------------------------------- the job


def _readable_files(rows: list[DrawingFileRow]) -> list[DrawingFileRow]:
    """Files that produced a working DXF, in the order they were planned.

    An ``is_xref`` row is skipped. The set ingest does not create any (only the
    plain drawing-set import does, ``api/jobs.py::_register_xref_results``), but
    if one ever reaches a compare set it must not be cut into sheets: an XREF
    target's content already appears, embedded, inside every host that
    references it, and counting it again would double those sheets.
    """
    return [
        row
        for row in rows
        if row.import_status == ImportStatus.DONE.value and row.working_dxf_path and not row.is_xref
    ]


async def _extract_side(
    *,
    loop: asyncio.AbstractEventLoop,
    executor: Any,
    jobs_manager: jobs.JobManager,
    job: jobs.JobRecord,
    reporter: jobs.ProgressReporter,
    role: str,
    rows: list[DrawingFileRow],
    frames_config: FramesConfig,
    progress: list[int],
    skipped: list[dict[str, str]],
) -> list[FrameRecord]:
    """Extract one side's frames, one file at a time.

    Sequential rather than fanned out over the pool: the job has to be
    cancellable between files (contract §6.2) and the frame order has to be the
    file order for the result to be deterministic, and the pool is two workers
    wide anyway.
    """
    extracted: list[FrameRecord] = []
    for row in rows:
        current = jobs_manager.get(job.id)
        if current is not None and current.cancel_requested:
            raise jobs.JobCancelled

        result = await loop.run_in_executor(
            executor,
            frames_mod.extract_file_frames,
            str(row.working_dxf_path),
            row.id,
            frames_config,
        )
        if result.error:
            logger.warning("frame extraction failed for %s: %s", row.original_name, result.error)
            skipped.append({"file": row.original_name, "role": role, "error": result.error})
        for frame in result.frames:
            frame.role = role
            frame.file_name = row.original_name
            frame.file_sha256 = row.sha256 or ""
            frame.converter = row.converter
            if frame.kind == frames_mod.KIND_UNRECOGNIZED:
                frame.norm_key = frames_mod.file_norm_key(row.original_name, frames_config)
            extracted.append(frame)

        progress[0] += 1
        await reporter(
            progress[0] / progress[1] if progress[1] else 1.0,
            f"{progress[0]}/{progress[1]}",
            stage="frames",
            extra={
                "role": role,
                "file": row.original_name,
                "frames": len(result.frames),
                "entity_count": result.entity_count,
                "assign_seconds": result.assign_seconds,
            },
        )
    return extracted


def _manual_snapshot(
    bundle: BundleHandle, compare_set_id: str
) -> list[tuple[tuple[str, int], tuple[str, int]]]:
    """The user's hand-made pairings as ``(file_id, sort_index)`` on both sides.

    Frame *ids* cannot be used: re-extraction issues new ones. The file row and
    the frame's position inside it both survive, because the frames job never
    touches ``drawing_file`` and the reading order of a file that did not
    change is the same order.
    """
    snapshot: list[tuple[tuple[str, int], tuple[str, int]]] = []
    with bundle.session_factory() as session:
        frames = {row.id: row for row in repos.list_frames(session, compare_set_id)}
        for pair in repos.list_pairs(session, compare_set_id):
            if pair.match_method != "manual":
                continue
            before = frames.get(pair.before_frame_id or "")
            after = frames.get(pair.after_frame_id or "")
            if before is None or after is None:
                continue
            snapshot.append(
                (
                    (before.file_id, before.sort_index),
                    (after.file_id, after.sort_index),
                )
            )
    return snapshot


def _reapply_manual(
    pairs: list[match_mod.PairRecord],
    snapshot: list[tuple[tuple[str, int], tuple[str, int]]],
    before: list[FrameRecord],
    after: list[FrameRecord],
) -> list[match_mod.PairRecord]:
    """Put the snapshotted manual pairs back, dropping whatever claimed those frames."""
    if not snapshot:
        return pairs
    before_index = {(f.file_id, f.sort_index): i for i, f in enumerate(before)}
    after_index = {(f.file_id, f.sort_index): i for i, f in enumerate(after)}

    manual: list[match_mod.PairRecord] = []
    claimed_before: set[int] = set()
    claimed_after: set[int] = set()
    for before_key, after_key in snapshot:
        b_index = before_index.get(before_key)
        a_index = after_index.get(after_key)
        if b_index is None or a_index is None:
            continue
        manual.append(match_mod.manual_pair(b_index, a_index, before[b_index], after[a_index]))
        claimed_before.add(b_index)
        claimed_after.add(a_index)

    kept = [
        pair
        for pair in pairs
        if pair.before_index not in claimed_before and pair.after_index not in claimed_after
    ]
    merged = [*kept, *manual]

    # Dropping an automatic pair can orphan its *other* frame: if the matcher
    # paired B3 with A7 and the user's manual pair claims B3, A7 now belongs to
    # nothing. A sheet that is in no pair at all is invisible in the list, so
    # give it back the row it would have had.
    paired_before = {p.before_index for p in merged if p.before_index is not None}
    paired_after = {p.after_index for p in merged if p.after_index is not None}
    for index in range(len(before)):
        if index not in paired_before:
            merged.append(
                match_mod.PairRecord(
                    before_index=index,
                    status=match_mod.STATUS_REMOVED,
                    sort_key=match_mod.natural_sort_key(before[index].norm_key),
                )
            )
    for index in range(len(after)):
        if index not in paired_after:
            merged.append(
                match_mod.PairRecord(
                    after_index=index,
                    status=match_mod.STATUS_ADDED,
                    sort_key=match_mod.natural_sort_key(after[index].norm_key),
                )
            )

    merged.sort(
        key=lambda pair: (
            pair.sort_key,
            pair.before_index if pair.before_index is not None else -1,
            pair.after_index if pair.after_index is not None else -1,
        )
    )
    return merged


def _pair_counts(pairs: list[match_mod.PairRecord]) -> dict[str, int]:
    counts = {
        "changed": 0,
        "same": 0,
        "added": 0,
        "removed": 0,
        "unpaired": 0,
        "unrecognized": 0,
        "converter_mismatch": 0,
        "pending": 0,
    }
    for pair in pairs:
        if pair.status in counts:
            counts[pair.status] += 1
    return counts


async def run_frame_extraction(
    app: Any, *, job: jobs.JobRecord, bundle: BundleHandle, compare_set_id: str
) -> None:
    """The ``compare.frames`` job body: extract 도곽, match them, store both."""

    async def _work(reporter: jobs.ProgressReporter) -> None:
        await _do_frames(
            app, job=job, bundle=bundle, compare_set_id=compare_set_id, reporter=reporter
        )

    await jobs.run_job(app, job, _work)


async def _do_frames(
    app: Any,
    *,
    job: jobs.JobRecord,
    bundle: BundleHandle,
    compare_set_id: str,
    reporter: jobs.ProgressReporter,
) -> None:
    loop = asyncio.get_running_loop()
    jobs_manager = jobs.get_job_manager(app)
    executor = jobs_manager.executor

    frames_config = load_frames_config(bundle)
    compare_config = load_compare_config(bundle)

    with bundle.session_factory() as session:
        compare_set = repos.get_compare_set(session, compare_set_id)
        if compare_set is None:
            raise KeyError(f"compare_set {compare_set_id!r} not found")
        before_rows = _readable_files(repos.list_files_for_set(session, compare_set.before_set_id))
        after_rows = _readable_files(repos.list_files_for_set(session, compare_set.after_set_id))

    manual = _manual_snapshot(bundle, compare_set_id)

    with bundle.session_factory() as session:
        repos.update_compare_set(session, compare_set_id, status="extracting")

    skipped: list[dict[str, str]] = []
    progress = [0, len(before_rows) + len(after_rows)]

    async def _side(role: str, rows: list[DrawingFileRow]) -> list[FrameRecord]:
        return await _extract_side(
            loop=loop,
            executor=executor,
            jobs_manager=jobs_manager,
            job=job,
            reporter=reporter,
            role=role,
            rows=rows,
            frames_config=frames_config,
            progress=progress,
            skipped=skipped,
        )

    # Before side first, then after -- the same order the ingest job converts
    # in, so a progress bar and a log read in the same sequence.
    before_frames = await _side("before", before_rows)
    after_frames = await _side("after", after_rows)

    with bundle.session_factory() as session:
        before_ids = [
            row.id
            for row in repos.replace_frames(
                session, compare_set_id, "before", [f.to_row() for f in before_frames]
            )
        ]
        after_ids = [
            row.id
            for row in repos.replace_frames(
                session, compare_set_id, "after", [f.to_row() for f in after_frames]
            )
        ]

    pairs, stats = match_mod.match_frames_with_stats(
        before_frames, after_frames, compare_config, frames_config
    )
    pairs = _reapply_manual(pairs, manual, before_frames, after_frames)

    with bundle.session_factory() as session:
        repos.replace_pairs(
            session, compare_set_id, match_mod.pair_rows(pairs, before_ids, after_ids)
        )

    def _titleblocks(records: list[FrameRecord]) -> int:
        return sum(1 for f in records if f.kind == frames_mod.KIND_TITLEBLOCK)

    unrecognized = sum(
        1 for f in [*before_frames, *after_frames] if f.kind == frames_mod.KIND_UNRECOGNIZED
    )

    with bundle.session_factory() as session:
        row = repos.get_compare_set(session, compare_set_id)
        merged: dict[str, Any] = dict((row.stats if row is not None else None) or {})
        merged.update(
            {
                "last_job_id": job.id,
                # contract §7 CompareSetSummary.frames / .pairs
                "frames": {
                    "before": _titleblocks(before_frames),
                    "after": _titleblocks(after_frames),
                    "unrecognized_files": unrecognized,
                },
                "pairs": _pair_counts(pairs),
                "duplicate_sheet_no": stats.duplicate_sheet_no,
                "frames_skipped": skipped,
            }
        )
        repos.update_compare_set(session, compare_set_id, status="matched", stats=merged)


# --------------------------------------------------------------------------- endpoints


@router.post(
    "/sets/{compare_set_id}/frames",
    response_model=JobAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_frame_extraction(compare_set_id: str, request: Request) -> JobAcceptedResponse:
    """Start ``compare.frames``: 도곽 추출 + 짝짓기, ending in status ``matched``."""
    bundle, compare_set = _get_open_bundle_or_404(request, compare_set_id)
    if compare_set.status not in EXTRACTABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=(
                f"compare_set {compare_set_id} is {compare_set.status}; "
                f"frame extraction needs one of {sorted(EXTRACTABLE_STATUSES)}"
            ),
        )

    job_manager = jobs.get_job_manager(request.app)
    job = job_manager.create(compare_set_id=compare_set_id, kind="compare.frames")

    with bundle.session_factory() as session:
        row = repos.get_compare_set(session, compare_set_id)
        merged = dict((row.stats if row is not None else None) or {})
        merged["last_job_id"] = job.id
        repos.update_compare_set(session, compare_set_id, stats=merged)

    task = asyncio.create_task(
        run_frame_extraction(request.app, job=job, bundle=bundle, compare_set_id=compare_set_id)
    )
    job_manager.set_task(job.id, task)
    return JobAcceptedResponse(job_id=job.id)


def _frame_summary(row: SheetFrameRow | None, *, compare_set_id: str) -> SheetFrameView | None:
    """One frame as the pairs list embeds it.

    ``entity_handles`` is dropped -- the schema says so, and a sheet's handle
    list is thousands of strings the list screen never reads. The file *name*
    is not carried: it is not a ``SheetFrame`` field yet, and adding one is a
    ``packages/schema`` change (see the report's Shared-file patch). The
    ``q`` filter below resolves it server-side instead.
    """
    if row is None:
        return None
    return SheetFrameView.model_validate(
        {
            "id": row.id,
            "compare_set_id": compare_set_id,
            "role": row.role,
            "file_id": row.file_id,
            "kind": row.kind,
            "titleblock_handle": row.titleblock_handle,
            "block_name": row.block_name,
            "bbox": list(row.bbox or []),
            "sheet_no": row.sheet_no,
            "sheet_title": row.sheet_title,
            "scale_text": row.scale_text,
            "scale_denominator": row.scale_denominator,
            "date_text": row.date_text,
            "norm_key": row.norm_key,
            "sort_index": row.sort_index,
            "entity_handles": None,
            "provenance": row.provenance,
            "attributes": row.attributes or None,
        }
    )


def _pair_model(
    pair: SheetPairRow, *, compare_set_id: str, frames: dict[str, SheetFrameRow]
) -> SheetPairView:
    return SheetPairView.model_validate(
        {
            "id": pair.id,
            "compare_set_id": compare_set_id,
            "before_frame_id": pair.before_frame_id,
            "after_frame_id": pair.after_frame_id,
            "status": pair.status,
            "match_method": pair.match_method,
            "score": pair.score,
            "sort_key": pair.sort_key,
            "change_count": pair.change_count,
            "minor_count": pair.minor_count,
            "cluster_count": pair.cluster_count,
            "compare_dxf_path": pair.compare_dxf_path,
            "clusters_json_path": pair.clusters_json_path,
            "warnings": pair.warnings,
            "before_frame": _frame_summary(
                frames.get(pair.before_frame_id or ""), compare_set_id=compare_set_id
            ),
            "after_frame": _frame_summary(
                frames.get(pair.after_frame_id or ""), compare_set_id=compare_set_id
            ),
        }
    )


def _search_key(text: str, frames_config: FramesConfig) -> str:
    """What ``?q=`` and the values it is matched against are folded to.

    :func:`~halo_engine.compare.frames.normalize_key` plus dropping the hyphen
    itself, so that typing ``a103`` finds ``A-103``. Someone searching a sheet
    list types the number the fast way, not the way it is printed.
    """
    return frames_mod.normalize_key(text, frames_config).replace("-", "")


def _haystack(
    pair: SheetPairRow, frames: dict[str, SheetFrameRow], file_names: dict[str, str]
) -> list[str]:
    values: list[str] = []
    for frame_id in (pair.before_frame_id, pair.after_frame_id):
        frame = frames.get(frame_id or "")
        if frame is None:
            continue
        values += [frame.sheet_no or "", frame.sheet_title or "", file_names.get(frame.file_id, "")]
    return values


@router.get("/sets/{compare_set_id}/pairs", response_model=list[SheetPairView])
async def list_sheet_pairs(
    compare_set_id: str,
    request: Request,
    status_filter: str | None = _STATUS_QUERY,
    q: str | None = _Q_QUERY,
    sort: SortField = _SORT_QUERY,
) -> list[SheetPairView]:
    """The sheet list of screen B, with its three controls (contract §7).

    ``q`` matches a drawing number, a drawing name or a file name on either
    side, normalised the same way matching normalises them -- so searching
    ``a101`` finds ``A-101``.
    """
    bundle, compare_set = _get_open_bundle_or_404(request, compare_set_id)
    frames_config = load_frames_config(bundle)
    frames = _frames_by_id(bundle, compare_set_id)
    file_names = _file_names(bundle, compare_set)

    with bundle.session_factory() as session:
        rows = repos.list_pairs(session, compare_set_id, status=status_filter)

    if q:
        needle = _search_key(q, frames_config)
        if needle:
            rows = [
                row
                for row in rows
                if any(
                    needle in _search_key(value, frames_config)
                    for value in _haystack(row, frames, file_names)
                )
            ]

    if sort == "status":
        rows.sort(key=lambda row: (row.status, row.sort_key, row.id))
    elif sort == "changes":
        rows.sort(key=lambda row: (-row.change_count, row.sort_key, row.id))
    else:
        rows.sort(key=lambda row: (row.sort_key, row.id))

    return [_pair_model(row, compare_set_id=compare_set_id, frames=frames) for row in rows]


@router.post("/sets/{compare_set_id}/pairs/manual", response_model=SheetPairView)
async def create_manual_pair(
    compare_set_id: str, body: ManualPairRequest, request: Request
) -> SheetPairView:
    """Pair two frames by hand, replacing the two rows they were in."""
    bundle, compare_set = _get_open_bundle_or_404(request, compare_set_id)
    frames = _frames_by_id(bundle, compare_set_id)

    before = frames.get(body.before_frame_id)
    after = frames.get(body.after_frame_id)
    for frame_id, frame, expected_role in (
        (body.before_frame_id, before, "before"),
        (body.after_frame_id, after, "after"),
    ):
        if frame is None:
            raise HTTPException(
                status_code=404, detail=f"sheet_frame {frame_id} not found in this compare set"
            )
        if frame.role != expected_role:
            raise HTTPException(
                status_code=422,
                detail=f"sheet_frame {frame_id} is a {frame.role} frame, not {expected_role}",
            )

    with bundle.session_factory() as session:
        current = repos.list_pairs(session, compare_set_id)
        for frame_id in (body.before_frame_id, body.after_frame_id):
            owning = [
                pair for pair in current if frame_id in (pair.before_frame_id, pair.after_frame_id)
            ]
            if any(pair.status not in MANUAL_PAIRABLE_STATUSES for pair in owning):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"sheet_frame {frame_id} is already matched; only "
                        f"{sorted(MANUAL_PAIRABLE_STATUSES)} sheets can be paired by hand"
                    ),
                )

        pair = repos.create_manual_pair(
            session,
            compare_set_id=compare_set_id,
            before_frame_id=body.before_frame_id,
            after_frame_id=body.after_frame_id,
            sort_key=match_mod.natural_sort_key(
                (after.norm_key if after is not None else "")
                or (before.norm_key if before is not None else "")
            ),
        )
        pair_id = pair.id

    frames = _frames_by_id(bundle, compare_set_id)
    with bundle.session_factory() as session:
        row = repos.get_pair(session, pair_id)
    assert row is not None  # just created in this request
    return _pair_model(row, compare_set_id=compare_set_id, frames=frames)


@router.delete("/pairs/{pair_id}", status_code=status.HTTP_200_OK)
async def delete_manual_pair(pair_id: str, request: Request) -> dict[str, Any]:
    """Undo a hand-made pairing, restoring the ``removed``/``added`` rows it replaced.

    Only a ``manual`` pair can be deleted (``repos.delete_pair`` enforces it):
    deleting a matched pair would drop a sheet out of the comparison with
    nothing on screen to say so. The two frames go back to being an unmatched
    before sheet and an unmatched after sheet, which is what they were when the
    user reached for the manual pairing in the first place.
    """
    bundle: BundleHandle | None = getattr(request.app.state, "bundle", None)
    if bundle is None:
        raise HTTPException(status_code=404, detail=f"sheet_pair {pair_id} not found")

    with bundle.session_factory() as session:
        pair = repos.get_pair(session, pair_id)
        if pair is None:
            raise HTTPException(status_code=404, detail=f"sheet_pair {pair_id} not found")
        if pair.match_method != "manual":
            raise HTTPException(
                status_code=409,
                detail=f"sheet_pair {pair_id} was matched by {pair.match_method}, not by hand",
            )
        compare_set_id = pair.compare_set_id
        before_frame_id = pair.before_frame_id
        after_frame_id = pair.after_frame_id
        frames = {row.id: row for row in repos.list_frames(session, compare_set_id)}

        repos.delete_pair(session, pair_id, manual_only=True)

        # `repos` (R1-01) has no "create one unmatched pair" function -- the
        # matcher writes them all at once through `replace_pairs`, which would
        # throw away every other pair of this set. Insert the two restored rows
        # directly on the ORM instead, the same way `compare_sets.py` sets
        # `drawing_set.role` without a dedicated setter.
        restored: list[str] = []
        for frame_id, pair_status in (
            (before_frame_id, match_mod.STATUS_REMOVED),
            (after_frame_id, match_mod.STATUS_ADDED),
        ):
            if frame_id is None:
                continue
            frame = frames.get(frame_id)
            now = datetime.now(UTC).replace(tzinfo=None)
            row = SheetPairRow(
                id=new_ulid(),
                compare_set_id=compare_set_id,
                before_frame_id=frame_id if pair_status == match_mod.STATUS_REMOVED else None,
                after_frame_id=frame_id if pair_status == match_mod.STATUS_ADDED else None,
                status=pair_status,
                match_method=None,
                score=None,
                sort_key=match_mod.natural_sort_key(frame.norm_key if frame else ""),
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            restored.append(row.id)
        session.commit()

    return {"deleted": pair_id, "restored": restored}


__all__ = ["router", "run_frame_extraction"]
