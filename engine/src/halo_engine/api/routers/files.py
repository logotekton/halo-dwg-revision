"""``GET /files/{id}/working-dxf`` (stream, ETag), ``GET /files/{id}/stats``,
``POST /files/{id}/converted`` (the desktop's DWG->DXF result), and
``POST /files/{id}/crosscheck`` (persists a comparison onto
``drawing_file.parser_crosscheck`` -- ``docs/contracts/wave-3.md``, ADR-0002
decision 6).

``POST /api/v1/files/crosscheck`` (no ``{id}``, stateless, W2-04) already
exists at ``api/routers/crosscheck.py`` and is unrelated -- this router adds
the *stateful*, file-scoped variant the contract's `parser_crosscheck?`
field and "뷰어 측 stats는 POST /files/{id}/crosscheck로 나중에 갱신" describe. The
two share the ``/api/v1/files`` prefix without colliding: ``/crosscheck`` has
two path segments, ``/{file_id}/crosscheck`` has three.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from halo_engine.api.routers.projects import get_open_bundle
from halo_engine.api.ws import get_connection_manager
from halo_engine.db import repos
from halo_engine.db.models import DrawingFileRow
from halo_engine.model.crosscheck import CrosscheckReport
from halo_engine.model.drawing import ConvertedAck, ConvertedRequest
from halo_engine.validate.crosscheck import (
    DEFAULT_WHITELIST,
    WhitelistError,
    compare,
    load_whitelist,
)

logger = logging.getLogger("halo_engine.api.files")

router = APIRouter()


def _get_file_row(request: Request, file_id: str) -> DrawingFileRow:
    bundle = get_open_bundle(request)
    with bundle.session_factory() as session:
        row = repos.get_drawing_file(session, file_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"file {file_id} not found")
        session.expunge(row)
        return row


def _stat_etag(stat_result: Any) -> str:
    # Same weak-validator recipe as Starlette's FileResponse.set_stat_headers,
    # duplicated so a conditional GET (If-None-Match) can be answered with a
    # bare 304 before a FileResponse (and its open() call) is even built.
    basis = f"{stat_result.st_mtime}-{stat_result.st_size}"
    return f'"{hashlib.md5(basis.encode(), usedforsecurity=False).hexdigest()}"'


@router.get("/{file_id}/working-dxf")
async def get_working_dxf(file_id: str, request: Request) -> Response:
    row = _get_file_row(request, file_id)
    if not row.working_dxf_path:
        raise HTTPException(
            status_code=409,
            detail=f"file {file_id} has no working DXF yet (import_status={row.import_status})",
        )
    path = Path(row.working_dxf_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail=f"working DXF missing on disk: {path}")

    stat_result = path.stat()
    etag = _stat_etag(stat_result)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    return FileResponse(
        path, media_type="application/dxf", filename=path.name, stat_result=stat_result
    )


@router.get("/{file_id}/stats")
async def get_file_stats(file_id: str, request: Request) -> dict[str, Any]:
    row = _get_file_row(request, file_id)
    if not row.stats_json_path:
        raise HTTPException(
            status_code=409,
            detail=f"file {file_id} has no stats yet (import_status={row.import_status})",
        )
    path = Path(row.stats_json_path)
    if not path.is_file():
        raise HTTPException(status_code=410, detail=f"stats missing on disk: {path}")
    return dict(json.loads(path.read_text(encoding="utf-8")))


@router.post("/{file_id}/converted", response_model=ConvertedAck)
async def post_converted(file_id: str, body: ConvertedRequest, request: Request) -> ConvertedAck:
    """The desktop's answer to a ``convert.request`` WS event (``docs/PLAN.md`` §3.6)."""
    _get_file_row(request, file_id)  # 404s if the file isn't in the open project
    manager = get_connection_manager(request.app)
    accepted = manager.resolve_conversion(file_id, body.model_dump())
    if not accepted:
        logger.warning(
            "POST /files/%s/converted: nothing was waiting on it (late or stale?)", file_id
        )
    return ConvertedAck(accepted=accepted, file_id=file_id)


class CrosscheckPersistRequest(BaseModel):
    """``POST /files/{id}/crosscheck`` body: the viewer's own ``LayerStatsDocument``."""

    model_config = ConfigDict(extra="forbid")

    other: dict[str, Any] = Field(
        description="LayerStatsDocument computed client-side by CadHost's statsByLayer()."
    )
    whitelist: str | None = Field(
        default=None,
        description='Whitelist YAML path. Omit for the shipped default; pass "" for none.',
    )


@router.post("/{file_id}/crosscheck", response_model=CrosscheckReport)
async def post_file_crosscheck(
    file_id: str, body: CrosscheckPersistRequest, request: Request
) -> CrosscheckReport:
    """Compare the viewer's stats against this file's engine-computed reference and persist it.

    ADR-0002 decision 6: "임포트 후 뷰어의 statsByLayer()와 엔진의 stats.py를
    비교해 레이어별 녹/황/적을 표시한다" -- the comparison itself is
    ``validate.crosscheck.compare()`` (W2-04, untouched here); this endpoint
    is what makes it file-scoped and durable on ``drawing_file.parser_crosscheck``.
    """
    row = _get_file_row(request, file_id)
    if not row.stats_json_path:
        raise HTTPException(
            status_code=409,
            detail=f"file {file_id} has no engine stats yet (import_status={row.import_status})",
        )
    reference = json.loads(Path(row.stats_json_path).read_text(encoding="utf-8"))

    if "buckets" not in body.other or "totals" not in body.other:
        raise HTTPException(
            status_code=422, detail="`other` is not a LayerStatsDocument (missing buckets/totals)"
        )

    if body.whitelist == "":
        whitelist_path: Path | None = None
    elif body.whitelist is None:
        whitelist_path = DEFAULT_WHITELIST
    else:
        whitelist_path = Path(body.whitelist)
        if not whitelist_path.is_file():
            raise HTTPException(status_code=422, detail=f"whitelist not found: {body.whitelist}")

    try:
        entries = load_whitelist(whitelist_path)
    except WhitelistError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    report = compare(
        reference,
        body.other,
        whitelist=entries,
        whitelist_path=None if whitelist_path is None else str(whitelist_path),
    )

    bundle = get_open_bundle(request)
    with bundle.session_factory() as session:
        repos.update_drawing_file(
            session, file_id, parser_crosscheck=report.model_dump(mode="json")
        )

    return report


__all__ = ["router"]
