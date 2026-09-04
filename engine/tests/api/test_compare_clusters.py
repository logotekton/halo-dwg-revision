"""``POST /compare/sets/{id}/run`` and the cluster endpoints, end to end (contract §7).

Driven through the real pipeline the app uses: two folders in, ``compare.ingest``
builds the working DXFs, ``compare.frames`` cuts them into 도곽 and pairs them,
``compare.run`` diffs every pair and writes the two files, and the review
screen's three endpoints serve and edit the result over HTTP.

``tests/compare/test_scenarios.py`` is where the comparison *rules* are proved
against the truth files; what is proved here is the plumbing around them --
the job envelope, the statuses, the skipping, the carry-over of a review across
a re-run, and the bytes the viewer will fetch.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from api_helpers import AUTH_HEADERS, make_app, shutdown_app, wait_for_job
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "fixtures" / "compare"
SCHEMA_SRC = REPO_ROOT / "packages" / "schema" / "src"
RUN_DATE = "2026-09-04"


def _scenario(name: str, tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    """Copy one fixture scenario into ``tmp_path`` and read its truth file.

    Copied because the ingest job writes ``<project>/.halo`` next to the two set
    folders, and ``fixtures/`` is neither this task's to write nor somewhere a
    test may leave litter (CLAUDE.md rule 1).
    """
    source = FIXTURES / name
    if not (source / "truth.json").is_file():
        pytest.skip(f"{source} missing -- run the fixture generator")
    project = tmp_path / "project"
    shutil.copytree(source / "before", project / "before")
    shutil.copytree(source / "after", project / "after")
    truth = json.loads((source / "truth.json").read_text(encoding="utf-8"))
    return project / "before", project / "after", truth


def _prepare(client: TestClient, name: str, tmp_path: Path) -> tuple[str, dict[str, Any]]:
    """Ingest and match one scenario, leaving the compare set ready to run."""
    before, after, truth = _scenario(name, tmp_path)
    resp = client.post(
        "/api/v1/compare/sets",
        json={"before_dir": str(before), "after_dir": str(after), "run_date": RUN_DATE},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 202, resp.text
    created = resp.json()
    assert wait_for_job(client, created["job_id"], timeout_s=60.0)["status"] == "DONE"

    compare_set_id = str(created["compare_set_id"])
    resp = client.post(f"/api/v1/compare/sets/{compare_set_id}/frames", headers=AUTH_HEADERS)
    assert resp.status_code == 202, resp.text
    assert wait_for_job(client, resp.json()["job_id"], timeout_s=120.0)["status"] == "DONE"
    return compare_set_id, truth


def _run(client: TestClient, compare_set_id: str, **body: Any) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/compare/sets/{compare_set_id}/run",
        json=body or None,
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 202, resp.text
    job = wait_for_job(client, resp.json()["job_id"], timeout_s=180.0)
    assert job["status"] == "DONE", job
    assert job["kind"] == "compare.run"
    assert job["compare_set_id"] == compare_set_id
    return dict(job)


def _pairs(client: TestClient, compare_set_id: str) -> list[dict[str, Any]]:
    resp = client.get(f"/api/v1/compare/sets/{compare_set_id}/pairs", headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    return list(resp.json())


@pytest.fixture
def client(tmp_path: Path) -> Any:
    app = make_app(tmp_path)
    with TestClient(app) as test_client:
        yield test_client
    shutdown_app(app)


# --------------------------------------------------------------------------- the run


def test_a_run_compares_every_pair_and_leaves_the_set_compared(
    client: TestClient, tmp_path: Path
) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    _run(client, compare_set_id)

    summary = client.get(f"/api/v1/compare/sets/{compare_set_id}", headers=AUTH_HEADERS).json()
    assert summary["status"] == "compared"
    # The frames job left the sheet `pending`; the summary has to say what it is now.
    assert summary["pairs"]["changed"] == 1
    assert summary["pairs"]["pending"] == 0

    pairs = _pairs(client, compare_set_id)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["status"] == "changed"
    assert pair["change_count"] == 1
    assert pair["cluster_count"] == 1
    assert pair["minor_count"] == 0
    assert Path(pair["compare_dxf_path"]).is_file()
    assert Path(pair["clusters_json_path"]).is_file()


def test_the_compared_files_land_under_the_bundle(client: TestClient, tmp_path: Path) -> None:
    """Contract §2: only ``.halo`` and the output folder are ever written."""
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]

    dxf = Path(pair["compare_dxf_path"])
    assert dxf.parent.name == pair["id"]
    assert dxf.parent.parent.name == "compare"
    assert dxf.parent.parent.parent.name == ".halo"
    assert dxf.name == "compare.dxf"


def test_a_sheet_with_nothing_changed_is_marked_same(client: TestClient, tmp_path: Path) -> None:
    compare_set_id, _truth = _prepare(client, "S01_identical", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]
    assert pair["status"] == "same"
    assert pair["change_count"] == 0
    assert pair["cluster_count"] == 0


def test_one_sided_sheets_are_skipped_rather_than_failed(
    client: TestClient, tmp_path: Path
) -> None:
    """``S14``: A-101 was removed and A-103 added; only A-102 can be diffed."""
    compare_set_id, _truth = _prepare(client, "S14_sheet_added_removed", tmp_path)
    _run(client, compare_set_id)

    statuses = sorted(pair["status"] for pair in _pairs(client, compare_set_id))
    assert statuses == ["added", "removed", "same"]

    summary = client.get(f"/api/v1/compare/sets/{compare_set_id}", headers=AUTH_HEADERS).json()
    stats = summary.get("stats") or {}
    if "compare" in stats:  # the summary may not surface stats; the DB does
        assert stats["compare"]["skipped"] == 2


def test_a_file_with_no_title_block_is_skipped(client: TestClient, tmp_path: Path) -> None:
    compare_set_id, _truth = _prepare(client, "S16_unrecognized", tmp_path)
    _run(client, compare_set_id)
    statuses = sorted(pair["status"] for pair in _pairs(client, compare_set_id))
    assert statuses == ["same", "unrecognized"]


def test_a_run_can_be_limited_to_named_pairs(client: TestClient, tmp_path: Path) -> None:
    compare_set_id, _truth = _prepare(client, "S13_multi_sheet", tmp_path)
    pairs = _pairs(client, compare_set_id)
    assert len(pairs) == 2
    target = next(pair for pair in pairs if _sheet_no(pair) == "A-102")

    _run(client, compare_set_id, pair_ids=[target["id"]])
    after = {pair["id"]: pair for pair in _pairs(client, compare_set_id)}
    assert after[target["id"]]["status"] == "changed"
    other = next(pair for pair in pairs if pair["id"] != target["id"])
    assert after[other["id"]]["compare_dxf_path"] is None


def _sheet_no(pair: dict[str, Any]) -> str | None:
    for side in ("after_frame", "before_frame"):
        frame = pair.get(side)
        if frame and frame.get("sheet_no"):
            return str(frame["sheet_no"])
    return None


def test_running_before_the_sheets_are_matched_is_a_conflict(
    client: TestClient, tmp_path: Path
) -> None:
    before, after, _truth = _scenario("S02_move_door", tmp_path)
    resp = client.post(
        "/api/v1/compare/sets",
        json={"before_dir": str(before), "after_dir": str(after), "run_date": RUN_DATE},
        headers=AUTH_HEADERS,
    )
    created = resp.json()
    wait_for_job(client, created["job_id"], timeout_s=60.0)

    resp = client.post(
        f"/api/v1/compare/sets/{created['compare_set_id']}/run", headers=AUTH_HEADERS
    )
    assert resp.status_code == 409, resp.text
    assert "ingested" in resp.text


def test_an_unknown_pair_id_is_a_404(client: TestClient, tmp_path: Path) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    resp = client.post(
        f"/api/v1/compare/sets/{compare_set_id}/run",
        json={"pair_ids": ["01J8QK00000000000000000XXX"]},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------- clusters


def test_the_sidecar_is_served_with_its_clusters_and_changes(
    client: TestClient, tmp_path: Path
) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]

    resp = client.get(f"/api/v1/compare/pairs/{pair['id']}/clusters", headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    sidecar = resp.json()

    assert sidecar["pair_id"] == pair["id"]
    assert sidecar["run_date"] == RUN_DATE
    assert sidecar["layer"] == "REV-20260904"
    assert sidecar["counts"] == {
        "clusters": 1,
        "changes": 1,
        "minor": 0,
        "approved": 0,
        "ignored": 0,
    }
    cluster = sidecar["clusters"][0]
    assert cluster["id"] == "c1"
    assert cluster["decision"] == "pending"
    assert cluster["label"].startswith("블록 DOOR_900 이동")
    assert cluster["cloud"]["handle"]
    assert set(sidecar["handle_to_cluster"].values()) == {"c1"}


def test_the_sidecar_validates_against_its_schema(client: TestClient, tmp_path: Path) -> None:
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    if not SCHEMA_SRC.is_dir():
        pytest.skip(f"{SCHEMA_SRC} missing")
    compare_set_id, _truth = _prepare(client, "S06_removed", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]
    sidecar = client.get(
        f"/api/v1/compare/pairs/{pair['id']}/clusters", headers=AUTH_HEADERS
    ).json()

    resources = []
    for path in SCHEMA_SRC.rglob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema, DRAFT202012)))
    validator = Draft202012Validator(
        {"$ref": "https://schema.halo-cad.internal/v0/compare/clusters-sidecar.schema.json"},
        registry=Registry().with_resources(resources),
    )
    errors = sorted(validator.iter_errors(sidecar), key=lambda e: list(e.absolute_path))
    assert not errors, [error.message for error in errors]


def test_asking_for_clusters_before_the_comparison_is_a_conflict(
    client: TestClient, tmp_path: Path
) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    pair = _pairs(client, compare_set_id)[0]
    resp = client.get(f"/api/v1/compare/pairs/{pair['id']}/clusters", headers=AUTH_HEADERS)
    assert resp.status_code == 409, resp.text


def test_an_unknown_pair_has_no_clusters(client: TestClient, tmp_path: Path) -> None:
    _prepare(client, "S02_move_door", tmp_path)
    resp = client.get(
        "/api/v1/compare/pairs/01J8QK00000000000000000XXX/clusters", headers=AUTH_HEADERS
    )
    assert resp.status_code == 404, resp.text


# --------------------------------------------------------------------------- deciding


def test_a_decision_is_stored_and_written_back_into_the_sidecar(
    client: TestClient, tmp_path: Path
) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]

    resp = client.patch(
        f"/api/v1/compare/pairs/{pair['id']}/clusters/1",
        json={"decision": "approved", "user_label": "문 위치 변경", "note": "현장 협의"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    cluster = resp.json()
    assert cluster["decision"] == "approved"
    assert cluster["user_label"] == "문 위치 변경"
    assert cluster["note"] == "현장 협의"
    assert cluster["id"] == "c1"

    on_disk = json.loads(Path(pair["clusters_json_path"]).read_text(encoding="utf-8"))
    assert on_disk["clusters"][0]["decision"] == "approved"
    assert on_disk["clusters"][0]["user_label"] == "문 위치 변경"
    assert on_disk["counts"]["approved"] == 1

    served = client.get(f"/api/v1/compare/pairs/{pair['id']}/clusters", headers=AUTH_HEADERS).json()
    assert served["clusters"][0]["decision"] == "approved"
    assert served["counts"]["approved"] == 1


def test_an_absent_field_is_left_alone_and_an_explicit_null_clears_it(
    client: TestClient, tmp_path: Path
) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]
    url = f"/api/v1/compare/pairs/{pair['id']}/clusters/1"

    client.patch(url, json={"decision": "ignored", "note": "보류"}, headers=AUTH_HEADERS)
    after = client.patch(url, json={"user_label": "라벨"}, headers=AUTH_HEADERS).json()
    assert after["decision"] == "ignored"
    assert after["note"] == "보류"

    cleared = client.patch(url, json={"note": None}, headers=AUTH_HEADERS).json()
    assert cleared["note"] is None
    assert cleared["decision"] == "ignored"


def test_deciding_a_cluster_that_is_not_there_is_a_404(client: TestClient, tmp_path: Path) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]
    resp = client.patch(
        f"/api/v1/compare/pairs/{pair['id']}/clusters/99",
        json={"decision": "approved"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404, resp.text


def test_a_review_survives_a_second_comparison(client: TestClient, tmp_path: Path) -> None:
    """``repos.replace_clusters(keep_decisions=True)`` -- contract §7, brief DoD.

    Re-running the comparison recomputes every cluster from scratch. What must
    not be recomputed is the work the user already did.
    """
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]
    client.patch(
        f"/api/v1/compare/pairs/{pair['id']}/clusters/1",
        json={"decision": "approved", "user_label": "문 위치 변경"},
        headers=AUTH_HEADERS,
    )

    _run(client, compare_set_id)

    served = client.get(f"/api/v1/compare/pairs/{pair['id']}/clusters", headers=AUTH_HEADERS).json()
    assert served["clusters"][0]["decision"] == "approved"
    assert served["clusters"][0]["user_label"] == "문 위치 변경"
    assert served["counts"]["approved"] == 1
    on_disk = json.loads(Path(pair["clusters_json_path"]).read_text(encoding="utf-8"))
    assert on_disk["clusters"][0]["decision"] == "approved"


def test_comparing_twice_rewrites_the_same_drawing(client: TestClient, tmp_path: Path) -> None:
    """Contract §8, through the real job runner and its process pool."""
    compare_set_id, _truth = _prepare(client, "S12_whole_redraw", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]
    first_dxf = Path(pair["compare_dxf_path"]).read_bytes()
    first_json = Path(pair["clusters_json_path"]).read_bytes()

    _run(client, compare_set_id)
    assert Path(pair["compare_dxf_path"]).read_bytes() == first_dxf
    assert Path(pair["clusters_json_path"]).read_bytes() == first_json


# --------------------------------------------------------------------------- the DXF


def test_the_compare_dxf_is_served_with_a_content_hash_etag(
    client: TestClient, tmp_path: Path
) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    _run(client, compare_set_id)
    pair = _pairs(client, compare_set_id)[0]

    resp = client.get(f"/api/v1/compare/pairs/{pair['id']}/compare-dxf", headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("application/dxf")

    payload = resp.content
    assert payload.startswith(b"  0\nSECTION")
    assert b"__CMP_ADDED" in payload
    assert b"REV-20260904" in payload

    etag = resp.headers["etag"]
    assert etag == f'"{hashlib.sha256(payload).hexdigest()}"'

    again = client.get(
        f"/api/v1/compare/pairs/{pair['id']}/compare-dxf",
        headers={**AUTH_HEADERS, "If-None-Match": etag},
    )
    assert again.status_code == 304
    assert again.headers["etag"] == etag


def test_the_compare_dxf_is_not_there_before_the_comparison(
    client: TestClient, tmp_path: Path
) -> None:
    compare_set_id, _truth = _prepare(client, "S02_move_door", tmp_path)
    pair = _pairs(client, compare_set_id)[0]
    resp = client.get(f"/api/v1/compare/pairs/{pair['id']}/compare-dxf", headers=AUTH_HEADERS)
    assert resp.status_code == 409, resp.text


# --------------------------------------------------------------------------- schema


def test_the_cluster_response_model_carries_exactly_the_schemas_fields() -> None:
    """The hand-written mirror must not drift from ``packages/schema``.

    Same guard R1-04 put on ``SheetFrameView``/``SheetPairView`` and for the
    same reason: the engine cannot import the generated ``halo_schema`` models
    yet (``engine/pyproject.toml`` is not a task's file), so the copy is checked
    against the contract it copies.
    """
    from halo_engine.model.compare import ClusterView

    schema_path = SCHEMA_SRC / "compare" / "cluster.schema.json"
    if not schema_path.is_file():
        pytest.skip(f"{schema_path} missing")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert set(schema["properties"]) == set(ClusterView.model_fields)
    required = set(schema["required"])
    optional = set(ClusterView.model_fields) - required
    assert optional == {"signature"}
