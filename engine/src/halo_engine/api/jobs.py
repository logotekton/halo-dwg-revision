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
from halo_engine.config import Settings
from halo_engine.db import repos
from halo_engine.db.ids import new_ulid
from halo_engine.ingest import pipeline
from halo_engine.model.drawing import DrawingFormat, ImportStatus, JobStatus, JobSummary

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
    file_id: str,
    source_path: Path,
    extra_search_paths: list[Path],
    converter_fallback: str | None,
) -> None:
    def update(**fields: Any) -> None:
        with bundle.session_factory() as session:
            repos.update_drawing_file(session, file_id, **fields)

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

    if copy_result.format is DrawingFormat.DXF:
        try:
            working = await loop.run_in_executor(
                executor,
                pipeline.build_working_dxf_step,
                str(source_path),
                str(bundle.layout.cache_dxf_dir),
                [str(p) for p in search_paths],
            )
        except Exception as exc:
            logger.warning("build_working_dxf failed for %s: %s", source_path, exc)
            update(import_status=ImportStatus.FAILED.value, error_message=str(exc))
            return
        _finalize_success(
            bundle=bundle, file_id=file_id, working=working, converter=None, dwg_version=None
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
        acad_bridge_bin = _resolve_acad_bridge_bin(settings)
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
    """The whole job: one entry in ``files`` at a time, cooperative-cancel between entries."""
    jobs = get_job_manager(app)
    connections = get_connection_manager(app)
    settings: Settings = app.state.settings
    loop = asyncio.get_running_loop()
    executor = jobs.executor

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
                    file_id=file_id,
                    source_path=Path(source_path_str),
                    extra_search_paths=[Path(p) for p in search_paths],
                    converter_fallback=converter_fallback,
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
