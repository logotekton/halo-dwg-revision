"""``POST /api/v1/files/crosscheck`` — auth, validation, report shape."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from helpers import stats_document

from halo_engine.api.main import create_app
from halo_engine.config import Settings

TOKEN = "secret"
AUTH = {"Authorization": f"Bearer {TOKEN}"}

EZDXF = "engine.ezdxf"
MLIGHTCAD = "viewer.mlightcad"


def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(Settings(data_dir=tmp_path, dev=True, token=TOKEN)))


def one_bucket(producer: str, aggregate: dict[str, Any]) -> dict[str, Any]:
    return stats_document(producer=producer, buckets=[("MODEL", "X-GRID", aggregate)])


def test_requires_a_token(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        json={
            "reference": one_bucket(EZDXF, {"count_by_type": {"LINE": 1}}),
            "other": one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 1}}),
        },
    )
    assert response.status_code == 401


def test_green_report_for_identical_documents(tmp_path: Path) -> None:
    aggregate = {"count_by_type": {"LINE": 24}, "length_sum_mm": 5000.0}
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        headers=AUTH,
        json={"reference": one_bucket(EZDXF, aggregate), "other": one_bucket(MLIGHTCAD, aggregate)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "GREEN"
    assert body["red_layers"] == []
    assert body["reference"]["name"] == EZDXF
    assert body["other"]["name"] == MLIGHTCAD


def test_red_report_names_the_layer_and_the_cause(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        headers=AUTH,
        json={
            "reference": one_bucket(EZDXF, {"count_by_type": {"LINE": 24}}),
            "other": one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 22}}),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "RED"
    assert body["red_layers"] == ["X-GRID"]
    assert body["layers"][0]["differences"][0]["detail"] == "count_by_type.LINE 24→22"


def test_default_whitelist_is_used_and_reported(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        headers=AUTH,
        json={
            "reference": one_bucket(
                EZDXF, {"count_by_type": {"SPLINE": 1}, "length_sum_mm": 1000.0}
            ),
            "other": one_bucket(
                MLIGHTCAD, {"count_by_type": {"SPLINE": 1}, "length_sum_mm": 1110.0}
            ),
        },
    )
    body = response.json()
    assert body["status"] == "AMBER", body
    assert body["whitelist_path"] is not None
    difference = body["layers"][0]["differences"][0]
    assert difference["whitelist_id"] == "W01-mlightcad-spline-length"
    assert difference["whitelist_reason"]


def test_empty_whitelist_string_disables_the_downgrade(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        headers=AUTH,
        json={
            "reference": one_bucket(
                EZDXF, {"count_by_type": {"SPLINE": 1}, "length_sum_mm": 1000.0}
            ),
            "other": one_bucket(
                MLIGHTCAD, {"count_by_type": {"SPLINE": 1}, "length_sum_mm": 1110.0}
            ),
            "whitelist": "",
        },
    )
    body = response.json()
    assert body["status"] == "RED"
    assert body["whitelist_path"] is None


def test_missing_whitelist_file_is_422(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        headers=AUTH,
        json={
            "reference": one_bucket(EZDXF, {"count_by_type": {"LINE": 1}}),
            "other": one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 1}}),
            "whitelist": str(tmp_path / "nope.yaml"),
        },
    )
    assert response.status_code == 422


def test_malformed_whitelist_file_is_422_not_500(tmp_path: Path) -> None:
    path = tmp_path / "wl.yaml"
    path.write_text("entries:\n  - producer_pair: [a, b]\n    field: bbox\n", encoding="utf-8")
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        headers=AUTH,
        json={
            "reference": one_bucket(EZDXF, {"count_by_type": {"LINE": 1}}),
            "other": one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 1}}),
            "whitelist": str(path),
        },
    )
    assert response.status_code == 422
    assert "reason" in response.json()["detail"]


def test_a_body_that_is_not_a_stats_document_is_422(tmp_path: Path) -> None:
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        headers=AUTH,
        json={"reference": {"nope": 1}, "other": one_bucket(MLIGHTCAD, {})},
    )
    assert response.status_code == 422


def test_sha_mismatch_is_a_warning_not_an_error(tmp_path: Path) -> None:
    reference = one_bucket(EZDXF, {"count_by_type": {"LINE": 1}})
    other = one_bucket(MLIGHTCAD, {"count_by_type": {"LINE": 1}})
    other["file_sha256"] = "b" * 64
    response = client(tmp_path).post(
        "/api/v1/files/crosscheck",
        headers=AUTH,
        json={"reference": reference, "other": other},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "GREEN"
    assert body["file_sha256_mismatch"] is True
    assert body["warnings"]
