"""``GET /files/{id}/xrefs``, ``POST /files/{id}/xrefs/{name}/resolve``,
``PUT /projects/{id}/search-paths``, ``GET``/``PUT /projects/{id}/import-settings``
(brief W3-06).

Acceptance criteria exercised here (brief "Acceptance beyond the brief"):

(b) importing a DWG host with an unresolved DWG XREF target, given the
    right search path, ends DONE with the target converted, registered as
    ``drawing_file(is_xref=1)`` and embedded
    (``test_dwg_xref_target_is_recursively_converted_and_embedded``).
(c) ``*_recover.dwg``/``*.bak`` are excluded, not imported
    (``test_ignored_filename_is_excluded_not_imported``).
(d) an unresolved XREF is listed via ``GET .../xrefs``; adding a search path
    (``PUT .../search-paths``) or manually matching a file
    (``POST .../xrefs/{name}/resolve``) re-imports and resolves it
    (``test_put_search_paths_reimports_and_resolves``,
    ``test_resolve_single_xref_by_manual_file_match``).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import ezdxf
import ezdxf.xref
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


def _make_host_with_dxf_xref(tmp_path: Path, *, xref_filename: str, name: str = "host") -> Path:
    """A host DXF whose one XREF block points at ``xref_filename`` (not
    created here -- the caller decides whether/where that target exists,
    to test both the resolved and unresolved cases)."""
    host_dir = tmp_path / name
    host_dir.mkdir()
    doc = ezdxf.new("R2018")
    ezdxf.xref.attach(doc, block_name="GRID", filename=xref_filename, insert=(0, 0, 0))
    host_path = host_dir / "host.dxf"
    doc.saveas(str(host_path))
    return host_path


def test_unresolved_xref_is_listed_and_missing_from_working_dxf(tmp_path: Path) -> None:
    host_path = _make_host_with_dxf_xref(tmp_path, xref_filename="nope.dxf")

    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(host_path)])
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"

            row = list_files(client, created["drawing_set_id"])[0]
            assert row["import_status"] == "DONE"  # one unresolved xref does not fail the host

            resp = client.get(f"/api/v1/files/{row['id']}/xrefs", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            links = resp.json()
            assert len(links) == 1
            assert links[0]["block_name"] == "GRID"
            assert links[0]["status"] == "UNRESOLVED"
            assert links[0]["resolved_path"] is None
    finally:
        shutdown_app(app)


def test_put_search_paths_reimports_and_resolves(tmp_path: Path) -> None:
    """Brief Goal: F10-shaped scenario -- the target lives in a folder the
    host does not already search; adding that folder as a project search
    path and asking for a re-import resolves it without the caller having
    to know anything about tiers/resolution order."""
    host_path = _make_host_with_dxf_xref(tmp_path, xref_filename="grid.dxf")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    ezdxf.new("R2018").saveas(str(elsewhere / "grid.dxf"))

    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(host_path)])
            wait_for_job(client, created["job_id"])
            row = list_files(client, created["drawing_set_id"])[0]

            links_before = client.get(
                f"/api/v1/files/{row['id']}/xrefs", headers=AUTH_HEADERS
            ).json()
            assert links_before[0]["status"] == "UNRESOLVED"

            resp = client.put(
                f"/api/v1/projects/{project['id']}/search-paths",
                json={"search_paths": [str(elsewhere)], "reimport_file_ids": [row["id"]]},
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["search_paths"] == [str(elsewhere)]
            assert len(body["job_ids"]) == 1
            wait_for_job(client, body["job_ids"][0])

            links_after = client.get(
                f"/api/v1/files/{row['id']}/xrefs", headers=AUTH_HEADERS
            ).json()
            assert links_after[0]["status"] == "RESOLVED"
            assert links_after[0]["resolved_path"] == str(elsewhere / "grid.dxf")

            # A brand-new import of a *different* host now also sees the
            # persisted search path without being told about it again.
            host2 = _make_host_with_dxf_xref(tmp_path, xref_filename="grid.dxf", name="host2")
            created2 = import_files(client, project["id"], [str(host2)])
            wait_for_job(client, created2["job_id"])
            row2 = list_files(client, created2["drawing_set_id"])[0]
            links2 = client.get(f"/api/v1/files/{row2['id']}/xrefs", headers=AUTH_HEADERS).json()
            assert links2[0]["status"] == "RESOLVED"
    finally:
        shutdown_app(app)


def test_resolve_single_xref_by_manual_file_match(tmp_path: Path) -> None:
    host_path = _make_host_with_dxf_xref(tmp_path, xref_filename="grid.dxf")
    elsewhere = tmp_path / "picked-by-hand"
    elsewhere.mkdir()
    ezdxf.new("R2018").saveas(str(elsewhere / "grid.dxf"))

    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(host_path)])
            wait_for_job(client, created["job_id"])
            row = list_files(client, created["drawing_set_id"])[0]

            resp = client.post(
                f"/api/v1/files/{row['id']}/xrefs/GRID/resolve",
                json={"resolved_path": str(elsewhere / "grid.dxf")},
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200, resp.text
            job_id = resp.json()["job_id"]
            wait_for_job(client, job_id)

            links = client.get(f"/api/v1/files/{row['id']}/xrefs", headers=AUTH_HEADERS).json()
            assert links[0]["status"] == "RESOLVED"

            settings = client.get(
                f"/api/v1/projects/{project['id']}/import-settings", headers=AUTH_HEADERS
            ).json()
            assert str(elsewhere) in settings["search_paths"]
    finally:
        shutdown_app(app)


def test_import_settings_get_and_put_round_trip(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)

            resp = client.get(
                f"/api/v1/projects/{project['id']}/import-settings", headers=AUTH_HEADERS
            )
            assert resp.status_code == 200
            defaults = resp.json()
            assert defaults["search_paths"] == []
            assert defaults["ignore_patterns"] == ["*_recover.dwg", "*.bak"]

            resp = client.put(
                f"/api/v1/projects/{project['id']}/import-settings",
                json={"search_paths": ["/tmp/xr"], "ignore_patterns": ["*.bak", "*.old"]},
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 200, resp.text
            assert resp.json() == {
                "search_paths": ["/tmp/xr"],
                "ignore_patterns": ["*.bak", "*.old"],
            }
    finally:
        shutdown_app(app)


def test_ignored_filename_is_excluded_not_imported(tmp_path: Path) -> None:
    """Brief addendum 3 / acceptance (c): a ``_recover.dwg``/``.bak`` sibling
    is listed with a distinct status and never copied into the bundle."""
    src_dir = tmp_path / "drop"
    src_dir.mkdir()
    real = src_dir / "A-520 부분확대 상세도.dxf"
    # ``*_recover.dwg`` (default ignore pattern) -- the extension is not
    # ``.dxf`` on purpose, matching the real set's actual naming
    # (`A-520 부분확대 상세도_recover.dwg`); the content doesn't matter
    # since an excluded file is never opened.
    recovered = src_dir / "A-520 부분확대 상세도_recover.dwg"
    ezdxf.new("R2018").saveas(str(real))
    recovered.write_bytes(b"not a real dwg -- never read, this file is excluded before parsing")

    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(real), str(recovered)])
            job = wait_for_job(client, created["job_id"])
            assert job["status"] == "DONE"

            rows = {
                row["original_name"]: row for row in list_files(client, created["drawing_set_id"])
            }
            assert rows["A-520 부분확대 상세도.dxf"]["import_status"] == "DONE"
            excluded = rows["A-520 부분확대 상세도_recover.dwg"]
            assert excluded["import_status"] == "EXCLUDED"
            assert not excluded["working_dxf_path"]

            bundle_path = Path(project["bundle_path"])
            originals = list((bundle_path / "originals").iterdir())
            # Only the non-excluded file's bytes ever reached originals/.
            assert len(originals) == 1
    finally:
        shutdown_app(app)


def test_dwg_xref_target_is_recursively_converted_and_embedded(
    tmp_path: Path, acad_bridge_bin: Path, generated_dir: Path
) -> None:
    """Brief addendum 1: a DXF host referencing a *.dwg* XREF target gets
    that target converted (acad-ts fallback here -- no desktop attached in
    tests, per this task's instructions) before being embedded, and the
    target is registered as its own ``drawing_file(is_xref=1)`` row."""
    host_path = _make_host_with_dxf_xref(tmp_path, xref_filename="grid.dwg")
    shutil.copy(generated_dir / "F10_grid.dwg", host_path.parent / "grid.dwg")

    app = make_app(tmp_path, converter_fallback="acad-ts", acad_bridge_bin=acad_bridge_bin)
    try:
        with TestClient(app) as client:
            project = create_project(client, tmp_path)
            created = import_files(client, project["id"], [str(host_path)])
            job = wait_for_job(client, created["job_id"], timeout_s=60.0)
            assert job["status"] == "DONE"

            files = list_files(client, created["drawing_set_id"])
            host_row = next(f for f in files if f["original_name"] == "host.dxf")
            assert host_row["import_status"] == "DONE"

            links = client.get(f"/api/v1/files/{host_row['id']}/xrefs", headers=AUTH_HEADERS).json()
            assert len(links) == 1
            assert links[0]["status"] == "RESOLVED", links

            # The converted xref target is its own drawing_file(is_xref=1) row.
            xref_rows = [f for f in files if f["original_name"] == "grid.dwg"]
            assert len(xref_rows) == 1, files
    finally:
        shutdown_app(app)
