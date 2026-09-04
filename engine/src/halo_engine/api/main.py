"""FastAPI application factory for the halo_engine sidecar.

Structure follows FastAPI's "Bigger Applications" pattern: a thin factory
here, feature routers under ``api/routers/``.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from halo_engine import __version__
from halo_engine.api import jobs, ws
from halo_engine.api.routers import (
    compare_clusters,
    compare_pairs,
    compare_sets,
    compare_zwcad,
    crosscheck,
    drawing_sets,
    files,
    projects,
    system,
    xrefs,
)
from halo_engine.config import Settings

# Electron packaged app origin + the two Vite dev-server origins (docs/PLAN.md §3.7).
ALLOWED_ORIGINS = [
    "halocad://app",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# Reachable without a bearer token.
_PUBLIC_PATHS = frozenset({"/api/v1/system/health"})


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI app. ``settings=None`` reconstructs it from env (uvicorn --reload)."""
    settings = settings or Settings()

    app = FastAPI(title="halo_engine", version=__version__)
    app.state.settings = settings
    # Set by cli.serve() once the uvicorn Server exists, so /system/shutdown can stop it.
    app.state.server = None

    @app.middleware("http")
    async def _bearer_auth(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        token = request.app.state.settings.token
        if token is None or request.url.path in _PUBLIC_PATHS:
            return await call_next(request)
        # Constant-time comparison: a naive `!=` short-circuits on the first
        # mismatched character, which leaks the token's length and correct
        # prefix through response-time differences (timing attack).
        provided = request.headers.get("authorization")
        if provided is None or not secrets.compare_digest(provided, f"Bearer {token}"):
            return JSONResponse({"detail": "unauthorized"}, status_code=401)
        return await call_next(request)

    # Added last so it is outermost: CORS preflight (OPTIONS) is answered
    # before the auth middleware runs (Starlette runs middlewares in
    # reverse registration order).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router, prefix="/api/v1/system", tags=["system"])
    app.include_router(compare_zwcad.router, prefix="/api/v1/compare", tags=["compare"])
    app.include_router(compare_sets.router, prefix="/api/v1/compare", tags=["compare"])
    app.include_router(compare_pairs.router, prefix="/api/v1/compare", tags=["compare"])
    app.include_router(compare_clusters.router, prefix="/api/v1/compare", tags=["compare"])
    app.include_router(crosscheck.router, prefix="/api/v1/files", tags=["files"])
    app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
    app.include_router(drawing_sets.router, prefix="/api/v1", tags=["drawing-sets"])
    app.include_router(files.router, prefix="/api/v1/files", tags=["files"])
    app.include_router(xrefs.router, prefix="/api/v1", tags=["xrefs"])
    app.include_router(jobs.router, prefix="/api/v1/jobs", tags=["jobs"])
    app.include_router(ws.router, prefix="/api/v1", tags=["ws"])

    return app
