"""``/api/v1/ws`` auth and the ``convert.request`` -> ``POST /files/{id}/converted`` round trip."""

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


def test_ws_event_order_for_a_single_file_dxf_import(generated_dir: Path, tmp_path: Path) -> None:
    """job.progress(0.0) -> job.progress(1.0) -> job.done, no other frames interleaved."""
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            with client.websocket_connect("/api/v1/ws") as ws:
                ws.send_json({"type": "auth", "token": "dev"})

                created = import_files(client, project["id"], [str(generated_dir / "F06.dxf")])

                first = ws.receive_json()
                second = ws.receive_json()
                third = ws.receive_json()

            assert first == {
                "type": "job.progress",
                "job_id": created["job_id"],
                "progress": 0.0,
                "message": "importing",
            }
            assert second == {
                "type": "job.progress",
                "job_id": created["job_id"],
                "progress": 1.0,
                "message": "1/1",
            }
            assert third == {
                "type": "job.done",
                "job_id": created["job_id"],
                "drawing_set_id": created["drawing_set_id"],
            }

            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"
    finally:
        shutdown_app(app)


def test_ws_rejects_missing_auth_frame(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/ws") as ws:
                ws.send_json({"type": "not-auth"})
                # the server closes the socket; receiving raises WebSocketDisconnect.
                import pytest
                from starlette.websockets import WebSocketDisconnect

                with pytest.raises(WebSocketDisconnect):
                    ws.receive_json()
    finally:
        shutdown_app(app)


def test_ws_rejects_wrong_token(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/ws") as ws:
                ws.send_json({"type": "auth", "token": "wrong"})
                import pytest
                from starlette.websockets import WebSocketDisconnect

                with pytest.raises(WebSocketDisconnect):
                    ws.receive_json()
    finally:
        shutdown_app(app)


def test_ws_accepts_correct_token(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/ws") as ws:
                ws.send_json({"type": "auth", "token": "dev"})
                # No further frame is sent by the server on connect; closing
                # cleanly (no exception) is the assertion.
    finally:
        shutdown_app(app)


def test_convert_request_round_trip_with_fake_converter(
    generated_dir: Path, tmp_path: Path
) -> None:
    """A DWG import asks a connected 'desktop' to convert it, and consumes its answer.

    Uses F06.dxf as a stand-in for what a real converter would have written
    for F06.dwg, with the entity count the engine itself computes for that
    DXF (86) so the crosscheck gate (ADR-0002 amendment 4c) passes.
    """
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)

            with client.websocket_connect("/api/v1/ws") as ws:
                ws.send_json({"type": "auth", "token": "dev"})

                created = import_files(client, project["id"], [str(generated_dir / "F06.dwg")])

                message = ws.receive_json()
                while message.get("type") != "convert.request":
                    message = ws.receive_json()
                assert message["file_id"]
                assert message["dwg_path"] == str(generated_dir / "F06.dwg")
                assert message["out_path"]

                resp = client.post(
                    f"/api/v1/files/{message['file_id']}/converted",
                    json={
                        "dxf_path": str(generated_dir / "F06.dxf"),
                        "entity_count": 86,
                        "converter": "mlightcad-dxfout",
                    },
                    headers=AUTH_HEADERS,
                )
                assert resp.status_code == 200
                assert resp.json()["accepted"] is True

                # drain until job.done so the socket doesn't outlive the `with` block mid-broadcast
                message = ws.receive_json()
                while message.get("type") != "job.done":
                    message = ws.receive_json()

            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"

            row = list_files(client, created["drawing_set_id"])[0]
            assert row["import_status"] == "DONE"
            assert row["format"] == "DWG"
            assert row["working_dxf_path"]
    finally:
        shutdown_app(app)


def test_converted_for_unknown_file_is_404(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            create_project(client, tmp_path)
            resp = client.post(
                "/api/v1/files/nonexistent/converted",
                json={"dxf_path": "/tmp/x.dxf", "entity_count": 1, "converter": "acad-ts"},
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 404
    finally:
        shutdown_app(app)


def test_converted_with_nothing_waiting_is_accepted_false(
    generated_dir: Path, tmp_path: Path
) -> None:
    """A late/duplicate `converted` POST (nothing pending) is reported, not an error."""
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(generated_dir / "F06.dxf")])
            wait_for_job(client, created["job_id"])
            row = list_files(client, created["drawing_set_id"])[0]

            resp = client.post(
                f"/api/v1/files/{row['id']}/converted",
                json={
                    "dxf_path": str(generated_dir / "F06.dxf"),
                    "entity_count": 1,
                    "converter": "acad-ts",
                },
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200
            assert resp.json()["accepted"] is False
    finally:
        shutdown_app(app)


def test_dwg_import_with_no_desktop_and_no_fallback_needs_manual_conversion(
    generated_dir: Path, tmp_path: Path
) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(generated_dir / "F06.dwg")])
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"

            row = list_files(client, created["drawing_set_id"])[0]
            assert row["import_status"] == "NEEDS_MANUAL_CONVERSION"
            assert row["error_message"]
    finally:
        shutdown_app(app)
