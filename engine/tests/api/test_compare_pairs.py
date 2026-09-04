"""``POST /compare/sets/{id}/frames`` and the pairs endpoints end to end
(brief R1-04, contract §7).

Driven through the real pipeline: two folders in, ``compare.ingest`` builds the
working DXFs, ``compare.frames`` extracts 도곽 and matches them, and the sheet
list comes back over HTTP. The inputs are R1-07's revision fixtures, and the
expectations are read out of their ``truth.json`` rather than restated here --
truth files are the shared answer key for R1-04 and R1-06, and a test that
carries its own copy of the answer stops being evidence the moment the two
disagree.

Frames-only statuses are not the truth file's statuses: ``changed`` and
``same`` there describe the sheet *after* a comparison, and matching can only
say ``pending`` -- or ``same`` when the two files are byte-identical, which
needs no geometry (contract §3).
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

#: Truth statuses that survive matching unchanged; the rest become `pending`
#: (or `same` for two identical files) until R1-06 compares the sheet.
PRE_COMPARISON_STATUSES = {"added", "removed", "unrecognized"}


def _scenario(name: str, tmp_path: Path) -> tuple[Path, Path, dict[str, Any]]:
    """Copy one fixture scenario into ``tmp_path`` and read its truth file.

    Copied because the ingest job writes ``<project>/.halo`` next to the two
    set folders, and ``fixtures/`` is neither this task's to write nor
    something a test may leave litter in (CLAUDE.md rule 1).
    """
    source = FIXTURES / name
    if not (source / "truth.json").is_file():
        pytest.skip(f"{source} missing -- run `cd fixtures/compare/gen && uv run python -m ...`")
    project = tmp_path / "project"
    shutil.copytree(source / "before", project / "before")
    shutil.copytree(source / "after", project / "after")
    truth = json.loads((source / "truth.json").read_text(encoding="utf-8"))
    return project / "before", project / "after", truth


def _start_set(client: TestClient, before: Path, after: Path) -> str:
    resp = client.post(
        "/api/v1/compare/sets",
        json={"before_dir": str(before), "after_dir": str(after), "run_date": RUN_DATE},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 202, resp.text
    created = resp.json()
    job = wait_for_job(client, created["job_id"], timeout_s=60.0)
    assert job["status"] == "DONE", job
    return str(created["compare_set_id"])


def _extract_frames(client: TestClient, compare_set_id: str) -> dict[str, Any]:
    resp = client.post(f"/api/v1/compare/sets/{compare_set_id}/frames", headers=AUTH_HEADERS)
    assert resp.status_code == 202, resp.text
    job = wait_for_job(client, resp.json()["job_id"], timeout_s=120.0)
    assert job["status"] == "DONE", job
    assert job["kind"] == "compare.frames"
    assert job["compare_set_id"] == compare_set_id
    return dict(job)


def _pairs(client: TestClient, compare_set_id: str, **params: Any) -> list[dict[str, Any]]:
    resp = client.get(
        f"/api/v1/compare/sets/{compare_set_id}/pairs", params=params, headers=AUTH_HEADERS
    )
    assert resp.status_code == 200, resp.text
    return list(resp.json())


def _sheet_no(pair: dict[str, Any]) -> str | None:
    for side in ("after_frame", "before_frame"):
        frame = pair.get(side)
        if frame and frame.get("sheet_no"):
            return str(frame["sheet_no"])
    return None


def _run(client: TestClient, name: str, tmp_path: Path) -> tuple[str, list[dict[str, Any]], Any]:
    before, after, truth = _scenario(name, tmp_path)
    compare_set_id = _start_set(client, before, after)
    _extract_frames(client, compare_set_id)
    return compare_set_id, _pairs(client, compare_set_id), truth


def _assert_matches_truth(pairs: list[dict[str, Any]], truth: dict[str, Any]) -> None:
    by_number = {_sheet_no(pair): pair for pair in pairs}
    assert len(pairs) == len(truth["expected_pairs"]), pairs
    for expected in truth["expected_pairs"]:
        pair = by_number.get(expected["sheet_no"])
        assert pair is not None, (expected["sheet_no"], sorted(map(str, by_number)))
        if expected["status"] in PRE_COMPARISON_STATUSES:
            assert pair["status"] == expected["status"], pair
        else:
            assert pair["status"] in {"pending", "same"}, pair
        assert pair["match_method"] == expected["match_method"], pair


# --------------------------------------------------------------------------- schema shape


@pytest.mark.parametrize(
    ("schema_file", "model_name"),
    [("sheet-frame.schema.json", "SheetFrameView"), ("sheet-pair.schema.json", "SheetPairView")],
)
def test_the_response_models_carry_exactly_the_schemas_fields(
    schema_file: str, model_name: str
) -> None:
    """The hand-written mirrors must not drift from ``packages/schema``.

    R1-04 could not import the generated ``halo_schema`` models: the package is
    not among the engine's dependencies and ``engine/pyproject.toml`` is not a
    task's file (contract §4 allows "같은 필드의 자체 모델" for exactly this
    case; the report proposes the dependency). Reading the schema file itself
    is what keeps the second option honest -- add a property to the contract
    and this test fails until the model follows.
    """
    from halo_engine.model import compare as compare_models

    schema_path = REPO_ROOT / "packages" / "schema" / "src" / "compare" / schema_file
    if not schema_path.is_file():
        pytest.skip(f"{schema_path} missing")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    model = getattr(compare_models, model_name)

    assert set(model.model_fields) == set(schema["properties"]), model_name
    # Everything the schema requires is required of the model too.
    optional = {name for name, field in model.model_fields.items() if not field.is_required()}
    assert set(schema["required"]) & optional == set(), model_name


# --------------------------------------------------------------------------- scenarios


@pytest.mark.parametrize(
    "scenario",
    ["S01_identical", "S13_multi_sheet", "S14_sheet_added_removed", "S16_unrecognized"],
)
def test_fixture_scenarios_pair_as_their_truth_file_says(scenario: str, tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            _, pairs, truth = _run(client, scenario, tmp_path)
            _assert_matches_truth(pairs, truth)
    finally:
        shutdown_app(app)


def test_identical_files_are_same_without_a_comparison(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            _, pairs, _ = _run(client, "S01_identical", tmp_path)
            assert [p["status"] for p in pairs] == ["same"]
            assert pairs[0]["match_method"] == "number"
            assert pairs[0]["score"] == 1.0
    finally:
        shutdown_app(app)


def test_two_sheets_in_one_file_become_two_pairs(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, pairs, _ = _run(client, "S13_multi_sheet", tmp_path)
            assert [_sheet_no(p) for p in pairs] == ["A-101", "A-102"]
            for pair in pairs:
                for side in ("before_frame", "after_frame"):
                    frame = pair[side]
                    assert frame["kind"] == "titleblock"
                    assert frame["scale_denominator"] == 100
                    assert frame["bbox"][2] - frame["bbox"][0] == pytest.approx(84100.0)
                    # The list summary drops the (large) handle list.
                    assert frame["entity_handles"] is None
                    assert frame["provenance"]["space"] == "MODEL"
                assert pair["compare_set_id"] == compare_set_id
                assert pair["change_count"] == 0
            # The two sheets came out of one file but own different entities.
            assert pairs[0]["before_frame"]["file_id"] == pairs[1]["before_frame"]["file_id"]
            assert pairs[0]["before_frame"]["sort_index"] == 0
            assert pairs[1]["before_frame"]["sort_index"] == 1
    finally:
        shutdown_app(app)


def test_an_unrecognised_file_is_listed_not_dropped(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            _, pairs, _ = _run(client, "S16_unrecognized", tmp_path)
            unrecognised = [p for p in pairs if p["status"] == "unrecognized"]
            assert len(unrecognised) == 1
            frame = unrecognised[0]["after_frame"]
            assert frame["kind"] == "unrecognized_file"
            assert frame["sheet_no"] is None
            assert frame["norm_key"] == "file:DETAIL.DXF"
            assert unrecognised[0]["before_frame"] is None
    finally:
        shutdown_app(app)


def test_a_1_to_50_sheet_keeps_its_denominator(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            _, pairs, _ = _run(client, "S17_scale_50", tmp_path)
            assert pairs[0]["after_frame"]["scale_denominator"] == 50
            assert pairs[0]["after_frame"]["scale_text"] == "1:50"
    finally:
        shutdown_app(app)


# --------------------------------------------------------------------------- job & stats


def test_the_job_leaves_the_set_matched_and_merges_its_stats(tmp_path: Path) -> None:
    """`stats` written by the ingest job has to survive the frames job."""
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, _, _ = _run(client, "S14_sheet_added_removed", tmp_path)

            summary = client.get(
                f"/api/v1/compare/sets/{compare_set_id}", headers=AUTH_HEADERS
            ).json()
            assert summary["status"] == "matched"

            bundle = app.state.bundle
            with bundle.session_factory() as session:
                from halo_engine.db import repos

                stats = repos.get_compare_set(session, compare_set_id).stats
            # R1-03's counters are still there ...
            assert stats["files"] == {"before": 1, "after": 1, "total": 2}
            assert "converter" in stats and "crosscheck" in stats
            # ... alongside R1-04's (contract §7 CompareSetSummary).
            assert stats["frames"] == {"before": 2, "after": 2, "unrecognized_files": 0}
            assert stats["pairs"]["pending"] == 1
            assert stats["pairs"]["added"] == 1
            assert stats["pairs"]["removed"] == 1
            assert stats["frames_skipped"] == []
    finally:
        shutdown_app(app)


def test_frames_can_be_re_extracted_after_matching(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, first, _ = _run(client, "S13_multi_sheet", tmp_path)
            _extract_frames(client, compare_set_id)
            second = _pairs(client, compare_set_id)
            assert [_sheet_no(p) for p in first] == [_sheet_no(p) for p in second]
            assert [p["status"] for p in first] == [p["status"] for p in second]
    finally:
        shutdown_app(app)


def test_extraction_before_ingest_finishes_is_409(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            before, after, _ = _scenario("S01_identical", tmp_path)
            compare_set_id = _start_set(client, before, after)

            from halo_engine.db import repos

            with app.state.bundle.session_factory() as session:
                repos.update_compare_set(session, compare_set_id, status="ingesting")

            resp = client.post(
                f"/api/v1/compare/sets/{compare_set_id}/frames", headers=AUTH_HEADERS
            )
            assert resp.status_code == 409, resp.text
    finally:
        shutdown_app(app)


def test_unknown_compare_set_is_404(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            assert (
                client.post("/api/v1/compare/sets/nope/frames", headers=AUTH_HEADERS).status_code
                == 404
            )
            assert (
                client.get("/api/v1/compare/sets/nope/pairs", headers=AUTH_HEADERS).status_code
                == 404
            )
            assert (
                client.delete("/api/v1/compare/pairs/nope", headers=AUTH_HEADERS).status_code == 404
            )
    finally:
        shutdown_app(app)


# --------------------------------------------------------------------------- list controls


def test_the_list_filters_by_status_searches_and_sorts(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, pairs, _ = _run(client, "S14_sheet_added_removed", tmp_path)
            assert [_sheet_no(p) for p in pairs] == ["A-101", "A-102", "A-103"]

            removed = _pairs(client, compare_set_id, status="removed")
            assert [_sheet_no(p) for p in removed] == ["A-101"]

            # `q` is normalised the same way matching is: no hyphen, any case.
            assert [_sheet_no(p) for p in _pairs(client, compare_set_id, q="a103")] == ["A-103"]
            assert [_sheet_no(p) for p in _pairs(client, compare_set_id, q="평면")] == [
                "A-101",
                "A-102",
                "A-103",
            ]
            # File name matches too.
            assert len(_pairs(client, compare_set_id, q="plan.dxf")) == 3
            assert _pairs(client, compare_set_id, q="nothing-like-this") == []

            by_status = _pairs(client, compare_set_id, sort="status")
            assert [p["status"] for p in by_status] == sorted(p["status"] for p in pairs)
            # `changes` is a stable order before any comparison has run.
            assert len(_pairs(client, compare_set_id, sort="changes")) == 3
    finally:
        shutdown_app(app)


# --------------------------------------------------------------------------- manual pairs


def _manual(client: TestClient, compare_set_id: str, before_id: str, after_id: str) -> Any:
    return client.post(
        f"/api/v1/compare/sets/{compare_set_id}/pairs/manual",
        json={"before_frame_id": before_id, "after_frame_id": after_id},
        headers=AUTH_HEADERS,
    )


def test_the_user_can_pair_a_removed_sheet_with_an_added_one(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, pairs, _ = _run(client, "S14_sheet_added_removed", tmp_path)
            removed = next(p for p in pairs if p["status"] == "removed")
            added = next(p for p in pairs if p["status"] == "added")

            resp = _manual(
                client, compare_set_id, removed["before_frame_id"], added["after_frame_id"]
            )
            assert resp.status_code == 200, resp.text
            manual = resp.json()
            assert manual["match_method"] == "manual"
            assert manual["status"] == "pending"
            assert manual["score"] is None
            assert manual["before_frame"]["sheet_no"] == "A-101"
            assert manual["after_frame"]["sheet_no"] == "A-103"

            # The two rows it replaced are gone; the sheet count drops by one.
            after_pairs = _pairs(client, compare_set_id)
            assert len(after_pairs) == 2
            assert {p["status"] for p in after_pairs} == {"pending"}
    finally:
        shutdown_app(app)


def test_deleting_a_manual_pair_restores_the_removed_and_added_rows(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, pairs, _ = _run(client, "S14_sheet_added_removed", tmp_path)
            removed = next(p for p in pairs if p["status"] == "removed")
            added = next(p for p in pairs if p["status"] == "added")
            manual = _manual(
                client, compare_set_id, removed["before_frame_id"], added["after_frame_id"]
            ).json()

            resp = client.delete(f"/api/v1/compare/pairs/{manual['id']}", headers=AUTH_HEADERS)
            assert resp.status_code == 200, resp.text
            assert len(resp.json()["restored"]) == 2

            restored = _pairs(client, compare_set_id)
            assert [(_sheet_no(p), p["status"]) for p in restored] == [
                ("A-101", "removed"),
                ("A-102", "pending"),
                ("A-103", "added"),
            ]
    finally:
        shutdown_app(app)


def test_a_matched_pair_cannot_be_deleted(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, pairs, _ = _run(client, "S14_sheet_added_removed", tmp_path)
            matched = next(p for p in pairs if p["match_method"] == "number")
            resp = client.delete(f"/api/v1/compare/pairs/{matched['id']}", headers=AUTH_HEADERS)
            assert resp.status_code == 409, resp.text
            assert len(_pairs(client, compare_set_id)) == 3
    finally:
        shutdown_app(app)


def test_a_sheet_that_is_already_matched_cannot_be_paired_by_hand(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, pairs, _ = _run(client, "S14_sheet_added_removed", tmp_path)
            matched = next(p for p in pairs if p["match_method"] == "number")
            added = next(p for p in pairs if p["status"] == "added")
            resp = _manual(
                client, compare_set_id, matched["before_frame_id"], added["after_frame_id"]
            )
            assert resp.status_code == 409, resp.text
    finally:
        shutdown_app(app)


def test_pairing_two_frames_of_the_same_side_is_422(tmp_path: Path) -> None:
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, pairs, _ = _run(client, "S14_sheet_added_removed", tmp_path)
            removed = next(p for p in pairs if p["status"] == "removed")
            resp = _manual(
                client, compare_set_id, removed["before_frame_id"], removed["before_frame_id"]
            )
            assert resp.status_code == 422, resp.text
    finally:
        shutdown_app(app)


def test_a_manual_pair_survives_a_second_frame_extraction(tmp_path: Path) -> None:
    """Re-extracting frames must not throw away the user's own pairing."""
    app = make_app(tmp_path)
    try:
        with TestClient(app) as client:
            compare_set_id, pairs, _ = _run(client, "S14_sheet_added_removed", tmp_path)
            removed = next(p for p in pairs if p["status"] == "removed")
            added = next(p for p in pairs if p["status"] == "added")
            _manual(client, compare_set_id, removed["before_frame_id"], added["after_frame_id"])

            _extract_frames(client, compare_set_id)

            after_pairs = _pairs(client, compare_set_id)
            assert len(after_pairs) == 2
            manual = next(p for p in after_pairs if p["match_method"] == "manual")
            assert manual["before_frame"]["sheet_no"] == "A-101"
            assert manual["after_frame"]["sheet_no"] == "A-103"
            # No sheet fell out of the list while the manual pair was restored.
            listed = {
                frame["id"]
                for pair in after_pairs
                for frame in (pair["before_frame"], pair["after_frame"])
                if frame
            }
            assert len(listed) == 4
    finally:
        shutdown_app(app)
