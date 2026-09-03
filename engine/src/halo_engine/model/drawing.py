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


class ConvertedRequest(BaseModel):
    """``POST /files/{id}/converted`` body -- the desktop's DWG->DXF conversion result."""

    model_config = ConfigDict(extra="forbid")

    dxf_path: str = Field(description="Absolute path to the converted DXF, written by the desktop.")
    entity_count: int = Field(
        ge=0, description="Converter-reported entity count (crosscheck gate)."
    )
    converter: ConverterName
    warnings: list[str] = Field(default_factory=list)


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
