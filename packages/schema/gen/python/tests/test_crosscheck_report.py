"""``CrosscheckReport`` (brief W3-08 goal 2, G0 follow-up 4) is unlike every
other schema this package generates from: its source of truth is the
engine's own pydantic model (``engine/src/halo_engine/model/crosscheck.py``),
not hand-authored JSON Schema. ``packages/schema/src/stats/crosscheck-report.schema.json``
is a byte-identical copy of the engine's own committed schema (see
``test/crosscheck-report.test.ts``'s docstring on the TS side for why a byte
copy rather than a re-authored one) -- generating a pydantic model from it
here and loading the *same* real report the engine's ``compare()`` produced
(``examples/crosscheck-report.f06.json``) into it is this task's proof that
the two languages' shapes have not drifted, without either language's test
suite importing the other's toolchain.

Not registered in ``halo_schema.SCHEMA_FILES``/``SCHEMA_IDS`` (that module is
hand written, outside this task's "Files you own" glob -- brief W3-08), so
this test loads the schema copy directly with a standalone
``jsonschema.Draft202012Validator`` instead of going through
``halo_schema.validation``.
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.models

pydantic = pytest.importorskip("pydantic")

from jsonschema import Draft202012Validator  # noqa: E402

from halo_schema import SCHEMAS_DIR  # noqa: E402
from halo_schema.models.stats.crosscheck_report_schema import CrosscheckReport  # noqa: E402

from conftest import load_example  # noqa: E402

SCHEMA_PATH = SCHEMAS_DIR / "stats" / "crosscheck-report.schema.json"


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def test_shipped_schema_copy_is_self_contained_and_valid_2020_12() -> None:
    """No external $refs (only local #/$defs/... pointers), so a standalone
    validator -- no registry -- is enough, unlike every registered schema.
    """
    _schema_validator()  # raises if the schema itself is malformed


def test_real_engine_report_validates_against_the_schema_copy() -> None:
    report = load_example("crosscheck-report.f06.json")
    validator = _schema_validator()
    errors = sorted(validator.iter_errors(report), key=lambda e: list(e.absolute_path))
    assert not errors, [e.message for e in errors]


def test_real_engine_report_loads_into_the_generated_pydantic_model() -> None:
    report = load_example("crosscheck-report.f06.json")
    model = CrosscheckReport.model_validate(report)
    assert model.status == "RED"
    assert model.reference.name == "engine.ezdxf"
    assert model.other.name == "viewer.mlightcad"
    assert model.red_layers == ["X-GRID"]
    assert [layer.layer for layer in model.layers] == [
        "A-TEXT",
        "S-BEAM",
        "S-COL",
        "X-GRID",
        "X-TITLE",
    ]
    x_grid = next(layer for layer in model.layers if layer.layer == "X-GRID")
    assert x_grid.status == "RED"
    assert x_grid.differences[0].detail == "count_by_type.LINE 7→6"


def test_model_round_trips_the_example_unchanged() -> None:
    report = load_example("crosscheck-report.f06.json")
    model = CrosscheckReport.model_validate(report)
    dumped = model.model_dump(mode="json", exclude_unset=True)
    assert dumped == report


def test_model_rejects_an_unknown_top_level_field() -> None:
    report = dict(load_example("crosscheck-report.f06.json"))
    report["unexpected_field"] = True
    with pytest.raises(pydantic.ValidationError):
        CrosscheckReport.model_validate(report)
