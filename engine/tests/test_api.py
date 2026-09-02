"""FastAPI app tests via httpx TestClient — no subprocess, no real socket."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from halo_engine.api.main import create_app
from halo_engine.config import Settings


def _client(tmp_path: Path, token: str | None = "secret") -> TestClient:
    settings = Settings(data_dir=tmp_path, dev=True, token=token)
    return TestClient(create_app(settings))


def test_health_ok_without_token(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/api/v1/system/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["deps"]["ezdxf"]
    assert body["deps"]["ifcopenshell"]
    assert body["deps"]["numpy"]


def test_capabilities_requires_token(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/api/v1/system/capabilities")
    assert resp.status_code == 401


def test_capabilities_with_valid_token(tmp_path: Path) -> None:
    resp = _client(tmp_path).get(
        "/api/v1/system/capabilities", headers={"Authorization": "Bearer secret"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["ifc_export"] is True
    assert body["dwg2dxf"] is False


def test_capabilities_wrong_token_rejected(tmp_path: Path) -> None:
    resp = _client(tmp_path).get(
        "/api/v1/system/capabilities", headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401
