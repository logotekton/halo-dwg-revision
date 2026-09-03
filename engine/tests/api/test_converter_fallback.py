"""``--converter-fallback acad-ts``: the engine runs the acad-ts CLI itself, as a
subprocess, when no desktop is connected over WS (brief W3-03).

Needs the built acad-bridge CLI (``pnpm --filter @halo-cad/acad-bridge
build``); skipped otherwise via the ``acad_bridge_bin`` fixture.

F10_host.dwg is a fixture the acad-ts DXF writer round-trips cleanly.
F06.dwg is not: acad-ts's DXF output has known gaps ezdxf's loader chokes on
(ADR-0002's 2026-09-02 amendment, decision 1 -- "acad-ts가 쓴 DXF는 ezdxf가
읽지 못한다": missing ATTRIB subclass markers, duplicate handles). That is
exactly why the amendment demoted acad-ts to a fallback in the first place;
this test asserts the pipeline *fails safe* on it (`NEEDS_MANUAL_CONVERSION`
with a reason), not that acad-ts becomes reliable.
"""

from __future__ import annotations

from pathlib import Path

from api_helpers import (
    create_project,
    import_files,
    list_files,
    make_app,
    shutdown_app,
    wait_for_job,
)
from fastapi.testclient import TestClient


def test_acad_ts_fallback_succeeds_on_a_clean_dwg(
    generated_dir: Path, tmp_path: Path, acad_bridge_bin: Path
) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(
                client,
                project["id"],
                [str(generated_dir / "F10_host.dwg")],
                converter_fallback="acad-ts",
            )
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"

            row = list_files(client, created["drawing_set_id"])[0]
            assert row["import_status"] == "DONE", row
            assert row["working_dxf_path"]
            assert row["entity_count"] and row["entity_count"] > 0
    finally:
        shutdown_app(app)


def test_acad_ts_fallback_fails_safe_on_a_dxf_it_cannot_round_trip(
    generated_dir: Path, tmp_path: Path, acad_bridge_bin: Path
) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(
                client,
                project["id"],
                [str(generated_dir / "F06.dwg")],
                converter_fallback="acad-ts",
            )
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"  # the job completes; this one row needs manual help

            row = list_files(client, created["drawing_set_id"])[0]
            assert row["import_status"] == "NEEDS_MANUAL_CONVERSION"
            assert "acad-ts" in row["error_message"]
    finally:
        shutdown_app(app)


def test_per_request_converter_fallback_overrides_server_default(
    generated_dir: Path, tmp_path: Path, acad_bridge_bin: Path
) -> None:
    """The server has no default fallback configured; the request's own field still enables it."""
    app = make_app(tmp_path)  # no converter_fallback in Settings
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(
                client,
                project["id"],
                [str(generated_dir / "F10_host.dwg")],
                converter_fallback="acad-ts",
            )
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"
            row = list_files(client, created["drawing_set_id"])[0]
            assert row["import_status"] == "DONE"
    finally:
        shutdown_app(app)


def test_server_default_converter_fallback_applies_without_a_per_request_flag(
    generated_dir: Path, tmp_path: Path, acad_bridge_bin: Path
) -> None:
    app = make_app(tmp_path, converter_fallback="acad-ts")
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(generated_dir / "F10_host.dwg")])
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"
            row = list_files(client, created["drawing_set_id"])[0]
            assert row["import_status"] == "DONE"
    finally:
        shutdown_app(app)
