"""The committed ``crosscheck_report.schema.json`` must match the pydantic model.

The schema is published for the TypeScript side (the W3 crosscheck panel reads
``drawing_file.parser_crosscheck``), so it is generated from
:class:`~halo_engine.model.crosscheck.CrosscheckReport` rather than hand
written — this test is what keeps the two from drifting.
"""

from __future__ import annotations

import json

import jsonschema
from helpers import stats_document

from halo_engine.validate.crosscheck import (
    DEFAULT_WHITELIST,
    compare,
    report_json_schema,
    report_schema_text,
)

SCHEMA_PATH = DEFAULT_WHITELIST.with_name("crosscheck_report.schema.json")


def test_committed_schema_matches_the_model() -> None:
    committed = SCHEMA_PATH.read_text(encoding="utf-8")
    assert committed == report_schema_text(), (
        "regenerate with: uv run python -c "
        "'from pathlib import Path; from halo_engine.validate.crosscheck import "
        "report_schema_text, DEFAULT_WHITELIST; "
        'Path(DEFAULT_WHITELIST.with_name("crosscheck_report.schema.json"))'
        '.write_text(report_schema_text(), encoding="utf-8")\''
    )


def test_a_real_report_validates_against_the_committed_schema() -> None:
    report = compare(
        stats_document(
            producer="engine.ezdxf", buckets=[("MODEL", "X-GRID", {"count_by_type": {"LINE": 24}})]
        ),
        stats_document(
            producer="viewer.mlightcad",
            buckets=[("MODEL", "X-GRID", {"count_by_type": {"LINE": 22}})],
        ),
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(report.model_dump(mode="json"), schema)


def test_schema_declares_red_layers_for_the_confidence_router() -> None:
    """`red_layers` is the P4 routing input (brief W2-04, "신뢰도 연동 준비")."""
    schema = report_json_schema()
    assert "red_layers" in schema["properties"]
    assert schema["properties"]["red_layers"]["type"] == "array"
