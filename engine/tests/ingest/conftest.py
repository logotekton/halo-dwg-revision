from __future__ import annotations

from pathlib import Path

import pytest

# engine/tests/ingest/conftest.py -> engine/tests -> engine -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_GENERATED = REPO_ROOT / "fixtures" / "generated"
FIXTURES_TRUTH = REPO_ROOT / "fixtures" / "truth"
SCHEMA_SRC = REPO_ROOT / "packages" / "schema" / "src"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"{path} missing -- run `cd fixtures/gen && uv run python -m fixtures_gen`")
    return path


@pytest.fixture
def generated_dir() -> Path:
    return _require(FIXTURES_GENERATED)


@pytest.fixture
def truth_dir() -> Path:
    return _require(FIXTURES_TRUTH)
