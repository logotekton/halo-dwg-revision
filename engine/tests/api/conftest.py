from __future__ import annotations

from pathlib import Path

import pytest

# engine/tests/api/conftest.py -> engine/tests -> engine -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_GENERATED = REPO_ROOT / "fixtures" / "generated"
ACAD_BRIDGE_BIN = REPO_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"{path} missing -- run `cd fixtures/gen && uv run python -m fixtures_gen`")
    return path


@pytest.fixture
def generated_dir() -> Path:
    return _require(FIXTURES_GENERATED)


@pytest.fixture
def acad_bridge_bin() -> Path:
    if not ACAD_BRIDGE_BIN.is_file():
        pytest.skip(
            f"{ACAD_BRIDGE_BIN} missing -- run `pnpm install && "
            "pnpm --filter @halo-cad/schema build && "
            "pnpm --filter @halo-cad/acad-bridge build`"
        )
    return ACAD_BRIDGE_BIN
