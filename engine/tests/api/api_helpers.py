"""Shared TestClient / job-polling helpers for the ``tests/api`` suite.

Kept out of ``conftest.py`` (module-import, not a fixture) following the
same split as ``tests/validate/helpers.py``.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from halo_engine.api.jobs import get_job_manager
from halo_engine.api.main import create_app
from halo_engine.config import Settings

TOKEN = "dev"
AUTH_HEADERS = {"Authorization": f"Bearer {TOKEN}"}

#: brief W3-03 acceptance checks poll a real job; keep individual test runs fast.
JOB_POLL_TIMEOUT_S = 30.0
JOB_POLL_INTERVAL_S = 0.05

_TERMINAL_STATUSES = {"DONE", "FAILED", "CANCELLED"}


def make_app(tmp_path: Path, **settings_overrides: Any) -> Any:
    settings = Settings(data_dir=tmp_path / "data", dev=True, token=TOKEN, **settings_overrides)
    return create_app(settings)


def shutdown_app(app: Any) -> None:
    """Stop the app's ``ProcessPoolExecutor`` so its worker processes don't linger."""
    get_job_manager(app).shutdown()


def create_project(client: TestClient, tmp_path: Path, name: str = "t") -> dict[str, Any]:
    resp = client.post(
        "/api/v1/projects",
        json={"name": name, "path": str(tmp_path / f"{name}.halo")},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 201, resp.text
    return dict(resp.json())


def import_files(
    client: TestClient,
    project_id: str,
    files: list[str],
    *,
    search_paths: list[str] | None = None,
    converter_fallback: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"files": files, "search_paths": search_paths or []}
    if converter_fallback is not None:
        body["converter_fallback"] = converter_fallback
    resp = client.post(
        f"/api/v1/projects/{project_id}/drawing-sets", json=body, headers=AUTH_HEADERS
    )
    assert resp.status_code == 202, resp.text
    return dict(resp.json())


def wait_for_job(
    client: TestClient, job_id: str, *, timeout_s: float = JOB_POLL_TIMEOUT_S
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    job: dict[str, Any] = {}
    while time.monotonic() < deadline:
        resp = client.get(f"/api/v1/jobs/{job_id}", headers=AUTH_HEADERS)
        assert resp.status_code == 200, resp.text
        job = resp.json()
        if job["status"] in _TERMINAL_STATUSES:
            return job
        time.sleep(JOB_POLL_INTERVAL_S)
    raise AssertionError(f"job {job_id} did not reach a terminal status within {timeout_s}s: {job}")


def list_files(client: TestClient, drawing_set_id: str) -> list[dict[str, Any]]:
    resp = client.get(f"/api/v1/drawing-sets/{drawing_set_id}/files", headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    return list(resp.json())


__all__ = [
    "AUTH_HEADERS",
    "TOKEN",
    "create_project",
    "import_files",
    "list_files",
    "make_app",
    "shutdown_app",
    "wait_for_job",
]
