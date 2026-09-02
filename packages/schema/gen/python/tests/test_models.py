"""The generated pydantic models must load the same example documents.

Marked ``models`` so the suite skips cleanly on a checkout where
``scripts/gen-python.sh`` has not been run yet (see conftest.py).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.models

pydantic = pytest.importorskip("pydantic")
ValidationError = pydantic.ValidationError

from halo_schema.models.bridge.messages_schema import BridgeMessage  # noqa: E402
from halo_schema.models.common.provenance_schema import Provenance  # noqa: E402
from halo_schema.models.levels.consistency_check_schema import ConsistencyCheckSet  # noqa: E402
from halo_schema.models.levels.floor_levels_schema import FloorLevelsDocument  # noqa: E402
from halo_schema.models.ndj.document_schema import NdjDocument  # noqa: E402
from halo_schema.models.sidecar.markup_schema import MarkupSidecar  # noqa: E402
from halo_schema.models.sidecar.tags_schema import TagsSidecar  # noqa: E402
from halo_schema.models.stats.layer_stats_schema import LayerStatsDocument  # noqa: E402

from halo_schema.validation import is_valid  # noqa: E402

from conftest import load_example  # noqa: E402


def test_ndj_document_loads() -> None:
    document = NdjDocument.model_validate(load_example("f06.ndj.json"))
    assert len(document.entities) == 14
    assert document.header.dwg_version.value == "AC1032"
    kinds = sorted({entity.type for entity in document.entities})
    assert kinds == ["ATTRIB", "HATCH", "INSERT", "LINE", "LWPOLYLINE", "MTEXT", "TEXT"]


def test_every_entity_keeps_its_provenance() -> None:
    document = NdjDocument.model_validate(load_example("f06.ndj.json"))
    for entity in document.entities:
        assert entity.provenance.handle
        assert entity.provenance.space == "MODEL"


def test_ndj_document_round_trips_through_json() -> None:
    original = load_example("f06.ndj.json")
    document = NdjDocument.model_validate(original)
    # `exclude_unset` reproduces exactly the fields the producer wrote, which is
    # what travels between the engine and the viewer.
    dumped = document.model_dump(mode="json", exclude_unset=True, by_alias=True)
    assert dumped == original
    assert NdjDocument.model_validate(dumped) == document
    assert is_valid("ndj_document", dumped)


def test_layer_stats_round_trip() -> None:
    stats = LayerStatsDocument.model_validate(load_example("layer-stats.f06.json"))
    assert stats.totals.entity_count == 14
    assert stats.totals.length_sum_mm == 36000
    dumped = stats.model_dump(mode="json", exclude_unset=True)
    assert dumped == load_example("layer-stats.f06.json")
    assert LayerStatsDocument.model_validate(dumped) == stats
    assert is_valid("layer_stats", dumped)


def test_floor_levels_keeps_the_four_heights_apart() -> None:
    levels = FloorLevelsDocument.model_validate(load_example("levels.ok.json"))
    third = levels.floors[0]
    assert (third.sl_mm, third.fl_mm, third.floor_height_mm, third.ch_mm) == (
        9000,
        9050,
        3300,
        2700,
    )
    # ADR-0003: the only legal relation across bases is this inequality.
    assert third.ch_mm + 200 + 50 < third.floor_height_mm


def test_provenance_requires_a_handle() -> None:
    with pytest.raises(ValidationError):
        Provenance.model_validate(load_example("entity.bad-missing-handle.json")["provenance"])


def test_unknown_entity_type_is_refused() -> None:
    document = load_example("f06.ndj.json")
    document["entities"] = [load_example("entity.bad-unknown-type.json")]
    with pytest.raises(ValidationError):
        NdjDocument.model_validate(document)


def test_sidecars_and_bridge_messages_load() -> None:
    assert len(MarkupSidecar.model_validate(load_example("markup.json")).markups) == 3
    assert len(TagsSidecar.model_validate(load_example("tags.json")).tags) == 2
    for name in ("ready", "load", "select", "colorize", "camera", "selected", "error"):
        message = BridgeMessage.model_validate(load_example(f"bridge.{name}.json"))
        assert message.root.type == name


def test_unknown_bridge_message_type_is_refused() -> None:
    with pytest.raises(ValidationError):
        BridgeMessage.model_validate(load_example("bridge.bad-unknown-type.json"))


def test_consistency_check_set_loads_the_shape_only() -> None:
    # The models carry the shape; the ADR-0003 rules are conditionals that
    # pydantic cannot express, so the forbidden set still loads here and is
    # rejected by halo_schema.validation instead (see test_schema_rules.py).
    checks = ConsistencyCheckSet.model_validate(load_example("consistency.ok.json"))
    assert [check.id for check in checks.checks][0] == "SL_ELEVATION_VS_SECTION"
