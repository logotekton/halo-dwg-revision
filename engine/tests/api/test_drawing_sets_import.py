"""``POST /projects/{id}/drawing-sets`` (DXF import) -> job -> files list.

The end-to-end vertical slice the brief's acceptance check names: F06.dxf in,
a ``DONE`` job, ``GET .../files`` shows ``working_dxf_path`` and the file is
readable back via ``GET /files/{id}/working-dxf`` and ``.../stats``.
"""

from __future__ import annotations

import json
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


def test_import_single_dxf_end_to_end(generated_dir: Path, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(generated_dir / "F06.dxf")])
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"
            assert job["progress"] == 1.0

            files = list_files(client, created["drawing_set_id"])
            assert len(files) == 1
            row = files[0]
            assert row["import_status"] == "DONE"
            assert row["original_name"] == "F06.dxf"
            assert row["format"] == "DXF"
            assert row["working_dxf_path"]
            assert row["entity_count"] and row["entity_count"] > 0
            assert row["error_message"] is None

            # working-dxf streams back the same bytes ingest wrote, with an ETag.
            resp = client.get(f"/api/v1/files/{row['id']}/working-dxf", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.headers.get("etag")
            assert Path(row["working_dxf_path"]).read_bytes() == resp.content

            # a conditional GET with the same ETag is a bare 304.
            resp2 = client.get(
                f"/api/v1/files/{row['id']}/working-dxf",
                headers={**AUTH_HEADERS, "if-none-match": resp.headers["etag"]},
            )
            assert resp2.status_code == 304

            # stats is the same LayerStatsDocument ingest computed.
            resp3 = client.get(f"/api/v1/files/{row['id']}/stats", headers=AUTH_HEADERS)
            assert resp3.status_code == 200
            stats = resp3.json()
            assert stats["totals"]["entity_count"] == row["entity_count"]
    finally:
        shutdown_app(app)


def test_import_f10_xref_set(generated_dir: Path, tmp_path: Path) -> None:
    """Two files in one drawing-set; the host's XREF resolves via the sibling in the same set."""
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(
                client,
                project["id"],
                [str(generated_dir / "F10_host.dxf"), str(generated_dir / "F10_grid.dxf")],
            )
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"

            files = {
                row["original_name"]: row for row in list_files(client, created["drawing_set_id"])
            }
            assert files["F10_host.dxf"]["import_status"] == "DONE"
            assert files["F10_grid.dxf"]["import_status"] == "DONE"

            resp = client.get(
                f"/api/v1/files/{files['F10_host.dxf']['id']}/stats", headers=AUTH_HEADERS
            )
            stats = resp.json()
            # The XREF got embedded: an INSERT of the grid block plus its content.
            assert stats["totals"]["count_by_type"].get("INSERT", 0) >= 1
    finally:
        shutdown_app(app)


def test_import_missing_file_fails_that_row_only(generated_dir: Path, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(
                client,
                project["id"],
                [str(generated_dir / "F06.dxf"), str(tmp_path / "does-not-exist.dxf")],
            )
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"  # the job itself completes; one row failed

            files = {
                row["original_name"]: row for row in list_files(client, created["drawing_set_id"])
            }
            assert files["F06.dxf"]["import_status"] == "DONE"
            assert files["does-not-exist.dxf"]["import_status"] == "FAILED"
            assert files["does-not-exist.dxf"]["error_message"]
    finally:
        shutdown_app(app)


def test_crosscheck_persists_on_drawing_file(generated_dir: Path, tmp_path: Path) -> None:
    """``POST /files/{id}/crosscheck`` compares against the engine's own stats and persists it."""
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(generated_dir / "F06.dxf")])
            wait_for_job(client, created["job_id"])
            row = list_files(client, created["drawing_set_id"])[0]
            assert row["parser_crosscheck"] is None

            engine_stats = json.loads(
                client.get(f"/api/v1/files/{row['id']}/stats", headers=AUTH_HEADERS).content
            )
            resp = client.post(
                f"/api/v1/files/{row['id']}/crosscheck",
                json={"other": engine_stats},  # comparing the doc against itself -> GREEN
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200, resp.text
            report = resp.json()
            assert report["status"] == "GREEN"

            row2 = list_files(client, created["drawing_set_id"])[0]
            assert row2["parser_crosscheck"] is not None
            assert row2["parser_crosscheck"]["status"] == "GREEN"
    finally:
        shutdown_app(app)


def test_drawing_set_for_wrong_project_is_404(generated_dir: Path, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            create_project(client, tmp_path)
            resp = client.post(
                "/api/v1/projects/not-open/drawing-sets",
                json={"files": [str(generated_dir / "F06.dxf")]},
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 404
    finally:
        shutdown_app(app)


def test_files_for_unknown_drawing_set_is_404(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            create_project(client, tmp_path)
            resp = client.get("/api/v1/drawing-sets/nonexistent/files", headers=AUTH_HEADERS)
            assert resp.status_code == 404
    finally:
        shutdown_app(app)
