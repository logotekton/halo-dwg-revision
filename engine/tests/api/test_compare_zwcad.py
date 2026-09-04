"""``GET /api/v1/compare/zwcad/status`` (brief R1-02, docs/contracts/r1.md §7)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from api_helpers import AUTH_HEADERS, make_app, shutdown_app
from fastapi.testclient import TestClient


def test_zwcad_status_returns_200_with_expected_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/compare/zwcad/status", headers=AUTH_HEADERS)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert set(body.keys()) == {"available", "installed", "version", "prog_id", "reason"}
            assert body["available"] is False
            assert body["installed"] is False
            assert body["version"] is None
            assert body["prog_id"] is None
            assert body["reason"] == "not_windows"
    finally:
        shutdown_app(app)


def test_zwcad_status_requires_auth(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/compare/zwcad/status")
            assert resp.status_code == 401
    finally:
        shutdown_app(app)


def test_zwcad_status_reflects_registered_prog_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    from halo_engine.compare import zwcad

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(zwcad, "_find_registered_prog_id", lambda: "ZWCAD.Application.2026")
    monkeypatch.setitem(sys.modules, "comtypes", types.ModuleType("comtypes"))

    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            resp = client.get("/api/v1/compare/zwcad/status", headers=AUTH_HEADERS)
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body["available"] is True
            assert body["installed"] is True
            assert body["version"] == "2026"
            assert body["prog_id"] == "ZWCAD.Application.2026"
            assert body["reason"] is None
    finally:
        shutdown_app(app)
