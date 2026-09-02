from __future__ import annotations

from pathlib import Path

import pytest

GEN_DIR = Path(__file__).resolve()
# tests/ -> gen/ -> fixtures/
FIXTURES_ROOT = GEN_DIR.parents[2]
GENERATED_DIR = FIXTURES_ROOT / "generated"
TRUTH_DIR = FIXTURES_ROOT / "truth"

COMMITTED_FIXTURE_IDS = [f"F{i:02d}" for i in range(1, 11)]  # F01..F10


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"{path} not generated yet -- run `uv run python -m fixtures_gen` first")
    return path


@pytest.fixture
def generated_dir() -> Path:
    return _require(GENERATED_DIR)


@pytest.fixture
def truth_dir() -> Path:
    return _require(TRUTH_DIR)
