"""Shared fixtures for the halo_schema tests.

The generated models live under ``halo_schema/models``. When they have not been
generated yet the whole suite skips with a pointer at the script that writes
them, so a checkout without uv still reports cleanly instead of erroring.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "halo_schema"
SCHEMA_PACKAGE_ROOT = Path(__file__).resolve().parents[3]
EXAMPLES_DIR = SCHEMA_PACKAGE_ROOT / "examples"


def load_example(name: str) -> Any:
    return json.loads((EXAMPLES_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def examples_dir() -> Path:
    return EXAMPLES_DIR


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if (PACKAGE_ROOT / "models" / "__init__.py").exists():
        return
    skip = pytest.mark.skip(
        reason="pydantic models not generated; run packages/schema/scripts/gen-python.sh"
    )
    for item in items:
        if "models" in item.keywords:
            item.add_marker(skip)
