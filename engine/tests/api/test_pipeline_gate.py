"""``ingest/pipeline.py``'s pure functions: format detection and the crosscheck gate.

ADR-0002's 2026-09-02 amendment, decision 4: a DWG conversion's engine
working-DXF must pass audit-error-count == 0 and a <=0.5% entity-count
delta, or it is a blocking failure -- not a warning.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from halo_engine.ingest.pipeline import (
    ENTITY_COUNT_TOLERANCE,
    detect_format,
    evaluate_conversion_gate,
)
from halo_engine.model.drawing import DrawingFormat


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("plan.dwg", DrawingFormat.DWG),
        ("plan.DWG", DrawingFormat.DWG),
        ("plan.dxf", DrawingFormat.DXF),
    ],
)
def test_detect_format(name: str, expected: DrawingFormat) -> None:
    assert detect_format(Path(name)) is expected


def test_detect_format_rejects_unknown_extensions() -> None:
    with pytest.raises(ValueError):
        detect_format(Path("plan.pdf"))


def test_gate_passes_on_an_exact_match() -> None:
    result = evaluate_conversion_gate(
        audit_error_count=0, engine_entity_count=100, converter_entity_count=100
    )
    assert result.passed is True
    assert result.reasons == []


def test_gate_passes_at_exactly_the_tolerance_boundary() -> None:
    engine_count = 1000
    converter_count = engine_count + round(engine_count * ENTITY_COUNT_TOLERANCE)
    result = evaluate_conversion_gate(
        audit_error_count=0,
        engine_entity_count=engine_count,
        converter_entity_count=converter_count,
    )
    assert result.passed is True


def test_gate_fails_just_over_the_tolerance() -> None:
    result = evaluate_conversion_gate(
        audit_error_count=0, engine_entity_count=1000, converter_entity_count=1010
    )
    assert result.passed is False
    assert "entity count mismatch" in result.reasons[0]


def test_gate_fails_on_any_audit_deletion_even_with_matching_counts() -> None:
    result = evaluate_conversion_gate(
        audit_error_count=1, engine_entity_count=100, converter_entity_count=100
    )
    assert result.passed is False
    assert "auditor deleted" in result.reasons[0]


def test_gate_reports_every_failing_reason_at_once() -> None:
    result = evaluate_conversion_gate(
        audit_error_count=3, engine_entity_count=100, converter_entity_count=200
    )
    assert result.passed is False
    assert len(result.reasons) == 2


def test_gate_handles_zero_engine_entity_count_without_dividing_by_zero() -> None:
    result = evaluate_conversion_gate(
        audit_error_count=0, engine_entity_count=0, converter_entity_count=0
    )
    assert result.passed is True
