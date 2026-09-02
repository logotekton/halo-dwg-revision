from __future__ import annotations

from pathlib import Path

import pytest

# engine/tests/validate/conftest.py -> engine/tests -> engine -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_TRUTH = REPO_ROOT / "fixtures" / "truth"


@pytest.fixture
def truth_dir() -> Path:
    if not FIXTURES_TRUTH.exists():
        pytest.skip(f"{FIXTURES_TRUTH} missing -- run the fixture generator")
    return FIXTURES_TRUTH
