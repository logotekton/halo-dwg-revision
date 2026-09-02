"""FastAPI app tests via httpx TestClient — no subprocess, no real socket."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
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


def test_capabilities_missing_authorization_header_rejected(tmp_path: Path) -> None:
    resp = _client(tmp_path).get("/api/v1/system/capabilities")
    assert resp.status_code == 401


def test_capabilities_near_miss_token_rejected(tmp_path: Path) -> None:
    # Shares a long prefix with the real token. A naive `!=` also rejects
    # this, but it guards against a future regression silently swapping
    # back to a short-circuiting comparison.
    resp = _client(tmp_path).get(
        "/api/v1/system/capabilities", headers={"Authorization": "Bearer secre0"}
    )
    assert resp.status_code == 401


def test_capabilities_auth_uses_constant_time_comparison(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Guards against a regression back to a `!=` timing-unsafe comparison."""
    calls: list[tuple[str, str]] = []
    original = secrets.compare_digest

    def spy(a: str, b: str) -> bool:
        calls.append((a, b))
        return bool(original(a, b))

    monkeypatch.setattr("halo_engine.api.main.secrets.compare_digest", spy)

    resp = _client(tmp_path).get(
        "/api/v1/system/capabilities", headers={"Authorization": "Bearer secret"}
    )

    assert resp.status_code == 200
    assert calls == [("Bearer secret", "Bearer secret")]
