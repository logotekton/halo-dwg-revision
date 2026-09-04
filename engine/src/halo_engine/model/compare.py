"""Request and response bodies for ``/api/v1/compare/...`` (``docs/contracts/r1.md`` §7).

The *inputs* and the small 202 acknowledgements live here. Records the engine
hands back -- ``SheetFrame``, ``SheetPair``, ``Change``, ``Cluster``, ``Run``,
``CompareSetSummary`` -- are defined by the JSON schemas
(``packages/schema/src/compare/*.schema.json``), and the contract (§4) allows a
router to serve them either as the generated ``halo_schema.models.compare.*``
models or as "같은 필드의 자체 모델".

R1-04 had to take the second option: ``halo-schema`` (the generated package at
``packages/schema/gen/python``) is not among ``engine/pyproject.toml``'s
dependencies, and that file belongs to Fable rather than to a task
(``CLAUDE.md`` 디렉터리 소유권). :class:`SheetFrameView` and
:class:`SheetPairView` below are therefore hand-written mirrors, and
``engine/tests/api/test_compare_pairs.py`` reads the schema files themselves
and fails if the field sets ever diverge -- so the copy cannot drift silently
while the dependency is being sorted out (report: Shared-file patch).

Strict mypy applies to this package (``engine/pyproject.toml``).
"""

from __future__ import annotations

from typing import Any, Literal

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
    #: R1-03 addition (contract §7 lists the endpoint's baseline fields; this
    #: one is additive): ``{zwcad_version, elapsed_s, warnings[]}``,
    #: ``{fallback_reason}``, ``{cache_hit: true}`` or
    #: ``{same_converter_forced: true}`` depending on how the file's working
    #: DXF was produced. ``None`` for a DXF input that skipped conversion.
    converter_meta: dict[str, object] | None = None


FrameKind = Literal["titleblock", "unrecognized_file"]
"""``sheet_frame.kind``: a recognised title block, or a whole file that had none."""

PairStatus = Literal[
    "pending",
    "changed",
    "same",
    "added",
    "removed",
    "unpaired",
    "unrecognized",
    "converter_mismatch",
]
"""``sheet_pair.status`` (contract §3). Matching writes all but ``changed``."""

MatchMethod = Literal["number", "title", "position", "manual"]
"""How the two frames were paired (contract §3)."""


class SheetFrameView(BaseModel):
    """One 도곽, as ``GET /compare/sets/{id}/pairs`` embeds it.

    Field-for-field ``compare/sheet-frame.schema.json``. ``entity_handles`` is
    ``None`` in the pairs list -- the schema says the summary omits it, and a
    sheet's handle list is thousands of strings the list screen never reads.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    compare_set_id: str
    role: Literal["before", "after"]
    file_id: str
    kind: FrameKind
    titleblock_handle: str | None = None
    block_name: str | None = None
    bbox: list[float] = Field(min_length=4, max_length=4, description="[x0, y0, x1, y1] in mm.")
    sheet_no: str | None = None
    sheet_title: str | None = None
    scale_text: str | None = None
    scale_denominator: int | None = Field(default=None, ge=1)
    date_text: str | None = None
    norm_key: str
    sort_index: int = Field(ge=0)
    entity_handles: list[str] | None = None
    provenance: dict[str, Any]
    attributes: dict[str, Any] | None = None


ClusterKind = Literal[
    "added", "removed", "modified", "moved", "text", "dimension", "blockdef", "mixed"
]
"""``cluster.kind``: the members' one kind, or ``mixed`` (contract §3)."""

ClusterDecision = Literal["pending", "approved", "ignored"]


class CloudMarkView(BaseModel):
    """``cluster.cloud`` -- the revision cloud's polyline (``cluster.schema.json``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    handle: str | None = None
    points: list[list[float]] = Field(min_length=4)


class ClusterBadgeView(BaseModel):
    """``cluster.badge`` -- the numbered triangle (``cluster.schema.json``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    shape_handle: str | None = None
    text_handle: str | None = None
    center: list[float] = Field(min_length=2, max_length=2)


class ClusterView(BaseModel):
    """One cluster, as ``PATCH /compare/pairs/{id}/clusters/{number}`` returns it.

    Field-for-field ``compare/cluster.schema.json``, the same hand-written
    mirror R1-04 had to make for ``SheetFrameView`` and for the same reason
    (contract §4 allows "같은 필드의 자체 모델"); the drift test lives in
    ``engine/tests/api/test_compare_clusters.py``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=r"^c[1-9][0-9]*$")
    number: int = Field(ge=1)
    signature: str | None = Field(default=None, max_length=64)
    bbox: list[float] = Field(min_length=4, max_length=4)
    kind: ClusterKind
    label: str
    user_label: str | None = Field(default=None, max_length=512)
    decision: ClusterDecision
    note: str | None = Field(default=None, max_length=4096)
    change_ids: list[str] = Field(min_length=1)
    cloud: CloudMarkView
    badge: ClusterBadgeView


class SheetPairView(BaseModel):
    """One 도곽 짝 with both frame summaries (``compare/sheet-pair.schema.json``)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    compare_set_id: str
    before_frame_id: str | None = None
    after_frame_id: str | None = None
    status: PairStatus
    match_method: MatchMethod | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    sort_key: str
    change_count: int = Field(ge=0)
    minor_count: int = Field(ge=0)
    cluster_count: int = Field(ge=0)
    compare_dxf_path: str | None = None
    clusters_json_path: str | None = None
    warnings: list[str] | None = None
    before_frame: SheetFrameView | None = None
    after_frame: SheetFrameView | None = None


__all__ = [
    "RUN_DATE_PATTERN",
    "ClusterBadgeView",
    "ClusterDecision",
    "ClusterDecisionRequest",
    "ClusterKind",
    "ClusterView",
    "CloudMarkView",
    "CompareFileEntry",
    "CompareRunRequest",
    "CompareSetCreateRequest",
    "CompareSetCreateResponse",
    "ExportAcceptedResponse",
    "ExportRequest",
    "FrameKind",
    "JobAcceptedResponse",
    "ManualPairRequest",
    "MatchMethod",
    "PairStatus",
    "SheetFrameView",
    "SheetPairView",
]
