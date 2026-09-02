"""Every committed ``fixtures/truth/F##.json`` (and ``F10_grid.json`` /
``F10_host.json``) must validate against ``LayerStatsDocument``
(``packages/schema/src/stats/layer-stats.schema.json``), per the brief's DoD.

Uses ``jsonschema`` + ``referencing`` against a registry of every schema
under ``packages/schema/src`` (same approach as
``packages/schema/gen/python/halo_schema/validation.py``, without depending
on that package -- brief Constraints).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pytest
from conftest import FIXTURES_TRUTH, SCHEMA_SRC
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

LAYER_STATS_SCHEMA_ID = "https://schema.halo-cad.internal/v0/stats/layer-stats.schema.json"

#: Known schema/contract mismatch, not ours to fix (packages/schema is
#: Fable-owned): the ``entity_type`` enum in
#: ``packages/schema/src/ndj/entity.schema.json`` lists the AutoCAD UI name
#: "MLEADER", but ``docs/contracts/stats-definition.md`` and every real DXF
#: file spell the group-code type name "MULTILEADER" (as does
#: ``fixtures/README.md`` Decision 10, for the same underlying naming
#: mismatch elsewhere). Reported as a Shared-file patch in the W2-03 report.
KNOWN_SCHEMA_GAPS: dict[str, str] = {"F05.json": "'MULTILEADER' is not one of"}


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    for path in SCHEMA_SRC.rglob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(schema, default_specification=DRAFT202012)
        resources.append((schema["$id"], resource))
    return Registry().with_resources(resources)


@lru_cache(maxsize=1)
def _validator() -> Draft202012Validator:
    return Draft202012Validator({"$ref": LAYER_STATS_SCHEMA_ID}, registry=_registry())


def _truth_stats_files() -> list[Path]:
    if not FIXTURES_TRUTH.exists():
        return []
    files = sorted(FIXTURES_TRUTH.glob("F*.json"))
    return [f for f in files if not f.name.endswith(".extra.json")]


@pytest.mark.parametrize("path", _truth_stats_files(), ids=lambda p: p.name)
def test_truth_file_validates_as_layer_stats_document(path: Path) -> None:
    doc = json.loads(path.read_text(encoding="utf-8"))
    errors = sorted(_validator().iter_errors(doc), key=lambda e: list(e.absolute_path))
    known_gap = KNOWN_SCHEMA_GAPS.get(path.name)
    if known_gap:
        errors = [e for e in errors if known_gap not in e.message]
    assert not errors, "; ".join(
        f"{'/'.join(str(p) for p in e.absolute_path) or '/'}: {e.message}" for e in errors
    )


def test_at_least_f01_through_f11_are_covered() -> None:
    if not FIXTURES_TRUTH.exists():
        pytest.skip(f"{FIXTURES_TRUTH} missing")
    names = {p.stem for p in _truth_stats_files()}
    expected = {f"F{i:02d}" for i in range(1, 10)} | {"F10_grid", "F10_host", "F11"}
    assert expected <= names
