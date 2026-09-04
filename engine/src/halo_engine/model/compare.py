"""Request and acknowledgement bodies for ``/api/v1/compare/...`` (``docs/contracts/r1.md`` §7).

Only the *inputs* and the small 202 acknowledgements live here. Everything the
engine hands back as a record -- ``SheetFrame``, ``SheetPair``, ``Change``,
``Cluster``, ``Run``, ``CompareSetSummary`` -- is generated from the JSON
schemas instead (``halo_schema.models.compare.*``), because the viewer has to
read exactly the same shape and one hand-written copy per language is how the
two drift apart (``packages/schema/README.md``).

Strict mypy applies to this package (``engine/pyproject.toml``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RUN_DATE_PATTERN = r"^[0-9]{4}-(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$"
"""`YYYY-MM-DD`. The engine never derives this from the clock (contract §11)."""


class CompareSetCreateRequest(BaseModel):
    """``POST /compare/sets`` body.

    ``project_dir`` is optional because the engine can derive it: the common
    parent of the two set folders, or the after folder's parent when they are
    not siblings (contract §1). The renderer sends it when the user picked the
    project folder explicitly.
    """

    model_config = ConfigDict(extra="forbid")

    before_dir: str = Field(min_length=1, description="Absolute path of the 변경 전 set folder.")
    after_dir: str = Field(min_length=1, description="Absolute path of the 변경 후 set folder.")
    project_dir: str | None = Field(
        default=None,
        description="Absolute path of the project folder; derived from the two set "
        "folders when omitted.",
    )
    run_date: str = Field(
        pattern=RUN_DATE_PATTERN,
        description="Export date the user entered on screen A. Fixes the revision layer name.",
    )
    options: dict[str, object] = Field(
        default_factory=dict,
        description="Per-run overrides of `compare.yaml`, kept as `compare_set.options`.",
    )


class CompareSetCreateResponse(BaseModel):
    """``POST /compare/sets`` 202 body: the ids the renderer polls with."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    compare_set_id: str
    project_id: str
    job_id: str


class JobAcceptedResponse(BaseModel):
    """202 body of the jobs that carry no new id of their own (frames, run)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str


class ManualPairRequest(BaseModel):
    """``POST /compare/sets/{id}/pairs/manual`` body: two frames the user paired by hand."""

    model_config = ConfigDict(extra="forbid")

    before_frame_id: str = Field(min_length=1)
    after_frame_id: str = Field(min_length=1)


class CompareRunRequest(BaseModel):
    """``POST /compare/sets/{id}/run`` body.

    ``pair_ids`` omitted means every pair that is ready to compare; a list
    re-compares just those, which is what the review screen's 다시 비교 does.
    """

    model_config = ConfigDict(extra="forbid")

    pair_ids: list[str] | None = Field(default=None)


class ClusterDecisionRequest(BaseModel):
    """``PATCH /compare/pairs/{pair_id}/clusters/{number}`` body.

    All three fields are optional and nullable, and the two meanings are
    different: a key that is absent leaves the column alone, a key that is
    ``null`` clears it. The router must therefore pass
    ``model_dump(exclude_unset=True)`` to ``repos.update_cluster`` rather than
    the whole model, or clearing a note would be indistinguishable from not
    mentioning it.
    """

    model_config = ConfigDict(extra="forbid")

    decision: Literal["pending", "approved", "ignored"] | None = Field(default=None)
    user_label: str | None = Field(default=None, max_length=512)
    note: str | None = Field(default=None, max_length=4096)


class ExportRequest(BaseModel):
    """``POST /compare/sets/{id}/export`` body.

    ``scope`` has one value in R1: exporting a chosen subset of sheets is a
    week-2 feature (CLAUDE.md rule 10). ``method`` defaults to `auto`, which
    tries ZWCAD, then acad-ts, then writes a DXF.
    """

    model_config = ConfigDict(extra="forbid")

    run_date: str = Field(pattern=RUN_DATE_PATTERN)
    scope: Literal["all"] = Field(default="all")
    method: Literal["auto", "zwcad", "acad-ts", "dxf-only"] = Field(default="auto")


class ExportAcceptedResponse(BaseModel):
    """``POST /compare/sets/{id}/export`` 202 body."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    run_id: str


class CompareFileEntry(BaseModel):
    """One row of ``GET /compare/sets/{id}/files``.

    A file that was excluded or that failed to convert still appears: the user
    has to be able to see which drawings did not make it into the comparison.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    role: Literal["before", "after"]
    original_name: str
    import_status: str
    converter: str | None = None
    excluded_reason: str | None = None
    error_message: str | None = None
    entity_count: int | None = None
    parser_crosscheck: dict[str, object] | None = None


__all__ = [
    "RUN_DATE_PATTERN",
    "ClusterDecisionRequest",
    "CompareFileEntry",
    "CompareRunRequest",
    "CompareSetCreateRequest",
    "CompareSetCreateResponse",
    "ExportAcceptedResponse",
    "ExportRequest",
    "JobAcceptedResponse",
    "ManualPairRequest",
]
