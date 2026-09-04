"""Every scenario's ``truth.json`` must validate against
``packages/schema/src/compare/truth.schema.json`` (`RevisionTruth`,
docs/contracts/r1.md SS4, R1-01). The schema is loaded from disk directly and
its absolute ``$ref``s (into ``common/primitives``, ``compare/sheet-frame``,
``compare/sheet-pair``, ``compare/change``) are resolved with a
``referencing`` registry built from every ``*.schema.json`` under
``packages/schema/src`` -- not by importing anything from ``packages/schema``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

GEN_ROOT = Path(__file__).resolve().parents[1]
COMPARE_ROOT = GEN_ROOT.parent
REPO_ROOT = COMPARE_ROOT.parents[1]
SCHEMA_SRC = REPO_ROOT / "packages" / "schema" / "src"
TRUTH_SCHEMA_PATH = SCHEMA_SRC / "compare" / "truth.schema.json"


def _build_registry() -> Registry:
    resources = []
    for path in SCHEMA_SRC.rglob("*.schema.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append(Resource.from_contents(contents))
    return Registry().with_resources((r.id(), r) for r in resources)


def _validator() -> Draft202012Validator:
    schema = json.loads(TRUTH_SCHEMA_PATH.read_text(encoding="utf-8"))
    registry = _build_registry()
    return Draft202012Validator(schema, registry=registry)


def _scenario_dirs() -> list[Path]:
    return sorted(p for p in COMPARE_ROOT.iterdir() if p.is_dir() and p.name != "gen")


SCENARIO_DIRS = _scenario_dirs()


def test_at_least_17_scenarios_committed() -> None:
    assert len(SCENARIO_DIRS) == 17, [p.name for p in SCENARIO_DIRS]


@pytest.mark.parametrize("scenario_dir", SCENARIO_DIRS, ids=lambda p: p.name)
def test_truth_json_matches_schema(scenario_dir: Path) -> None:
    truth_path = scenario_dir / "truth.json"
    assert truth_path.is_file(), f"missing {truth_path}"
    data = json.loads(truth_path.read_text(encoding="utf-8"))

    validator = _validator()
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    assert errors == [], "\n".join(f"{list(e.path)}: {e.message}" for e in errors)

    assert data["scenario"] == scenario_dir.name


@pytest.mark.parametrize("scenario_dir", SCENARIO_DIRS, ids=lambda p: p.name)
def test_before_after_dirs_exist(scenario_dir: Path) -> None:
    data = json.loads((scenario_dir / "truth.json").read_text(encoding="utf-8"))
    before_dir = scenario_dir / data["before_dir"]
    after_dir = scenario_dir / data["after_dir"]
    assert before_dir.is_dir(), before_dir
    assert after_dir.is_dir(), after_dir
    assert list(before_dir.glob("*.dxf")), f"no DXF under {before_dir}"
    assert list(after_dir.glob("*.dxf")), f"no DXF under {after_dir}"
