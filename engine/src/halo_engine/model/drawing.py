"""Drawing-set / drawing-file / job resource models (``docs/contracts/wave-3.md``).

``DrawingFile.import_status`` walks a fixed pipeline (``ingest/pipeline.py``):
``PENDING -> COPYING -> (CONVERTING) -> BUILDING_WORKING_DXF -> CROSSCHECKING
-> DONE``, or ``FAILED`` / ``NEEDS_MANUAL_CONVERSION`` when a step cannot
complete -- ADR-0002's 2026-09-02 amendment makes the crosscheck gate a
blocking failure, not a warning, for DWG conversions.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class DrawingFormat(StrEnum):
    DWG = "DWG"
    DXF = "DXF"


class ImportStatus(StrEnum):
    """One file's progress through ``ingest/pipeline.py``."""

    PENDING = "PENDING"
    COPYING = "COPYING"
    CONVERTING = "CONVERTING"
    BUILDING_WORKING_DXF = "BUILDING_WORKING_DXF"
    CROSSCHECKING = "CROSSCHECKING"
    DONE = "DONE"
    FAILED = "FAILED"
    NEEDS_MANUAL_CONVERSION = "NEEDS_MANUAL_CONVERSION"
    #: W3-06 addendum 3 / G1 답변: matched ``import.ignore_patterns``
    #: (default ``*_recover.dwg``, ``*.bak``) -- copied nowhere, listed as
    #: "제외됨(복구 파일)" instead of imported.
    EXCLUDED = "EXCLUDED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


#: ``docs/contracts/wave-3.md``: ``POST /files/{id}/converted``'s ``converter`` field.
ConverterName = Literal["mlightcad-dxfout", "acad-ts"]


class DrawingSetCreateRequest(BaseModel):
    """``POST /projects/{id}/drawing-sets`` body."""

    model_config = ConfigDict(extra="forbid")

    files: list[str] = Field(
        min_length=1, description="Absolute source paths to import. Never written to."
    )
    search_paths: list[str] = Field(
        default_factory=list, description="Extra directories to search for XREFs."
    )
    converter_fallback: Literal["acad-ts"] | None = Field(
        default=None,
        description=(
            "When set and no desktop is connected over WS for a DWG file, the "
            "engine runs the acad-ts CLI itself as a subprocess instead of "
            "waiting on `convert.request`/`converted` (brief W3-03: "
            "`--converter-fallback acad-ts`). Overrides the server's own "
            "`--converter-fallback` default for this import only."
        ),
    )


class DrawingSetCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    drawing_set_id: str


class DrawingFileSummary(BaseModel):
    """One row of ``GET /drawing-sets/{id}/files``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    original_name: str
    format: DrawingFormat
    dwg_version: str | None = None
    entity_count: int | None = None
    codepage_effective: str | None = None
    import_status: ImportStatus
    error_message: str | None = None
    working_dxf_path: str | None = None
    parser_crosscheck: dict[str, Any] | None = None


class XrefMeta(BaseModel):
    """One entry of ``ConvertedRequest.xrefs`` -- an XREF block's declared path,
    verbatim (Windows backslashes and all; the engine normalises it)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    block_name: str
    path: str


class StyleMeta(BaseModel):
    """One entry of ``ConvertedRequest.styles`` -- a STYLE table record, as read
    by a second parser pass (``acad-bridge info --xrefs``) that still has it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    font: str
    bigfont: str
    typeface: str | None = None


class ConvertedRequest(BaseModel):
    """``POST /files/{id}/converted`` body -- the desktop's DWG->DXF conversion result.

    ``xrefs``/``styles`` (``docs/contracts/wave-3.md`` "계약 갱신", W3-06
    addendum 2): ``dxfOut()``-produced DXF loses XREF path strings and STYLE
    XDATA typeface names entirely (W3-09 실측 §3, 0/133 and 0/838), so the
    desktop reads them straight off the source DWG with acad-ts (a second,
    cheap pass -- ADR-0002 already keeps acad-ts around as the DWG-read
    fallback/third parser) and sends them alongside the converted DXF path
    instead of expecting the engine to recover them from the DXF itself.
    Both default to empty: the acad-ts *fallback* converter path
    (``ingest/pipeline.py``) does not go through this endpoint at all -- its
    own DXF output keeps XREF paths natively (W3-09 §3: 133/133), so there
    is nothing to backfill.
    """

    model_config = ConfigDict(extra="forbid")

    dxf_path: str = Field(description="Absolute path to the converted DXF, written by the desktop.")
    entity_count: int = Field(
        ge=0, description="Converter-reported entity count (crosscheck gate)."
    )
    converter: ConverterName
    warnings: list[str] = Field(default_factory=list)
    xrefs: list[XrefMeta] = Field(default_factory=list)
    styles: list[StyleMeta] = Field(default_factory=list)


class ConvertedAck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    accepted: bool
    file_id: str


class JobSummary(BaseModel):
    """``GET /jobs/{id}`` response."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    status: JobStatus
    progress: float = Field(ge=0.0, le=1.0)
    message: str | None = None
    drawing_set_id: str | None = None
    created_at: datetime
    updated_at: datetime
    error: str | None = None


__all__ = [
    "ConverterName",
    "ConvertedAck",
    "ConvertedRequest",
    "DrawingFileSummary",
    "DrawingFormat",
    "DrawingSetCreateRequest",
    "DrawingSetCreateResponse",
    "ImportStatus",
    "JobStatus",
    "JobSummary",
]
