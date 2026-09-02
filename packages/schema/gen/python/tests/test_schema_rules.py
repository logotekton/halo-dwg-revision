"""The Python side must reject exactly what the viewer rejects.

These tests go through :mod:`halo_schema.validation`, which validates against
the JSON Schema sources shipped with the package. They need no generated model,
so they run even before ``scripts/gen-python.sh`` has been executed.
"""

from __future__ import annotations

import pytest

from halo_schema import SCHEMA_FILES, SCHEMA_IDS, SCHEMA_VERSION, load_schema, schema_path
from halo_schema.validation import (
    SchemaValidationError,
    assert_valid,
    consistency_check_validator,
    failures,
    is_valid,
)

from conftest import load_example

EXPECTATIONS = [
    ("f06.ndj.json", "ndj_document", True),
    ("layer-stats.f06.json", "layer_stats", True),
    ("entity.line.json", "ndj_entity", True),
    ("entity.bad-missing-handle.json", "ndj_entity", False),
    ("entity.bad-unknown-type.json", "ndj_entity", False),
    ("levels.ok.json", "floor_levels", True),
    ("levels.bad-ch-eq-sl.json", "consistency_check_set", False),
    ("consistency.ok.json", "consistency_check_set", True),
    ("consistency.bad.json", "consistency_check_set", False),
    ("markup.json", "markup_sidecar", True),
    ("tags.json", "tags_sidecar", True),
    ("bridge.ready.json", "bridge_message", True),
    ("bridge.load.json", "bridge_message", True),
    ("bridge.select.json", "bridge_message", True),
    ("bridge.colorize.json", "bridge_message", True),
    ("bridge.camera.json", "bridge_message", True),
    ("bridge.selected.json", "bridge_message", True),
    ("bridge.error.json", "bridge_message", True),
    ("bridge.bad-unknown-type.json", "bridge_message", False),
]


@pytest.mark.parametrize(("name", "key", "expected"), EXPECTATIONS)
def test_example_matches_expectation(name: str, key: str, expected: bool) -> None:
    document = load_example(name)
    assert is_valid(key, document) is expected, failures(key, document)


def test_every_example_is_covered(examples_dir) -> None:
    on_disk = sorted(path.name for path in examples_dir.glob("*.json"))
    assert on_disk == sorted(name for name, _, _ in EXPECTATIONS)


def test_schema_files_are_all_present() -> None:
    for key in SCHEMA_FILES:
        assert schema_path(key).is_file(), key
        assert load_schema(key)["$id"] == SCHEMA_IDS[key]


def _check(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "PROBE",
        "left_kind": "SL",
        "right_kind": "SL",
        "operator": "EQ",
        "tolerance_mm": 5,
    }
    base.update(overrides)
    return base


class TestHeightRules:
    """ADR-0003, enforced by the schema itself so neither language can express
    a forbidden comparison."""

    validator = consistency_check_validator()

    @pytest.mark.parametrize("kind", ["SL", "FL", "FLOOR_HEIGHT"])
    def test_same_basis_equality_is_allowed(self, kind: str) -> None:
        assert self.validator.is_valid(_check(left_kind=kind, right_kind=kind))

    @pytest.mark.parametrize("other", ["SL", "FL", "FLOOR_HEIGHT"])
    def test_ceiling_height_equality_is_refused(self, other: str) -> None:
        assert not self.validator.is_valid(_check(left_kind="CH", right_kind=other))
        assert not self.validator.is_valid(_check(left_kind=other, right_kind="CH"))

    @pytest.mark.parametrize("operator", ["LT", "LE", "GT", "GE"])
    def test_ceiling_height_inequality_is_allowed(self, operator: str) -> None:
        assert self.validator.is_valid(
            _check(
                left_kind="CH",
                right_kind="FLOOR_HEIGHT",
                operator=operator,
                tolerance_mm=0,
                left_offset_mm=250,
            )
        )

    def test_cross_basis_equality_without_ceiling_height_is_refused(self) -> None:
        assert not self.validator.is_valid(_check(left_kind="FL", right_kind="SL"))

    def test_only_the_offending_check_is_blamed(self) -> None:
        document = load_example("levels.bad-ch-eq-sl.json")
        reasons = failures("consistency_check_set", document)
        assert reasons
        assert any(reason.startswith("/checks/1") for reason in reasons)
        assert not any(reason.startswith("/checks/0") for reason in reasons)


def test_assert_valid_raises_with_every_reason() -> None:
    with pytest.raises(SchemaValidationError) as excinfo:
        assert_valid("provenance", {"space": "MODEL"}, "provenance")
    assert len(excinfo.value.reasons) >= 3
    assert excinfo.value.schema_id == SCHEMA_IDS["provenance"]


def test_documents_carry_the_current_schema_version() -> None:
    for name in ("f06.ndj.json", "layer-stats.f06.json", "levels.ok.json", "tags.json"):
        assert load_example(name)["schema_version"] == SCHEMA_VERSION


def test_evidence_is_required_unless_the_value_was_typed_by_a_user() -> None:
    observation = {
        "id": "3QDKA01V7Z92XDAFB342P3RS7T",
        "kind": "CH",
        "value_mm": 2700,
        "source": "LEVEL_TABLE",
        "evidence": [],
        "confidence": 0.8,
        "raw_text": "2,700",
    }
    assert not is_valid("level_observation", observation)
    observation["source"] = "USER"
    observation["raw_text"] = ""
    assert is_valid("level_observation", observation)
