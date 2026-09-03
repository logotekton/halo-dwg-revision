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


def test_acad_ts_fallback_round_trips_an_attrib_drawing_after_writer_repair(
    generated_dir: Path, tmp_path: Path, acad_bridge_bin: Path
) -> None:
    """F06.dwg (ATTRIB-bearing) now imports through the acad-ts fallback.

    W3-08 repaired the acad-ts DXF writer (ATTRIB subclass/tag, duplicate SEQEND,
    MTEXT direction vector), so the engine reads its output. The one remaining
    acad-ts gap (an INSERT dropped when a block and a layer share a name, here
    X-TITLE) is invisible to the engine gate because the converter's own report
    and the engine count are both downstream of the same loss (85 instead of 86).
    The independent check is the viewer-side crosscheck against libredwg-web.
    """
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
            assert job["status"] == "DONE"

            row = list_files(client, created["drawing_set_id"])[0]
            assert row["import_status"] == "DONE", row
            assert row["working_dxf_path"]
            # Known acad-ts gap: X-TITLE INSERT is lost (86 -> 85). Keep this pinned so a
            # change in either direction is noticed.
            assert row["entity_count"] == 85, row["entity_count"]
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
