"""``POST /jobs/{id}/cancel`` -- cooperative cancellation between files (brief: "취소 지원")."""

from __future__ import annotations

from pathlib import Path

from api_helpers import (
    AUTH_HEADERS,
    create_project,
    import_files,
    list_files,
    make_app,
    shutdown_app,
    wait_for_job,
)
from fastapi.testclient import TestClient


def test_cancel_unknown_job_is_404(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/jobs/nonexistent/cancel", headers=AUTH_HEADERS)
            assert resp.status_code == 404
    finally:
        shutdown_app(app)


def test_cancel_stops_the_job_before_every_file_is_processed(
    generated_dir: Path, tmp_path: Path
) -> None:
    """Cancel requested right after the job is created: it should not reach every file.

    Five copies of the same small DXF give the background task enough files
    that a cancel issued immediately after `create_drawing_set` returns
    reliably lands before the last one starts (cooperative: the running
    file finishes, the next one is never started).
    """
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            f06 = str(generated_dir / "F06.dxf")
            created = import_files(client, project["id"], [f06] * 5)

            cancel_resp = client.post(
                f"/api/v1/jobs/{created['job_id']}/cancel", headers=AUTH_HEADERS
            )
            assert cancel_resp.status_code == 200
            assert cancel_resp.json()["accepted"] is True

            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "CANCELLED"

            files = list_files(client, created["drawing_set_id"])
            statuses = [row["import_status"] for row in files]
            assert "PENDING" in statuses, statuses  # at least one file was never started
    finally:
        shutdown_app(app)


def test_cancel_after_job_is_done_is_not_accepted(generated_dir: Path, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(generated_dir / "F06.dxf")])
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"

            resp = client.post(f"/api/v1/jobs/{created['job_id']}/cancel", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["accepted"] is False
    finally:
        shutdown_app(app)
