"""``POST /projects``, ``POST /projects/open``, ``GET /projects/recent``, ``GET /projects/{id}``."""

from __future__ import annotations

from pathlib import Path

import pytest
from api_helpers import AUTH_HEADERS, create_project, make_app, shutdown_app
from fastapi.testclient import TestClient


def test_create_project_creates_bundle_and_opens_it(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            body = create_project(client, tmp_path, "alpha")
            bundle_path = Path(body["bundle_path"])
            assert bundle_path.is_dir()
            assert (bundle_path / "project.json").is_file()
            assert (bundle_path / "project.sqlite").is_file()
            assert (bundle_path / "originals").is_dir()
            assert (bundle_path / "cache" / "dxf").is_dir()

            resp = client.get(f"/api/v1/projects/{body['id']}", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert resp.json()["name"] == "alpha"
            assert resp.json()["bundle_path"] == str(bundle_path)
    finally:
        shutdown_app(app)


def test_create_project_without_path_uses_default_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import halo_engine.bundle.create as create_mod

    default_root = tmp_path / "Documents" / "Halo CAD"
    monkeypatch.setattr(
        create_mod, "default_bundle_path", lambda name: default_root / f"{name}.halo"
    )

    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = client.post("/api/v1/projects", json={"name": "no-path"}, headers=AUTH_HEADERS)
            assert resp.status_code == 201, resp.text
            assert resp.json()["bundle_path"] == str(default_root / "no-path.halo")
    finally:
        shutdown_app(app)


def test_open_existing_project_round_trip(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            created = create_project(client, tmp_path, "beta")

            # A second app instance simulates a fresh engine process opening
            # a bundle a previous run created.
            app2 = make_app(tmp_path)
            try:
                with TestClient(app2) as client2:
                    resp = client2.post(
                        "/api/v1/projects/open",
                        json={"bundle_path": created["bundle_path"]},
                        headers=AUTH_HEADERS,
                    )
                    assert resp.status_code == 200, resp.text
                    assert resp.json()["id"] == created["id"]
            finally:
                shutdown_app(app2)
    finally:
        shutdown_app(app)


def test_open_missing_bundle_is_404(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/projects/open",
                json={"bundle_path": str(tmp_path / "nope.halo")},
                headers=AUTH_HEADERS,
            )
            assert resp.status_code == 404
    finally:
        shutdown_app(app)


def test_recent_projects_lists_created_and_opened_bundles(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            create_project(client, tmp_path, "gamma")
            create_project(client, tmp_path, "delta")

            resp = client.get("/api/v1/projects/recent", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            names = {entry["name"] for entry in resp.json()}
            assert names == {"gamma", "delta"}
    finally:
        shutdown_app(app)


def test_recent_projects_persists_across_engine_restarts(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            create_project(client, tmp_path, "epsilon")
    finally:
        shutdown_app(app)

    app2 = make_app(tmp_path)  # same data_dir -> same recent-projects.json
    try:
        with TestClient(app2) as client2:
            resp = client2.get("/api/v1/projects/recent", headers=AUTH_HEADERS)
            assert resp.status_code == 200
            assert {e["name"] for e in resp.json()} == {"epsilon"}
    finally:
        shutdown_app(app2)


def test_get_project_without_any_open_project_is_409(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/projects/nonexistent-id", headers=AUTH_HEADERS)
            assert resp.status_code == 409
    finally:
        shutdown_app(app)


def test_get_project_wrong_id_is_404(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            create_project(client, tmp_path, "zeta")
            resp = client.get("/api/v1/projects/not-the-open-one", headers=AUTH_HEADERS)
            assert resp.status_code == 404
    finally:
        shutdown_app(app)
