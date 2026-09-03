"""System endpoints: health, capabilities, shutdown (`docs/PLAN.md` §3)."""

from __future__ import annotations

import importlib.metadata
import logging
import platform
from typing import Any

from fastapi import APIRouter, Request

logger = logging.getLogger("halo_engine.api.system")

router = APIRouter()

# Dependencies whose versions are reported by /health. Import names, not
# distribution names, differ for a couple of these (handled in _dep_version).
_DEP_DISTRIBUTIONS = {
    "ezdxf": "ezdxf",
    "shapely": "shapely",
    "manifold3d": "manifold3d",
    "trimesh": "trimesh",
    "ifcopenshell": "ifcopenshell",
    "numpy": "numpy",
    "fastapi": "fastapi",
}


def _dep_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Unauthenticated liveness probe. Returns dependency versions for diagnostics."""
    return {
        "status": "ok",
        "version": request.app.version,
        "python": platform.python_version(),
        "deps": {name: _dep_version(dist) for name, dist in _DEP_DISTRIBUTIONS.items()},
    }


@router.get("/capabilities")
async def capabilities() -> dict[str, bool]:
    """Honest, current feature flags — no aspirational values."""
    return {
        "dwg2dxf": False,
        "ifc_export": True,
        "job_runner": True,
        "websocket": True,
        "dms_sync": False,
    }


@router.post("/shutdown")
async def shutdown(request: Request) -> dict[str, str]:
    """Graceful shutdown, used by the sidecar protocol's step 5 (parent-initiated stop)."""
    server = getattr(request.app.state, "server", None)
    if server is not None:
        logger.info("shutdown requested via API")
        server.should_exit = True
    return {"status": "shutting down"}
