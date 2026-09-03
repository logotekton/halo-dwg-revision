"""Job runner: in-memory job registry, the drawing-set import orchestrator, and
``GET /jobs/{id}`` / ``POST /jobs/{id}/cancel`` (``docs/PLAN.md`` §3.6, brief W3-03).

Job orchestration (looping over files, the WS ``convert.request`` ->
``converted`` wait, DB writes, progress broadcast) runs as an ``asyncio.Task``
on the server's own event loop -- it needs the live WS connections and the
bundle's SQLite session, neither of which cross a process boundary. The
actual ingest work -- hashing/copying, the acad-ts subprocess, and
``ingest/working_dxf.py``'s full working-DXF build -- runs in a 2-worker
``ProcessPoolExecutor(spawn)`` (brief W3-03, Constraints) via
``loop.run_in_executor``, which is where the wall-clock time actually goes.
"""

from __future__ import annotations

import asyncio
import logging
import multiprocessing
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Request

from halo_engine.api.ws import ConnectionManager, get_connection_manager
from halo_engine.bundle.create import BundleHandle
from halo_engine.bundle.originals import sha256_file
from halo_engine.config import Settings
from halo_engine.db import repos
from halo_engine.db.ids import new_ulid
from halo_engine.ingest import pipeline
from halo_engine.ingest.xref import is_ignored_name
from halo_engine.model.drawing import DrawingFormat, ImportStatus, JobStatus, JobSummary
from halo_engine.model.xref import XrefLinkStatus

logger = logging.getLogger("halo_engine.api.jobs")

router = APIRouter()

#: brief W3-03, Constraints: "converted 콜백을 최대 10분 대기".
CONVERT_TIMEOUT_S = 600.0
#: engine/src/halo_engine/api/jobs.py -> api -> halo_engine -> src -> engine -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_ACAD_BRIDGE_BIN = _REPO_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass
class JobRecord:
    id: str
    status: JobStatus
    progress: float
    message: str | None
    drawing_set_id: str | None
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    cancel_requested: bool = False
    task: asyncio.Task[None] | None = None

    def to_summary(self) -> JobSummary:
        return JobSummary(
            id=self.id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            drawing_set_id=self.drawing_set_id,
            created_at=self.created_at,
            updated_at=self.updated_at,
            error=self.error,
        )


class JobManager:
    """In-memory job registry plus the shared ``ProcessPoolExecutor``.

    In-memory is enough here: a job's outcome is durably recorded on
    ``drawing_file`` rows as it runs, so losing the registry on an engine
    restart loses only progress-polling for jobs that were in flight (which
    is the documented behaviour for an engine crash/restart, PLAN §3.5:
    "진행 중 잡 FAILED(engine_restart)").
    """

    def __init__(self, *, max_workers: int = 2) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._executor: Executor = ProcessPoolExecutor(
            max_workers=max_workers, mp_context=multiprocessing.get_context("spawn")
        )

    @property
    def executor(self) -> Executor:
        return self._executor

    def create(self, *, drawing_set_id: str | None) -> JobRecord:
        now = _now()
        job = JobRecord(
            id=new_ulid(),
            status=JobStatus.QUEUED,
            progress=0.0,
            message=None,
            drawing_set_id=drawing_set_id,
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: Any) -> JobRecord | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        for key, value in fields.items():
            setattr(job, key, value)
        job.updated_at = _now()
        return job

    def set_task(self, job_id: str, task: asyncio.Task[None]) -> None:
        """Keep a reference to the running job's ``asyncio.Task`` (asyncio GC gotcha)."""
        job = self._jobs.get(job_id)
        if job is not None:
            job.task = task

    def request_cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return False
        job.cancel_requested = True
        return True

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def get_job_manager(app: FastAPI) -> JobManager:
    manager = getattr(app.state, "job_manager", None)
    if manager is None:
        manager = JobManager()
        app.state.job_manager = manager
    return manager


def _resolve_acad_bridge_bin(settings: Settings) -> Path | None:
    candidate = settings.acad_bridge_bin or _DEFAULT_ACAD_BRIDGE_BIN
    return candidate if candidate.is_file() else None


@dataclass(frozen=True)
class _ConvertedInfo:
    dxf_path: str
    entity_count: int
    converter: str
    dwg_version: str | None = None
    codepage_declared: str | None = None


def _dedup_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            out.append(path)
    return out


async def _import_one_file(
    *,
    loop: asyncio.AbstractEventLoop,
    executor: Executor,
    connections: ConnectionManager,
    settings: Settings,
    bundle: BundleHandle,
    drawing_set_id: str,
    file_id: str,
    source_path: Path,
    extra_search_paths: list[Path],
    converter_fallback: str | None,
    ignore_patterns: list[str],
) -> None:
    def update(**fields: Any) -> None:
        with bundle.session_factory() as session:
            repos.update_drawing_file(session, file_id, **fields)

    # W3-06 addendum 3 / G1 답변: matched `import.ignore_patterns` (default
    # `*_recover.dwg`, `*.bak`) -- never copied, never converted, just
    # marked excluded so the file list can show why (drawing_sets.py's
    # `list_drawing_set_files` surfaces `error_message` as-is).
    if is_ignored_name(source_path.name, ignore_patterns):
        update(
            import_status=ImportStatus.EXCLUDED.value,
            error_message="제외됨(복구 파일)",
        )
        return

    update(import_status=ImportStatus.COPYING.value)

    copy_result = await loop.run_in_executor(
        executor, pipeline.copy_original_step, str(source_path), str(bundle.layout.root)
    )
    update(
        sha256=copy_result.sha256,
        format=copy_result.format.value,
        original_originals_path=copy_result.dest_path,
    )

    search_paths = _dedup_paths([source_path.parent, *extra_search_paths])
    acad_bridge_bin = _resolve_acad_bridge_bin(settings)

    if copy_result.format is DrawingFormat.DXF:
        try:
            working = await loop.run_in_executor(
                executor,
                pipeline.build_working_dxf_step,
                str(source_path),
                str(bundle.layout.cache_dxf_dir),
                [str(p) for p in search_paths],
                str(acad_bridge_bin) if acad_bridge_bin else None,
                ignore_patterns,
            )
        except Exception as exc:
            logger.warning("build_working_dxf failed for %s: %s", source_path, exc)
            update(import_status=ImportStatus.FAILED.value, error_message=str(exc))
            return
        _finalize_success(
            bundle=bundle, file_id=file_id, working=working, converter=None, dwg_version=None
        )
        _register_xref_results(
            bundle=bundle, drawing_set_id=drawing_set_id, host_file_id=file_id, working=working
        )
        return

    # DWG: needs a converter before working_dxf can run at all.
    update(import_status=ImportStatus.CONVERTING.value)
    out_path = bundle.layout.cache_dxf_dir / f"{copy_result.sha256}.converted.dxf"

    candidates: list[tuple[str, Callable[[], Awaitable[_ConvertedInfo]]]] = []
    if connections.has_clients():

        async def via_desktop() -> _ConvertedInfo:
            payload = await connections.request_conversion(
                file_id=file_id,
                dwg_path=str(source_path),
                out_path=str(out_path),
                timeout_s=CONVERT_TIMEOUT_S,
            )
            return _ConvertedInfo(
                dxf_path=str(payload["dxf_path"]),
                entity_count=int(payload["entity_count"]),
                converter=str(payload["converter"]),
            )

        candidates.append(("desktop", via_desktop))

    effective_fallback = converter_fallback or settings.converter_fallback
    if effective_fallback == "acad-ts":
        if acad_bridge_bin is not None:

            async def via_fallback() -> _ConvertedInfo:
                result = await loop.run_in_executor(
                    executor,
                    pipeline.run_acad_ts_fallback,
                    str(source_path),
                    str(out_path),
                    str(acad_bridge_bin),
                )
                return _ConvertedInfo(
                    dxf_path=result.dxf_path,
                    entity_count=result.entity_count,
                    converter=result.converter,
                    dwg_version=result.dwg_version,
                    codepage_declared=result.codepage_declared,
                )

            candidates.append(("acad-ts", via_fallback))

    if not candidates:
        update(
            import_status=ImportStatus.NEEDS_MANUAL_CONVERSION.value,
            error_message="no desktop connected and no converter_fallback configured",
        )
        return

    reasons: list[str] = []
    for label, candidate in candidates:
        try:
            converted = await candidate()
        except Exception as exc:  # noqa: BLE001 - a candidate failing just tries the next one
            reasons.append(f"{label}: {exc}")
            continue

        try:
            working = await loop.run_in_executor(
                executor,
                pipeline.build_working_dxf_step,
                converted.dxf_path,
                str(bundle.layout.cache_dxf_dir),
                [str(p) for p in search_paths],
                str(acad_bridge_bin) if acad_bridge_bin else None,
                ignore_patterns,
            )
        except Exception as exc:
            reasons.append(
                f"{converted.converter}: engine could not open the converted DXF ({exc})"
            )
            continue

        gate = pipeline.evaluate_conversion_gate(
            audit_error_count=working.audit_error_count,
            engine_entity_count=int(working.stats.get("totals", {}).get("entity_count", 0)),
            converter_entity_count=converted.entity_count,
        )
        if gate.passed:
            _finalize_success(
                bundle=bundle,
                file_id=file_id,
                working=working,
                converter=converted.converter,
                dwg_version=converted.dwg_version,
                codepage_declared_override=converted.codepage_declared,
            )
            _register_xref_results(
                bundle=bundle, drawing_set_id=drawing_set_id, host_file_id=file_id, working=working
            )
            return
        reasons.append(f"{converted.converter}: " + "; ".join(gate.reasons))

    update(
        import_status=ImportStatus.NEEDS_MANUAL_CONVERSION.value,
        error_message=" | ".join(reasons) or "conversion failed",
    )


def _finalize_success(
    *,
    bundle: BundleHandle,
    file_id: str,
    working: pipeline.WorkingDxfStepResult,
    converter: str | None,
    dwg_version: str | None,
    codepage_declared_override: str | None = None,
) -> None:
    totals = working.stats.get("totals", {})
    with bundle.session_factory() as session:
        repos.update_drawing_file(
            session,
            file_id,
            import_status=ImportStatus.DONE.value,
            error_message=None,
            working_dxf_path=working.working_dxf_path,
            stats_json_path=working.stats_json_path,
            codepage_declared=codepage_declared_override or working.codepage_declared,
            codepage_effective=working.codepage_effective,
            entity_count=int(totals.get("entity_count", 0)),
            converter=converter,
            dwg_version=dwg_version,
        )


def _register_xref_results(
    *,
    bundle: BundleHandle,
    drawing_set_id: str,
    host_file_id: str,
    working: pipeline.WorkingDxfStepResult,
) -> None:
    """Persists this build's XREF outcome (brief W3-06):

    - every definition (resolved or not) as one ``xref_link`` row, replacing
      whatever a previous import of this same host left behind, so the file
      panel's XREF tree (Goal: "호스트 -> 참조, 상태 아이콘") and the
      unresolved-XREF dialog read the *current* state, not a stale mix;
    - every XREF target that turned out to be a DWG and had to be converted
      (addendum 1) as its own ``drawing_file(is_xref=1)`` row, deduplicated
      by content hash within this drawing set -- the real set's 8 XREF
      target files are each referenced by dozens of hosts, and
      ``ingest/pipeline.py``'s ``make_dwg_xref_converter`` already dedupes
      the actual conversion work by the same sha256, so the DB row follows
      the same key instead of one row per host reference.
    """
    with bundle.session_factory() as session:
        links: list[dict[str, str | None]] = [
            {
                "block_name": r["block_name"],
                "declared_path": r["declared_path"],
                "resolved_path": r["resolved_path"],
                "status": XrefLinkStatus.RESOLVED.value,
            }
            for r in working.resolved_xrefs
        ]
        links += [
            {
                "block_name": u["block_name"],
                "declared_path": u["declared_path"],
                "resolved_path": None,
                "status": XrefLinkStatus.UNRESOLVED.value,
            }
            for u in working.unresolved_xrefs
        ]
        repos.replace_xref_links(session, host_file_id=host_file_id, links=links)

        for converted in working.converted_xref_dwgs:
            source_dwg = Path(converted["source_dwg"])
            if not source_dwg.is_file():
                continue  # defensive: cache could have been cleared mid-job
            xref_sha256 = sha256_file(source_dwg)
            if repos.get_drawing_file_by_sha256(
                session, drawing_set_id=drawing_set_id, sha256=xref_sha256
            ):
                continue
            xref_row = repos.create_drawing_file(
                session,
                drawing_set_id=drawing_set_id,
                original_path=str(source_dwg),
                original_name=source_dwg.name,
                sha256=xref_sha256,
                format=DrawingFormat.DWG.value,
                import_status=ImportStatus.DONE.value,
                is_xref=True,
            )
            repos.update_drawing_file(session, xref_row.id, working_dxf_path=converted["dxf_path"])


async def run_drawing_set_import(
    app: FastAPI,
    *,
    job_id: str,
    bundle: BundleHandle,
    drawing_set_id: str,
    files: list[tuple[str, str]],  # (drawing_file_id, absolute source path)
    search_paths: list[str],
    converter_fallback: str | None,
) -> None:
    """The whole job: one entry in ``files`` at a time, cooperative-cancel between entries.

    W3-06: the project's own persisted ``search_paths``/``ignore_patterns``
    (``PUT /projects/{id}/search-paths``, ``PUT .../import-settings``) are
    read once here and merged into every file's own -- so a folder a user
    already added stays in effect for every later import, not just the one
    request that added it, and a search-path-only re-import
    (``api/routers/xrefs.py``'s ``_start_reimport``) does not need to pass
    anything beyond the file itself.
    """
    jobs = get_job_manager(app)
    connections = get_connection_manager(app)
    settings: Settings = app.state.settings
    loop = asyncio.get_running_loop()
    executor = jobs.executor

    with bundle.session_factory() as session:
        project = repos.get_project(session, bundle.id)
        project_search_paths = list(project.search_paths) if project else []
        ignore_patterns = list(project.ignore_patterns) if project else []
    merged_search_paths = [*project_search_paths, *search_paths]

    jobs.update(job_id, status=JobStatus.RUNNING, message="importing")
    await connections.broadcast(
        {"type": "job.progress", "job_id": job_id, "progress": 0.0, "message": "importing"}
    )

    total = len(files)
    try:
        for index, (file_id, source_path_str) in enumerate(files):
            job = jobs.get(job_id)
            if job is not None and job.cancel_requested:
                jobs.update(job_id, status=JobStatus.CANCELLED, message="cancelled")
                await connections.broadcast(
                    {"type": "job.failed", "job_id": job_id, "reason": "cancelled"}
                )
                return

            try:
                await _import_one_file(
                    loop=loop,
                    executor=executor,
                    connections=connections,
                    settings=settings,
                    bundle=bundle,
                    drawing_set_id=drawing_set_id,
                    file_id=file_id,
                    source_path=Path(source_path_str),
                    extra_search_paths=[Path(p) for p in merged_search_paths],
                    converter_fallback=converter_fallback,
                    ignore_patterns=ignore_patterns,
                )
            except Exception:
                logger.exception("import failed for %s", source_path_str)
                with bundle.session_factory() as session:
                    repos.update_drawing_file(
                        session,
                        file_id,
                        import_status=ImportStatus.FAILED.value,
                        error_message="internal error -- see engine log",
                    )

            progress = (index + 1) / total if total else 1.0
            jobs.update(job_id, progress=progress, message=f"{index + 1}/{total}")
            await connections.broadcast(
                {
                    "type": "job.progress",
                    "job_id": job_id,
                    "progress": progress,
                    "message": f"{index + 1}/{total}",
                }
            )
    except Exception as exc:  # noqa: BLE001 - orchestration-level failure, not a per-file one
        logger.exception("drawing-set import job %s crashed", job_id)
        jobs.update(job_id, status=JobStatus.FAILED, error=str(exc), message="internal error")
        await connections.broadcast({"type": "job.failed", "job_id": job_id, "reason": str(exc)})
        return

    jobs.update(job_id, status=JobStatus.DONE, progress=1.0, message="done")
    await connections.broadcast(
        {"type": "job.done", "job_id": job_id, "drawing_set_id": drawing_set_id}
    )


@router.get("/{job_id}", response_model=JobSummary)
async def get_job(job_id: str, request: Request) -> JobSummary:
    manager = get_job_manager(request.app)
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return job.to_summary()


@router.post("/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> dict[str, bool]:
    manager = get_job_manager(request.app)
    accepted = manager.request_cancel(job_id)
    if manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail=f"job {job_id} not found")
    return {"accepted": accepted}


__all__ = [
    "CONVERT_TIMEOUT_S",
    "JobManager",
    "JobRecord",
    "get_job_manager",
    "router",
    "run_drawing_set_import",
]
