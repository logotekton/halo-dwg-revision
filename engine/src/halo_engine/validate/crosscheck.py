"""Parser crosscheck: compare two ``LayerStatsDocument``s bucket by bucket.

ADR-0002 decision 6 ("임포트 후 뷰어의 statsByLayer()와 엔진의 stats.py를 비교해
레이어별 녹/황/적을 표시한다"), brief W2-04, thresholds verbatim from
``docs/contracts/stats-definition.md`` "비교 임계":

======================  =====================================================
measure                 rule
======================  =====================================================
``count_by_type``       exact, per type
``insert_by_block``     exact, per block name
``text_count``          exact
``text_hash``           exact
``length_sum_mm``       relative delta <= 0.1 %
``hatch_area_sum_mm2``  relative delta <= 0.5 %
``bbox``                every corner within 1 mm; present on both sides
======================  =====================================================

Buckets are matched on ``(space, layer)``; a bucket present on one side only
is ``RED`` and is never whitelistable.

Whitelist
---------

``whitelist.yaml`` downgrades *known* parser gaps from RED to AMBER, quoting
the entry's ``reason`` into the report. Two guards keep it honest:

* an entry without a non-empty ``reason`` is a load error (brief: "사유 없는
  항목은 로드 시 오류");
* count differences can never be downgraded (brief: "**카운트 격차는
  화이트리스트 금지**"). :data:`NEVER_WHITELISTABLE` holds the fields where a
  difference means one parser saw more or fewer entities than the other;
  ``insert_by_block`` is whitelistable only while both sides agree on the
  *total* number of INSERTs, i.e. only a block-name resolution gap, never a
  lost INSERT (see :func:`_insert_totals_agree`).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from halo_engine.model.crosscheck import (
    CrosscheckReport,
    Difference,
    DiffField,
    LayerResult,
    ProducerInfo,
    Severity,
)

#: Version of the report shape (``CrosscheckReport.schema_version``).
REPORT_SCHEMA_VERSION = "0.1"

#: Relative tolerance for ``length_sum_mm`` (contract: ±0.1 %).
LENGTH_TOLERANCE = 0.001
#: Relative tolerance for ``hatch_area_sum_mm2`` (contract: ±0.5 %).
HATCH_AREA_TOLERANCE = 0.005
#: Absolute tolerance for every ``bbox`` corner, in mm (contract: ±1 mm).
BBOX_TOLERANCE_MM = 1.0

#: Fields a whitelist entry may never downgrade: a difference here means the
#: two parsers disagree about how many entities exist.
NEVER_WHITELISTABLE = frozenset({DiffField.BUCKET, DiffField.COUNT_BY_TYPE, DiffField.TEXT_COUNT})

#: Shipped whitelist of known parser gaps.
DEFAULT_WHITELIST = Path(__file__).with_name("whitelist.yaml")

_TOTALS_LAYER = "(totals)"
_TOTALS_SPACE = "(all)"


class WhitelistError(ValueError):
    """A malformed whitelist file — raised at load time, never silently ignored."""


@dataclass(frozen=True)
class WhitelistEntry:
    """One ``{producer_pair, entity_type | field, reason}`` record.

    ``producers`` is an unordered pair; ``"*"`` matches any producer name.
    ``field`` and ``entity_types`` are both optional filters — an entry with
    neither matches every difference of the pair, which is legal but blunt, so
    the loader requires at least one of them.

    ``entry_id`` (``W01``, ``W02``, … by file order unless the entry gives an
    explicit ``id``) is what the markdown table cites; the full ``reason`` is
    quoted once in the report's footnote section so the table stays readable.
    """

    entry_id: str
    producers: frozenset[str]
    field: DiffField | None
    entity_types: frozenset[str]
    reason: str

    def matches(self, producer_a: str, producer_b: str, difference: Difference) -> bool:
        if not self._producers_match(producer_a, producer_b):
            return False
        if self.field is not None and self.field != difference.field:
            return False
        if self.entity_types and not (self.entity_types & set(difference.entity_types)):
            return False
        return True

    def _producers_match(self, producer_a: str, producer_b: str) -> bool:
        if "*" in self.producers:
            others = self.producers - {"*"}
            # `[*, *]` matches anything; `[*, acad-ts]` matches any pair that
            # has acad-ts on one side.
            return not others or bool(others & {producer_a, producer_b})
        return self.producers == frozenset({producer_a, producer_b})


def load_whitelist(path: Path | None) -> list[WhitelistEntry]:
    """Parse ``path``. ``None`` -> no entries (every difference stays RED)."""
    if path is None:
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - message passthrough
        raise WhitelistError(f"{path}: not valid YAML: {exc}") from exc
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise WhitelistError(f"{path}: top level must be a mapping with an `entries` list")
    entries = raw.get("entries")
    if entries is None:
        return []
    if not isinstance(entries, list):
        raise WhitelistError(f"{path}: `entries` must be a list")
    return [_entry_from(path, index, item) for index, item in enumerate(entries)]


def _entry_from(path: Path, index: int, item: Any) -> WhitelistEntry:
    where = f"{path}: entries[{index}]"
    if not isinstance(item, dict):
        raise WhitelistError(f"{where}: must be a mapping")
    unknown = set(item) - {"id", "producer_pair", "field", "entity_type", "reason"}
    if unknown:
        raise WhitelistError(f"{where}: unknown keys {sorted(unknown)}")

    entry_id = item.get("id", f"W{index + 1:02d}")
    if not isinstance(entry_id, str) or not entry_id.strip():
        raise WhitelistError(f"{where}: `id` must be a non-empty string when given")

    reason = item.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise WhitelistError(f"{where}: `reason` is required and must be a non-empty string")

    pair = item.get("producer_pair")
    if not isinstance(pair, list) or len(pair) != 2 or not all(isinstance(p, str) for p in pair):
        raise WhitelistError(f"{where}: `producer_pair` must be a list of two producer names")

    field_name = item.get("field")
    field: DiffField | None = None
    if field_name is not None:
        if not isinstance(field_name, str):
            raise WhitelistError(f"{where}: `field` must be a string")
        try:
            field = DiffField(field_name)
        except ValueError as exc:
            allowed = ", ".join(sorted(f.value for f in DiffField))
            raise WhitelistError(
                f"{where}: unknown field {field_name!r} (allowed: {allowed})"
            ) from exc
        if field in NEVER_WHITELISTABLE:
            raise WhitelistError(
                f"{where}: `{field.value}` is a count measure and must never be whitelisted "
                "(brief W2-04: 카운트 격차는 화이트리스트 금지) — propose a patch to the "
                "producing task instead"
            )

    raw_types = item.get("entity_type")
    if raw_types is None:
        entity_types: frozenset[str] = frozenset()
    elif isinstance(raw_types, str):
        entity_types = frozenset({raw_types})
    elif isinstance(raw_types, list) and all(isinstance(t, str) for t in raw_types):
        entity_types = frozenset(raw_types)
    else:
        raise WhitelistError(f"{where}: `entity_type` must be a string or a list of strings")

    if field is None and not entity_types:
        raise WhitelistError(f"{where}: needs at least one of `field` / `entity_type`")

    return WhitelistEntry(
        entry_id=entry_id.strip(),
        producers=frozenset(pair),
        field=field,
        entity_types=entity_types,
        reason=" ".join(reason.split()),
    )


def _relative_delta(a: float, b: float) -> float:
    base = max(abs(a), abs(b))
    if base == 0.0:
        return 0.0
    return abs(a - b) / base


def _aggregates(document: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for bucket in document.get("buckets", []):
        out[(str(bucket["space"]), str(bucket["layer"]))] = bucket["aggregate"]
    return out


def _entity_types(*aggregates: dict[str, Any] | None) -> list[str]:
    """DXF record names a whitelist entry can match this bucket on.

    Union of both sides' ``count_by_type`` keys, plus ``ATTRIB`` when the
    bucket's ``text_count`` exceeds its TEXT+MTEXT count — ATTRIBs are
    deliberately absent from ``count_by_type`` (contract: "ATTRIB·SEQEND·
    VERTEX는 세지 않는다") yet an ATTRIB-only bucket still has a bbox and a
    text hash that the parsers can disagree about.
    """
    types: set[str] = set()
    for aggregate in aggregates:
        if aggregate is None:
            continue
        counts = aggregate.get("count_by_type") or {}
        types.update(str(k) for k in counts)
        text_count = int(aggregate.get("text_count") or 0)
        inline = int(counts.get("TEXT", 0)) + int(counts.get("MTEXT", 0))
        if text_count > inline:
            types.add("ATTRIB")
    return sorted(types)


def _insert_totals_agree(reference: dict[str, Any], other: dict[str, Any]) -> bool:
    """True when both sides counted the same number of INSERTs overall.

    Only then may an ``insert_by_block`` difference be whitelisted: the
    disagreement is about a block *name* (acad-ts's unresolved-block gap), not
    about how many INSERTs exist.
    """

    def total(aggregate: dict[str, Any]) -> int:
        return sum(int(v) for v in (aggregate.get("insert_by_block") or {}).values())

    return total(reference) == total(other)


def _diff_count_map(
    field: DiffField, reference: dict[str, Any], other: dict[str, Any], key: str
) -> list[Difference]:
    left = {str(k): int(v) for k, v in (reference.get(key) or {}).items()}
    right = {str(k): int(v) for k, v in (other.get(key) or {}).items()}
    differences: list[Difference] = []
    for name in sorted(set(left) | set(right)):
        a, b = left.get(name, 0), right.get(name, 0)
        if a == b:
            continue
        differences.append(
            Difference(
                field=field,
                severity=Severity.RED,
                detail=f"{key}.{name} {a}→{b}",
                reference_value=str(a),
                other_value=str(b),
                entity_types=[name] if field is DiffField.COUNT_BY_TYPE else [],
            )
        )
    return differences


def _diff_numeric(
    field: DiffField, key: str, reference: dict[str, Any], other: dict[str, Any], tolerance: float
) -> list[Difference]:
    a = float(reference.get(key) or 0.0)
    b = float(other.get(key) or 0.0)
    delta = _relative_delta(a, b)
    if delta <= tolerance:
        return []
    return [
        Difference(
            field=field,
            severity=Severity.RED,
            detail=(f"{key} {a:.6f}→{b:.6f} ({delta * 100:.3f}% > {tolerance * 100:.3f}% 허용)"),
            reference_value=f"{a:.6f}",
            other_value=f"{b:.6f}",
            relative_delta=delta,
        )
    ]


def _diff_bbox(reference: dict[str, Any], other: dict[str, Any]) -> list[Difference]:
    a = reference.get("bbox")
    b = other.get("bbox")
    if a is None and b is None:
        return []
    if a is None or b is None:
        missing = "reference" if a is None else "other"
        return [
            Difference(
                field=DiffField.BBOX,
                severity=Severity.RED,
                detail=f"bbox 누락 ({missing} 문서에 없음)",
                reference_value=None if a is None else _bbox_text(a),
                other_value=None if b is None else _bbox_text(b),
            )
        ]
    corners_a = [a["min"][0], a["min"][1], a["max"][0], a["max"][1]]
    corners_b = [b["min"][0], b["min"][1], b["max"][0], b["max"][1]]
    worst = max(abs(float(x) - float(y)) for x, y in zip(corners_a, corners_b, strict=True))
    if worst <= BBOX_TOLERANCE_MM or math.isclose(worst, BBOX_TOLERANCE_MM):
        return []
    return [
        Difference(
            field=DiffField.BBOX,
            severity=Severity.RED,
            detail=f"bbox 최대 코너 편차 {worst:.3f}mm > {BBOX_TOLERANCE_MM:g}mm",
            reference_value=_bbox_text(a),
            other_value=_bbox_text(b),
            absolute_delta=worst,
        )
    ]


def _bbox_text(bbox: dict[str, Any]) -> str:
    return (
        f"[{float(bbox['min'][0]):.3f}, {float(bbox['min'][1]):.3f}, "
        f"{float(bbox['max'][0]):.3f}, {float(bbox['max'][1]):.3f}]"
    )


def _diff_aggregate(reference: dict[str, Any], other: dict[str, Any]) -> list[Difference]:
    differences: list[Difference] = []
    differences += _diff_count_map(DiffField.COUNT_BY_TYPE, reference, other, "count_by_type")
    differences += _diff_count_map(DiffField.INSERT_BY_BLOCK, reference, other, "insert_by_block")
    differences += _diff_numeric(
        DiffField.LENGTH_SUM_MM, "length_sum_mm", reference, other, LENGTH_TOLERANCE
    )
    differences += _diff_numeric(
        DiffField.HATCH_AREA_SUM_MM2,
        "hatch_area_sum_mm2",
        reference,
        other,
        HATCH_AREA_TOLERANCE,
    )
    ref_text = int(reference.get("text_count") or 0)
    other_text = int(other.get("text_count") or 0)
    if ref_text != other_text:
        differences.append(
            Difference(
                field=DiffField.TEXT_COUNT,
                severity=Severity.RED,
                detail=f"text_count {ref_text}→{other_text}",
                reference_value=str(ref_text),
                other_value=str(other_text),
            )
        )
    ref_hash = str(reference.get("text_hash") or "")
    other_hash = str(other.get("text_hash") or "")
    if ref_hash != other_hash:
        differences.append(
            Difference(
                field=DiffField.TEXT_HASH,
                severity=Severity.RED,
                detail=f"text_hash {ref_hash}→{other_hash}",
                reference_value=ref_hash,
                other_value=other_hash,
            )
        )
    differences += _diff_bbox(reference, other)

    types = _entity_types(reference, other)
    return [d.model_copy(update={"entity_types": d.entity_types or types}) for d in differences]


def _apply_whitelist(
    differences: list[Difference],
    entries: list[WhitelistEntry],
    producer_a: str,
    producer_b: str,
    reference: dict[str, Any] | None,
    other: dict[str, Any] | None,
) -> list[Difference]:
    """Downgrade RED -> AMBER where an entry explains the difference."""
    out: list[Difference] = []
    for difference in differences:
        if difference.field in NEVER_WHITELISTABLE:
            out.append(difference)
            continue
        if difference.field is DiffField.INSERT_BY_BLOCK and not (
            reference is not None and other is not None and _insert_totals_agree(reference, other)
        ):
            # An INSERT was gained or lost, not merely renamed: a count gap.
            out.append(difference)
            continue
        entry = next((e for e in entries if e.matches(producer_a, producer_b, difference)), None)
        if entry is None:
            out.append(difference)
            continue
        out.append(
            difference.model_copy(
                update={
                    "severity": Severity.AMBER,
                    "whitelist_id": entry.entry_id,
                    "whitelist_reason": entry.reason,
                }
            )
        )
    return out


def _worst(differences: list[Difference]) -> Severity:
    if any(d.severity is Severity.RED for d in differences):
        return Severity.RED
    if differences:
        return Severity.AMBER
    return Severity.GREEN


def _producer(document: dict[str, Any]) -> ProducerInfo:
    producer = document.get("producer") or {}
    if isinstance(producer, str):  # tolerate the contract's older bare-string form
        return ProducerInfo(name=producer, version="")
    return ProducerInfo(
        name=str(producer.get("name", "?")), version=str(producer.get("version", ""))
    )


def compare(
    reference: dict[str, Any],
    other: dict[str, Any],
    *,
    whitelist: list[WhitelistEntry] | None = None,
    whitelist_path: str | None = None,
) -> CrosscheckReport:
    """Compare two ``LayerStatsDocument``s and build the report.

    Pure and side-effect free; ``O(buckets)`` so the brief's "<1초 regardless of
    document size" holds for any document the stats producers can emit.
    """
    entries = whitelist or []
    ref_producer = _producer(reference)
    other_producer = _producer(other)
    a_name, b_name = ref_producer.name, other_producer.name

    ref_buckets = _aggregates(reference)
    other_buckets = _aggregates(other)

    layers: list[LayerResult] = []
    for space, layer in sorted(set(ref_buckets) | set(other_buckets), key=lambda k: (k[1], k[0])):
        ref_aggregate = ref_buckets.get((space, layer))
        other_aggregate = other_buckets.get((space, layer))
        if ref_aggregate is None or other_aggregate is None:
            missing = "reference" if ref_aggregate is None else "other"
            present = other_aggregate if ref_aggregate is None else ref_aggregate
            differences = [
                Difference(
                    field=DiffField.BUCKET,
                    severity=Severity.RED,
                    detail=f"버킷이 {missing} 문서에만 없음 ({space} / {layer})",
                    entity_types=_entity_types(present),
                )
            ]
        else:
            differences = _apply_whitelist(
                _diff_aggregate(ref_aggregate, other_aggregate),
                entries,
                a_name,
                b_name,
                ref_aggregate,
                other_aggregate,
            )
        layers.append(
            LayerResult(
                layer=layer, space=space, status=_worst(differences), differences=differences
            )
        )

    totals_differences = _apply_whitelist(
        _diff_aggregate(reference.get("totals") or {}, other.get("totals") or {}),
        entries,
        a_name,
        b_name,
        reference.get("totals") or {},
        other.get("totals") or {},
    )
    totals = LayerResult(
        layer=_TOTALS_LAYER,
        space=_TOTALS_SPACE,
        status=_worst(totals_differences),
        differences=totals_differences,
    )

    red_layers = sorted({layer.layer for layer in layers if layer.status is Severity.RED})
    amber_layers = sorted({layer.layer for layer in layers if layer.status is Severity.AMBER})
    counts = {
        Severity.GREEN.value: sum(1 for x in layers if x.status is Severity.GREEN),
        Severity.AMBER.value: sum(1 for x in layers if x.status is Severity.AMBER),
        Severity.RED.value: sum(1 for x in layers if x.status is Severity.RED),
    }

    warnings: list[str] = []
    ref_sha = str(reference.get("file_sha256") or "")
    other_sha = str(other.get("file_sha256") or "")
    mismatch = ref_sha != other_sha
    if mismatch:
        warnings.append(
            f"file_sha256 불일치: {ref_sha[:12]}… vs {other_sha[:12]}… "
            "(DWG와 그 DXF 변환본을 비교하는 경우 정상). 비교는 그대로 진행한다."
        )

    status = _worst([d for layer in [*layers, totals] for d in layer.differences])

    return CrosscheckReport(
        schema_version=REPORT_SCHEMA_VERSION,
        status=status,
        reference=ref_producer,
        other=other_producer,
        file_sha256=None if mismatch else (ref_sha or None),
        file_sha256_mismatch=mismatch,
        layers=layers,
        totals=totals,
        red_layers=red_layers,
        amber_layers=amber_layers,
        counts=counts,
        warnings=warnings,
        whitelist_path=whitelist_path,
    )


_STATUS_MARK = {Severity.GREEN: "🟢 GREEN", Severity.AMBER: "🟡 AMBER", Severity.RED: "🔴 RED"}


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def _layer_row(result: LayerResult) -> str:
    if not result.differences:
        cause = "-"
    else:
        parts = []
        for difference in result.differences:
            piece = f"`{difference.detail}`"
            if difference.whitelist_id:
                # Only the id here; the reason is quoted once in the footnote
                # section so a table cell stays one readable line.
                piece += f" ({difference.whitelist_id})"
            parts.append(piece)
        cause = "<br>".join(parts)
    return (
        f"| {_escape_cell(result.layer)} | {_escape_cell(result.space)} | "
        f"{_STATUS_MARK[result.status]} | {_escape_cell(cause)} |"
    )


def _cited_whitelist(report: CrosscheckReport) -> list[tuple[str, str]]:
    """``(id, reason)`` of every whitelist entry this report actually used."""
    cited: dict[str, str] = {}
    for result in [*report.layers, report.totals]:
        for difference in result.differences:
            if difference.whitelist_id and difference.whitelist_reason:
                cited.setdefault(difference.whitelist_id, difference.whitelist_reason)
    return sorted(cited.items())


def render_markdown(report: CrosscheckReport) -> str:
    """Korean-headed layer table plus an overall verdict (brief: 마크다운 표는 한국어 헤더)."""
    lines: list[str] = []
    ref = f"{report.reference.name}@{report.reference.version}".rstrip("@")
    other = f"{report.other.name}@{report.other.version}".rstrip("@")
    lines.append(f"# 파서 교차검증 리포트 — {ref} vs {other}")
    lines.append("")
    lines.append(f"- 총평: **{_STATUS_MARK[report.status]}**")
    lines.append(
        f"- 레이어: 전체 {len(report.layers)}개 "
        f"(GREEN {report.counts.get('GREEN', 0)} / "
        f"AMBER {report.counts.get('AMBER', 0)} / "
        f"RED {report.counts.get('RED', 0)})"
    )
    lines.append(f"- 총계(totals): {_STATUS_MARK[report.totals.status]}")
    if report.red_layers:
        lines.append(f"- `red_layers`: {', '.join(f'`{x}`' for x in report.red_layers)}")
    if report.whitelist_path:
        lines.append(f"- 화이트리스트: `{report.whitelist_path}`")
    for warning in report.warnings:
        lines.append(f"- ⚠️ {warning}")
    lines.append("")
    lines.append("| 레이어 | 공간 | 상태 | 원인 |")
    lines.append("|---|---|---|---|")
    for result in report.layers:
        lines.append(_layer_row(result))
    lines.append(_layer_row(report.totals))

    cited = _cited_whitelist(report)
    if cited:
        lines.append("")
        lines.append("## 화이트리스트 사유 (AMBER로 낮춘 근거)")
        lines.append("")
        for entry_id, reason in cited:
            lines.append(f"- **{entry_id}** — {reason}")
    lines.append("")
    return "\n".join(lines)


def report_json_schema() -> dict[str, Any]:
    """JSON Schema of :class:`CrosscheckReport`, as committed next to this module."""
    schema = CrosscheckReport.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://schema.halo-cad.internal/v0/validate/crosscheck-report.schema.json"
    return schema


def report_schema_text() -> str:
    """Canonical serialisation of :func:`report_json_schema` (committed form)."""
    return json.dumps(report_json_schema(), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


__all__ = [
    "BBOX_TOLERANCE_MM",
    "DEFAULT_WHITELIST",
    "HATCH_AREA_TOLERANCE",
    "LENGTH_TOLERANCE",
    "NEVER_WHITELISTABLE",
    "REPORT_SCHEMA_VERSION",
    "WhitelistEntry",
    "WhitelistError",
    "compare",
    "load_whitelist",
    "render_markdown",
    "report_json_schema",
    "report_schema_text",
]
