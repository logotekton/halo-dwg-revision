"""``POST/GET /api/v1/compare/sets`` end-to-end (brief R1-03, contract §7).

Only DXF inputs here -- no converter runs at all (contract Definition of
done: "converter.before/after = null(DXF)"), so this suite needs neither
ZWCAD nor acad-ts. ``compare/ingest_set.py``'s own module-level tests
(``tests/compare/test_ingest_set.py``) cover the ZWCAD/builtin/fallback
machinery this router's job (``compare.ingest``) delegates to.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

from api_helpers import AUTH_HEADERS, make_app, shutdown_app, wait_for_job
from fastapi.testclient import TestClient

RUN_DATE = "2026-09-04"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_before_after(
    tmp_path: Path, generated_dir: Path, *, with_excluded: bool = False
) -> tuple[Path, Path]:
    """``<tmp_path>/project/{before,after}``, each with two DXF sheets (same
    two files on both sides -- R1-04's frame/pair matching is out of scope
    here). ``with_excluded`` adds one ``*_recover.dwg`` to the before side."""
    project_dir = tmp_path / "project"
    before_dir = project_dir / "before"
    after_dir = project_dir / "after"
    before_dir.mkdir(parents=True)
    after_dir.mkdir(parents=True)
    shutil.copyfile(generated_dir / "F06.dxf", before_dir / "A-101.dxf")
    shutil.copyfile(generated_dir / "F02.dxf", before_dir / "A-102.dxf")
    shutil.copyfile(generated_dir / "F06.dxf", after_dir / "A-101.dxf")
    shutil.copyfile(generated_dir / "F02.dxf", after_dir / "A-102.dxf")
    if with_excluded:
        (before_dir / "A-103_recover.dwg").write_bytes(b"placeholder, never opened")
    return before_dir, after_dir


def _post_compare_set(
    client: TestClient,
    *,
    before_dir: Path,
    after_dir: Path,
    project_dir: Path | None = None,
    run_date: str = RUN_DATE,
    options: dict[str, Any] | None = None,
) -> Any:
    body: dict[str, Any] = {
        "before_dir": str(before_dir),
        "after_dir": str(after_dir),
        "run_date": run_date,
    }
    if project_dir is not None:
        body["project_dir"] = str(project_dir)
    if options is not None:
        body["options"] = options
    return client.post("/api/v1/compare/sets", json=body, headers=AUTH_HEADERS)


def test_two_dxf_folders_end_to_end(generated_dir: Path, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            before_dir, after_dir = _make_before_after(tmp_path, generated_dir, with_excluded=True)

            resp = _post_compare_set(client, before_dir=before_dir, after_dir=after_dir)
            assert resp.status_code == 202, resp.text
            created = resp.json()
            assert set(created) == {"compare_set_id", "project_id", "job_id"}

            job = wait_for_job(client, created["job_id"], timeout_s=60.0)
            assert job["status"] == "DONE", job
            assert job["kind"] == "compare.ingest"
            assert job["compare_set_id"] == created["compare_set_id"]

            resp2 = client.get(
                f"/api/v1/compare/sets/{created['compare_set_id']}", headers=AUTH_HEADERS
            )
            assert resp2.status_code == 200, resp2.text
            summary = resp2.json()
            assert summary["status"] == "ingested"
            assert summary["project_id"] == created["project_id"]
            assert summary["before"]["files"] == 3  # 2 sheets + 1 excluded
            assert summary["before"]["converted"] == 2
            assert summary["before"]["excluded"] == 1
            assert summary["before"]["failed"] == 0
            assert summary["after"]["files"] == 2
            assert summary["after"]["converted"] == 2
            assert summary["after"]["excluded"] == 0
            # DXF-only inputs: no converter ran on either side (contract DoD).
            assert summary["converter"] == {"before": None, "after": None, "mismatch_files": 0}
            assert summary["frames"] is None  # R1-04 has not run yet
            assert summary["pairs"] is None
            assert summary["last_job_id"] == created["job_id"]
            assert isinstance(summary["fonts_missing"], list)
            assert summary["crosscheck"] == {"sampled": 0, "mismatched": 0}
            assert "available" in summary["zwcad"]

            files_resp = client.get(
                f"/api/v1/compare/sets/{created['compare_set_id']}/files", headers=AUTH_HEADERS
            )
            assert files_resp.status_code == 200
            files = files_resp.json()
            assert len(files) == 5
            by_name = {f["original_name"]: f for f in files}
            assert by_name["A-101.dxf"]["import_status"] == "DONE"
            assert by_name["A-101.dxf"]["converter"] is None
            excluded = by_name["A-103_recover.dwg"]
            assert excluded["import_status"] == "EXCLUDED"
            assert excluded["excluded_reason"] == "ignore_pattern"
            assert excluded["role"] == "before"

            list_resp = client.get("/api/v1/compare/sets", headers=AUTH_HEADERS)
            assert list_resp.status_code == 200
            ids = [row["id"] for row in list_resp.json()]
            assert created["compare_set_id"] in ids
    finally:
        shutdown_app(app)


def test_same_project_ingested_twice_hits_the_sha_cache(
    generated_dir: Path, tmp_path: Path
) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            before_dir, after_dir = _make_before_after(tmp_path, generated_dir)
            project_dir = before_dir.parent

            first = _post_compare_set(
                client, before_dir=before_dir, after_dir=after_dir, project_dir=project_dir
            )
            assert first.status_code == 202, first.text
            wait_for_job(client, first.json()["job_id"], timeout_s=60.0)

            second = _post_compare_set(
                client, before_dir=before_dir, after_dir=after_dir, project_dir=project_dir
            )
            assert second.status_code == 202, second.text
            wait_for_job(client, second.json()["job_id"], timeout_s=60.0)

            files_resp = client.get(
                f"/api/v1/compare/sets/{second.json()['compare_set_id']}/files",
                headers=AUTH_HEADERS,
            )
            files = files_resp.json()
            assert files and all(f["import_status"] == "DONE" for f in files)
            assert any((f.get("converter_meta") or {}).get("cache_hit") is True for f in files)
    finally:
        shutdown_app(app)


def test_source_files_are_never_written_to(generated_dir: Path, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            before_dir, after_dir = _make_before_after(tmp_path, generated_dir, with_excluded=True)

            def _snapshot(directory: Path) -> dict[Path, tuple[int, str]]:
                return {p: (p.stat().st_mtime_ns, _sha256(p)) for p in sorted(directory.iterdir())}

            before_snapshot = _snapshot(before_dir)
            after_snapshot = _snapshot(after_dir)
            assert before_snapshot and after_snapshot  # sanity: files actually exist

            resp = _post_compare_set(client, before_dir=before_dir, after_dir=after_dir)
            assert resp.status_code == 202, resp.text
            wait_for_job(client, resp.json()["job_id"], timeout_s=60.0)

            for path, (mtime_ns, sha) in {**before_snapshot, **after_snapshot}.items():
                assert path.stat().st_mtime_ns == mtime_ns, f"{path} mtime changed"
                assert _sha256(path) == sha, f"{path} content changed"
    finally:
        shutdown_app(app)


def test_project_dir_defaults_to_common_parent(generated_dir: Path, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            before_dir, after_dir = _make_before_after(tmp_path, generated_dir)
            resp = _post_compare_set(client, before_dir=before_dir, after_dir=after_dir)
            assert resp.status_code == 202, resp.text
            created = resp.json()
            wait_for_job(client, created["job_id"], timeout_s=60.0)

            summary = client.get(
                f"/api/v1/compare/sets/{created['compare_set_id']}", headers=AUTH_HEADERS
            ).json()
            assert summary["project_dir"] == str(before_dir.parent)
    finally:
        shutdown_app(app)


def test_missing_before_dir_is_422(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = _post_compare_set(
                client, before_dir=tmp_path / "does-not-exist", after_dir=tmp_path
            )
            assert resp.status_code == 422
    finally:
        shutdown_app(app)


def test_missing_after_dir_is_422(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = _post_compare_set(
                client, before_dir=tmp_path, after_dir=tmp_path / "does-not-exist"
            )
            assert resp.status_code == 422
    finally:
        shutdown_app(app)


def test_bad_run_date_is_422(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = _post_compare_set(
                client, before_dir=tmp_path, after_dir=tmp_path, run_date="04-09-2026"
            )
            assert resp.status_code == 422
    finally:
        shutdown_app(app)


def test_unknown_compare_set_is_404(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/compare/sets/nonexistent", headers=AUTH_HEADERS)
            assert resp.status_code == 404
            resp2 = client.get("/api/v1/compare/sets/nonexistent/files", headers=AUTH_HEADERS)
            assert resp2.status_code == 404
    finally:
        shutdown_app(app)


def test_ws_progress_carries_kind_and_stage(generated_dir: Path, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            before_dir, after_dir = _make_before_after(tmp_path, generated_dir)
            with client.websocket_connect("/api/v1/ws") as ws:
                ws.send_json({"type": "auth", "token": "dev"})

                resp = _post_compare_set(client, before_dir=before_dir, after_dir=after_dir)
                assert resp.status_code == 202, resp.text
                created = resp.json()

                seen_convert_progress = False
                message = ws.receive_json()
                while message.get("type") != "job.done":
                    if message.get("type") == "job.progress" and message.get("stage") == "convert":
                        assert message["kind"] == "compare.ingest"
                        assert message["compare_set_id"] == created["compare_set_id"]
                        seen_convert_progress = True
                    message = ws.receive_json()
                assert seen_convert_progress
                assert message["kind"] == "compare.ingest"
                assert message["compare_set_id"] == created["compare_set_id"]
    finally:
        shutdown_app(app)
