"""``POST /compare/sets/{id}/export`` and the run endpoints, end to end (contract §7).

The whole vertical slice screen D sits on: two folders in, ingest, frames, run,
승인 on one cloud mark, export -- and out come a markup drawing, a change list
and a ``run`` record, over HTTP, through the real job runner.

``tests/compare/test_export.py`` is where the output *rules* are checked (file
names, the ``-2`` folder, the writer fallback, ``run.json``'s shape). What is
proved here is the plumbing: the statuses that gate the export, the 202 that
carries the run id before the job has done anything, and the two GETs the
renderer polls.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from api_helpers import AUTH_HEADERS, make_app, shutdown_app, wait_for_job
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "fixtures" / "compare"
RUN_DATE = "2026-09-04"


@pytest.fixture
def client(tmp_path: Path) -> Any:
    app = make_app(tmp_path)
    with TestClient(app) as test_client:
        yield test_client
    shutdown_app(app)


def _scenario(name: str, tmp_path: Path) -> tuple[Path, Path]:
    """Copy one fixture scenario into ``tmp_path``: the project the user picked."""
    source = FIXTURES / name
    if not (source / "truth.json").is_file():
        pytest.skip(f"{source} missing -- run the fixture generator")
    project = tmp_path / "project"
    shutil.copytree(source / "before", project / "변경전")
    shutil.copytree(source / "after", project / "변경후")
    return project / "변경전", project / "변경후"


def _ingest_and_match(client: TestClient, name: str, tmp_path: Path) -> str:
    before, after = _scenario(name, tmp_path)
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
    return compare_set_id


def _compare(client: TestClient, compare_set_id: str) -> list[dict[str, Any]]:
    resp = client.post(f"/api/v1/compare/sets/{compare_set_id}/run", headers=AUTH_HEADERS)
    assert resp.status_code == 202, resp.text
    assert wait_for_job(client, resp.json()["job_id"], timeout_s=180.0)["status"] == "DONE"
    resp = client.get(f"/api/v1/compare/sets/{compare_set_id}/pairs", headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    return list(resp.json())


def _approve(client: TestClient, pair_id: str, number: int, **fields: Any) -> dict[str, Any]:
    resp = client.patch(
        f"/api/v1/compare/pairs/{pair_id}/clusters/{number}",
        json={"decision": "approved", **fields},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text
    return dict(resp.json())


def _export(client: TestClient, compare_set_id: str, **body: Any) -> dict[str, Any]:
    resp = client.post(
        f"/api/v1/compare/sets/{compare_set_id}/export",
        json={"run_date": RUN_DATE, **body},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 202, resp.text
    accepted = resp.json()
    job = wait_for_job(client, accepted["job_id"], timeout_s=180.0)
    assert job["status"] == "DONE", job
    assert job["kind"] == "compare.export"
    assert job["compare_set_id"] == compare_set_id
    return dict(accepted)


# --------------------------------------------------------------------------- the gate


def test_exporting_before_the_comparison_is_a_conflict(client: TestClient, tmp_path: Path) -> None:
    """Contract §7: 409 for any status but ``compared``.

    Before the comparison there is nothing to approve, so an export would
    produce an empty folder and a run that claims success.
    """
    compare_set_id = _ingest_and_match(client, "S02_move_door", tmp_path)
    resp = client.post(
        f"/api/v1/compare/sets/{compare_set_id}/export",
        json={"run_date": RUN_DATE},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 409, resp.text
    assert "matched" in resp.text


def test_exporting_an_unknown_compare_set_is_a_404(client: TestClient, tmp_path: Path) -> None:
    _ingest_and_match(client, "S02_move_door", tmp_path)
    resp = client.post(
        "/api/v1/compare/sets/01J8QK00000000000000000XXX/export",
        json={"run_date": RUN_DATE},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 404, resp.text


def test_a_run_date_that_is_not_a_date_is_rejected(client: TestClient, tmp_path: Path) -> None:
    compare_set_id = _ingest_and_match(client, "S02_move_door", tmp_path)
    resp = client.post(
        f"/api/v1/compare/sets/{compare_set_id}/export",
        json={"run_date": "2026/09/04"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 422, resp.text


# --------------------------------------------------------------------------- the slice


def test_approve_then_export_produces_a_drawing_a_list_and_a_run(
    client: TestClient, tmp_path: Path
) -> None:
    """The brief's acceptance path: 409 -> 승인 -> export 202 -> run done -> GET run·tsv."""
    compare_set_id = _ingest_and_match(client, "S02_move_door", tmp_path)
    pairs = _compare(client, compare_set_id)
    assert len(pairs) == 1
    pair = pairs[0]
    _approve(client, pair["id"], 1, user_label="문 위치 변경")

    accepted = _export(client, compare_set_id)
    assert accepted["run_id"]

    resp = client.get(f"/api/v1/compare/runs/{accepted['run_id']}", headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    run = resp.json()

    assert run["id"] == accepted["run_id"]
    assert run["compare_set_id"] == compare_set_id
    assert run["status"] == "done"
    assert run["run_date"] == RUN_DATE
    assert run["layer_name"] == "REV-20260904"
    assert run["scope"] == "all"
    assert run["approved_count"] == 1
    assert run["ignored_count"] == 0
    assert run["pair_ids"] == [pair["id"]]

    assert len(run["files"]) == 1
    entry = run["files"][0]
    assert entry["pair_id"] == pair["id"]
    assert entry["sheet_no"] == "A-101"
    written = Path(entry["path"])
    assert written.is_file()
    assert written.stem == "A-101_변경후_markup"
    assert written.suffix.lstrip(".") == entry["format"]

    output_dir = Path(run["output_dir"])
    assert output_dir.name == RUN_DATE
    assert output_dir.parent.name == "출력"
    assert output_dir.parent.parent == tmp_path / "project"
    assert (output_dir / "run.json").is_file()
    assert (output_dir / "changes.tsv").is_file()

    # The user's own label is what the drawing and the list both say.
    assert "문 위치 변경" in (output_dir / "changes.tsv").read_text("utf-8")
    assert "문 위치 변경" in written.read_text("utf-8", errors="ignore")


def test_the_change_list_is_served_as_a_tsv(client: TestClient, tmp_path: Path) -> None:
    """Contract §7: ``text/tab-separated-values; charset=utf-8``, the file's own bytes."""
    compare_set_id = _ingest_and_match(client, "S02_move_door", tmp_path)
    pair = _compare(client, compare_set_id)[0]
    _approve(client, pair["id"], 1)
    accepted = _export(client, compare_set_id)

    resp = client.get(f"/api/v1/compare/runs/{accepted['run_id']}/tsv", headers=AUTH_HEADERS)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "text/tab-separated-values; charset=utf-8"
    assert "changes.tsv" in resp.headers["content-disposition"]

    run = client.get(f"/api/v1/compare/runs/{accepted['run_id']}", headers=AUTH_HEADERS).json()
    on_disk = (Path(run["output_dir"]) / "changes.tsv").read_bytes()
    assert resp.content == on_disk

    lines = resp.content.decode("utf-8").rstrip("\n").split("\n")
    assert lines[0].split("\t") == ["도면번호", "도면명", "번호", "종류", "내용", "판정", "일자"]
    assert lines[1].split("\t")[0] == "A-101"
    assert lines[1].split("\t")[5] == "승인"


def test_an_ignored_cluster_is_listed_but_not_drawn(client: TestClient, tmp_path: Path) -> None:
    """Brief Defaults for ambiguity: 무시는 TSV에만."""
    compare_set_id = _ingest_and_match(client, "S02_move_door", tmp_path)
    pair = _compare(client, compare_set_id)[0]
    resp = client.patch(
        f"/api/v1/compare/pairs/{pair['id']}/clusters/1",
        json={"decision": "ignored"},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200, resp.text

    accepted = _export(client, compare_set_id)
    run = client.get(f"/api/v1/compare/runs/{accepted['run_id']}", headers=AUTH_HEADERS).json()
    assert run["files"] == []
    assert run["ignored_count"] == 1

    tsv = client.get(
        f"/api/v1/compare/runs/{accepted['run_id']}/tsv", headers=AUTH_HEADERS
    ).content.decode("utf-8")
    assert "무시" in tsv


def test_the_set_is_exportable_again_afterwards(client: TestClient, tmp_path: Path) -> None:
    """Contract §3: ``compared`` -> ``exporting`` -> ``compared``, so a fix can be re-exported."""
    compare_set_id = _ingest_and_match(client, "S02_move_door", tmp_path)
    pair = _compare(client, compare_set_id)[0]
    _approve(client, pair["id"], 1)

    first = _export(client, compare_set_id)
    summary = client.get(f"/api/v1/compare/sets/{compare_set_id}", headers=AUTH_HEADERS).json()
    assert summary["status"] == "compared"

    second = _export(client, compare_set_id)
    assert second["run_id"] != first["run_id"]
    runs = [
        client.get(f"/api/v1/compare/runs/{accepted['run_id']}", headers=AUTH_HEADERS).json()
        for accepted in (first, second)
    ]
    assert Path(runs[0]["output_dir"]).name == RUN_DATE
    assert Path(runs[1]["output_dir"]).name == f"{RUN_DATE}-2"
    assert runs[1]["layer_name"] == "REV-20260904-2"
    assert Path(runs[0]["files"][0]["path"]).is_file(), "the first export is not overwritten"


def test_a_multi_sheet_set_exports_only_the_approved_sheets(
    client: TestClient, tmp_path: Path
) -> None:
    """``S13`` has two 도곽; approving one must not export the other."""
    compare_set_id = _ingest_and_match(client, "S13_multi_sheet", tmp_path)
    pairs = _compare(client, compare_set_id)
    changed = [pair for pair in pairs if pair["cluster_count"] > 0]
    assert changed, "S13 is meant to have a changed sheet"
    target = changed[0]
    _approve(client, target["id"], 1)

    accepted = _export(client, compare_set_id)
    run = client.get(f"/api/v1/compare/runs/{accepted['run_id']}", headers=AUTH_HEADERS).json()
    assert run["pair_ids"] == [target["id"]]
    assert len(run["files"]) == 1


def test_the_run_json_on_disk_matches_the_served_run(client: TestClient, tmp_path: Path) -> None:
    compare_set_id = _ingest_and_match(client, "S02_move_door", tmp_path)
    pair = _compare(client, compare_set_id)[0]
    _approve(client, pair["id"], 1)
    accepted = _export(client, compare_set_id)
    run = client.get(f"/api/v1/compare/runs/{accepted['run_id']}", headers=AUTH_HEADERS).json()

    on_disk = json.loads((Path(run["output_dir"]) / "run.json").read_text("utf-8"))
    assert on_disk["id"] == run["id"]
    assert on_disk["status"] == run["status"]
    assert on_disk["pair_ids"] == run["pair_ids"]
    # The file names its outputs relative to itself; the API names them absolutely.
    assert not Path(on_disk["files"][0]["path"]).is_absolute()
    assert Path(run["files"][0]["path"]).is_absolute()


def test_an_unknown_run_is_a_404(client: TestClient, tmp_path: Path) -> None:
    _ingest_and_match(client, "S02_move_door", tmp_path)
    for suffix in ("", "/tsv"):
        resp = client.get(
            f"/api/v1/compare/runs/01J8QK00000000000000000XXX{suffix}", headers=AUTH_HEADERS
        )
        assert resp.status_code == 404, resp.text
