"""``CrosscheckReport`` — the persisted result of a parser crosscheck (ADR-0002 6).

Lives in :mod:`halo_engine.model` rather than :mod:`halo_engine.validate`
because the document is stored on ``drawing_file.parser_crosscheck`` and read
back by consumers that never run a comparison (brief W2-04, Constraints).
That also puts it under this package's ``strict`` mypy override
(``engine/pyproject.toml``).

The comparison itself is :mod:`halo_engine.validate.crosscheck`; the JSON
Schema published for other languages is
``engine/src/halo_engine/validate/crosscheck_report.schema.json``, generated
from these models (``CrosscheckReport.model_json_schema()``).

Vocabulary
----------

``Severity``
    Per-difference verdict. ``RED`` is a contract violation; ``AMBER`` is a
    difference a whitelist entry explains (the entry's ``reason`` is copied
    onto the difference so the report is readable on its own); ``GREEN`` never
    appears on a difference, only as a layer/report status.
``LayerResult``
    One ``(space, layer)`` bucket, present in at least one of the two
    documents. ``status`` is the worst severity among its ``differences``.
``CrosscheckReport.red_layers``
    Layer names with at least one ``RED`` difference, deduplicated and sorted.
    P4 evidence routing multiplies the confidence of any quantity whose
    evidence sits on one of these layers (brief W2-04, "신뢰도 연동 준비").
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """Traffic-light verdict of ADR-0002 6."""

    GREEN = "GREEN"
    AMBER = "AMBER"
    RED = "RED"


class DiffField(StrEnum):
    """The compared measure a :class:`Difference` is about.

    One member per row of ``docs/contracts/stats-definition.md`` "비교 임계",
    plus ``bucket`` for a ``(space, layer)`` bucket that exists on one side
    only (always ``RED``: a missing bucket is never a tolerance question).
    """

    BUCKET = "bucket"
    COUNT_BY_TYPE = "count_by_type"
    INSERT_BY_BLOCK = "insert_by_block"
    LENGTH_SUM_MM = "length_sum_mm"
    HATCH_AREA_SUM_MM2 = "hatch_area_sum_mm2"
    TEXT_COUNT = "text_count"
    TEXT_HASH = "text_hash"
    BBOX = "bbox"


class Difference(BaseModel):
    """One measured disagreement inside one bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    field: DiffField = Field(description="Which measure disagrees.")
    severity: Severity = Field(description="RED unless a whitelist entry explains it.")
    detail: str = Field(
        description=(
            "Human-readable cause, e.g. `count_by_type.LINE 24→22`. Rendered "
            "verbatim into the markdown report."
        )
    )
    reference_value: str | None = Field(
        default=None, description="The reference document's value, as text."
    )
    other_value: str | None = Field(
        default=None, description="The other document's value, as text."
    )
    relative_delta: float | None = Field(
        default=None,
        description="|a-b| / max(|a|,|b|) for the numeric measures; null otherwise.",
    )
    absolute_delta: float | None = Field(
        default=None,
        description="Largest absolute corner delta in mm for `bbox`; null otherwise.",
    )
    entity_types: list[str] = Field(
        default_factory=list,
        description=(
            "DXF record names present in this bucket (union of both sides, plus "
            "ATTRIB when the bucket's text_count exceeds its TEXT+MTEXT count). "
            "This is what a whitelist entry's `entity_type` matches against."
        ),
    )
    whitelist_id: str | None = Field(
        default=None,
        description="Id of the whitelist entry that downgraded this difference (e.g. `W03`).",
    )
    whitelist_reason: str | None = Field(
        default=None,
        description="Reason quoted from the whitelist entry that downgraded this to AMBER.",
    )


class LayerResult(BaseModel):
    """Verdict for one ``(space, layer)`` bucket."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    layer: str = Field(description="Layer name, or `(totals)` for the document totals row.")
    space: str = Field(description="`MODEL` or `PAPER:<layout>`, or `(all)` for the totals row.")
    status: Severity
    differences: list[Difference] = Field(default_factory=list)


class ProducerInfo(BaseModel):
    """``producer`` of the compared ``LayerStatsDocument`` (schema `$defs/producer`)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: str


class CrosscheckReport(BaseModel):
    """Full comparison of two ``LayerStatsDocument``s.

    Stored as-is on ``drawing_file.parser_crosscheck``.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(description="Version of this report shape, not of the inputs.")
    status: Severity = Field(description="Worst status across every layer and the totals row.")
    reference: ProducerInfo
    other: ProducerInfo
    file_sha256: str | None = Field(
        default=None,
        description="sha256 the two documents agree on, or null when they disagree.",
    )
    file_sha256_mismatch: bool = Field(
        default=False,
        description=(
            "True when the two documents were computed from different bytes "
            "(DWG vs. its DXF conversion). Never fatal on its own — the "
            "comparison still runs (brief W2-04, Defaults for ambiguity)."
        ),
    )
    layers: list[LayerResult] = Field(
        default_factory=list, description="One entry per bucket, ordered by (layer, space)."
    )
    totals: LayerResult = Field(description="The same comparison applied to `totals`.")
    red_layers: list[str] = Field(
        default_factory=list,
        description=(
            "Sorted, deduplicated layer names carrying at least one RED difference. "
            "Confidence routing input (ADR-0002 6: 적색 레이어에 근거를 둔 항목은 "
            "신뢰도를 감점한다)."
        ),
    )
    amber_layers: list[str] = Field(
        default_factory=list, description="Sorted layer names whose worst difference is AMBER."
    )
    counts: dict[str, int] = Field(
        default_factory=dict,
        description="Layer counts by status: keys `GREEN`, `AMBER`, `RED`.",
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-fatal notes, e.g. the sha256 mismatch."
    )
    whitelist_path: str | None = Field(
        default=None, description="Whitelist file used, if any (as given on the command line)."
    )


__all__ = [
    "CrosscheckReport",
    "DiffField",
    "Difference",
    "LayerResult",
    "ProducerInfo",
    "Severity",
]
