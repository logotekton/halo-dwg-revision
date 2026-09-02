"""``POST /api/v1/files/crosscheck`` — compare two ``LayerStatsDocument``s.

The viewer computes its half with ``@halo-cad/cad-core``'s ``statsByLayer``
right after an import and posts both documents here; the engine answers with
the :class:`~halo_engine.model.crosscheck.CrosscheckReport` that gets stored on
``drawing_file.parser_crosscheck`` and drives the layer traffic lights
(ADR-0002 decision 6). The W3 UI panel consumes exactly this response.

Bearer token required — the router is mounted behind
:func:`halo_engine.api.main.create_app`'s auth middleware and this path is not
in ``_PUBLIC_PATHS``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from halo_engine.model.crosscheck import CrosscheckReport
from halo_engine.validate.crosscheck import (
    DEFAULT_WHITELIST,
    WhitelistError,
    compare,
    load_whitelist,
)

logger = logging.getLogger("halo_engine.api.crosscheck")

router = APIRouter()


class CrosscheckRequest(BaseModel):
    """Two inline ``LayerStatsDocument``s plus an optional whitelist path.

    The documents are passed through as plain mappings rather than re-modelled
    here: ``packages/schema`` owns the ``LayerStatsDocument`` shape, the
    comparer only reads the seven contract measures, and an unknown extra key
    must not turn a crosscheck into a 422.
    """

    model_config = ConfigDict(extra="forbid")

    reference: dict[str, Any] = Field(description="LayerStatsDocument taken as the reference.")
    other: dict[str, Any] = Field(description="LayerStatsDocument compared against it.")
    whitelist: str | None = Field(
        default=None,
        description=(
            "Path to a known-parser-gap whitelist YAML. Omit for the shipped "
            '`halo_engine/validate/whitelist.yaml`; pass `""` to compare with no whitelist.'
        ),
    )


@router.post("/crosscheck", response_model=CrosscheckReport)
async def crosscheck(request: CrosscheckRequest) -> CrosscheckReport:
    """Compare the two documents and return the report."""
    for name, document in (("reference", request.reference), ("other", request.other)):
        if "buckets" not in document or "totals" not in document:
            raise HTTPException(
                status_code=422,
                detail=f"{name} is not a LayerStatsDocument (missing `buckets`/`totals`)",
            )

    if request.whitelist == "":
        whitelist_path: Path | None = None
    elif request.whitelist is None:
        whitelist_path = DEFAULT_WHITELIST
    else:
        whitelist_path = Path(request.whitelist)
        if not whitelist_path.is_file():
            raise HTTPException(status_code=422, detail=f"whitelist not found: {request.whitelist}")

    try:
        entries = load_whitelist(whitelist_path)
    except WhitelistError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    report = compare(
        request.reference,
        request.other,
        whitelist=entries,
        whitelist_path=None if whitelist_path is None else str(whitelist_path),
    )
    logger.info(
        "crosscheck %s vs %s -> %s (%d red layers)",
        report.reference.name,
        report.other.name,
        report.status.value,
        len(report.red_layers),
    )
    return report
