"""The acceptance criterion: seventeen planted revisions, checked against their truth.

Seed AC3 and the brief's Definition of done. Every scenario in
``fixtures/compare`` (R1-07) plants a known change and records the answer in
``truth.json``; this module compares the two sheets and asserts that the engine
found exactly what was planted -- no more (오탐 0) and no less (심은 변경 100%
검출).

Nothing here restates an expectation. The kinds, the fold reasons, the boxes,
the cluster counts and the clean regions all come out of the truth file, so a
generator change and an engine change cannot quietly agree with each other.
"""

from __future__ import annotations

from typing import Any

import pytest

from halo_engine.compare.config import scale_factor

from .scenario_helpers import (
    SCENARIOS,
    ScenarioRun,
    intersects,
    match_expected,
    packaged_compare_config,
    run_scenario,
    truth_of,
)

CONFIG = packaged_compare_config()

#: Truth statuses that describe a sheet with only one side. There is nothing to
#: diff, so the comparison never sees them (the run skips those pairs,
#: ``api/routers/compare_clusters.py``).
ONE_SIDED = {"added", "removed", "unrecognized"}

_RUNS: dict[str, ScenarioRun] = {}


def _run(scenario: str) -> ScenarioRun:
    """Compare a scenario once and reuse it: seventeen scenarios, several assertions each."""
    if scenario not in _RUNS:
        _RUNS[scenario] = run_scenario(scenario)
    return _RUNS[scenario]


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_planted_change_is_detected(scenario: str) -> None:
    run = _run(scenario)
    for expected_pair in run.truth["expected_pairs"]:
        sheet_no = expected_pair.get("sheet_no")
        if expected_pair["status"] in ONE_SIDED:
            assert sheet_no not in run.sheets, (
                f"{scenario}/{sheet_no} is {expected_pair['status']} in the truth file "
                "but was compared as a pair"
            )
            continue
        sheet = run.sheets.get(sheet_no)
        assert sheet is not None, (scenario, sheet_no, sorted(map(str, run.sheets)))
        for expected in expected_pair.get("expected_changes") or []:
            found = match_expected(sheet.diff.changes, expected)
            assert found is not None, (
                f"{scenario}/{sheet_no}: nothing matched {expected['kind']} "
                f"{expected.get('etype')} {expected.get('note') or ''} -- got "
                + "; ".join(
                    f"{c.kind}/{c.etype}/minor={c.minor}/{c.minor_reason}/{c.bbox}"
                    for c in sheet.diff.changes
                )
            )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_no_change_is_reported_that_was_not_planted(scenario: str) -> None:
    """오탐 0, the criterion ``S12_whole_redraw`` exists to test.

    Counted rather than sampled: the truth file lists every change the fixture
    planted, minor ones included, so the engine's own counts must equal them
    exactly. One extra `modified` on a redrawn sheet is the failure this
    project cannot ship with.
    """
    run = _run(scenario)
    for expected_pair in run.truth["expected_pairs"]:
        sheet_no = expected_pair.get("sheet_no")
        if expected_pair["status"] in ONE_SIDED:
            continue
        sheet = run.sheets[sheet_no]
        expected_changes = expected_pair.get("expected_changes") or []
        expected_real = [c for c in expected_changes if not c.get("minor")]
        expected_minor = [c for c in expected_changes if c.get("minor")]

        assert len(sheet.real_changes) == len(expected_real), (
            f"{scenario}/{sheet_no}: {len(sheet.real_changes)} real changes, "
            f"expected {len(expected_real)} -- "
            + "; ".join(f"{c.kind}/{c.etype}/{c.bbox}" for c in sheet.real_changes)
        )
        assert sheet.diff.minor_count == len(expected_minor), (
            f"{scenario}/{sheet_no}: {sheet.diff.minor_count} minor changes, "
            f"expected {len(expected_minor)}"
        )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_pair_status_matches_the_truth(scenario: str) -> None:
    run = _run(scenario)
    for expected_pair in run.truth["expected_pairs"]:
        if expected_pair["status"] in ONE_SIDED:
            continue
        sheet = run.sheets[expected_pair.get("sheet_no")]
        assert sheet.status == expected_pair["status"], (scenario, sheet.sheet_no)


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_cluster_count_matches_where_the_truth_fixes_one(scenario: str) -> None:
    run = _run(scenario)
    for expected_pair in run.truth["expected_pairs"]:
        if expected_pair["status"] in ONE_SIDED:
            continue
        expected = expected_pair.get("expected_cluster_count")
        if expected is None:
            continue  # the truth deliberately leaves it open (S11)
        sheet = run.sheets[expected_pair.get("sheet_no")]
        assert len(sheet.clusters) == expected, (
            f"{scenario}/{sheet.sheet_no}: {len(sheet.clusters)} clusters, expected {expected}"
        )


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_no_cloud_mark_lands_in_a_region_the_truth_calls_clean(scenario: str) -> None:
    run = _run(scenario)
    for expected_pair in run.truth["expected_pairs"]:
        if expected_pair["status"] in ONE_SIDED:
            continue
        sheet = run.sheets[expected_pair.get("sheet_no")]
        for region in expected_pair.get("clean_regions") or []:
            for cluster in sheet.clusters:
                assert not intersects(cluster.bbox, region), (
                    f"{scenario}/{sheet.sheet_no}: cluster {cluster.number} "
                    f"({cluster.label}) at {cluster.bbox} is inside the clean region {region}"
                )


def test_a_file_with_no_title_block_is_never_compared() -> None:
    """``S16_unrecognized``: ``detail.dxf`` is a sheet list entry, not a comparison."""
    run = _run("S16_unrecognized")
    assert run.unrecognized == ["detail.dxf"]
    assert set(run.sheets) == {"A-101"}


def test_sheets_that_exist_on_one_side_only_are_not_diffed() -> None:
    """``S14_sheet_added_removed``: A-101 went away and A-103 arrived."""
    run = _run("S14_sheet_added_removed")
    assert set(run.sheets) == {"A-102"}
    assert run.sheets["A-102"].status == "same"


def test_a_one_to_fifty_sheet_draws_its_cloud_at_half_size() -> None:
    """Contract §5 end to end: the factor reaches the cloud, not just the sidecar."""
    fifty = _run("S17_scale_50")
    hundred = _run("S02_move_door")
    assert fifty.sheets["A-101"].scale_factor == scale_factor(50) == 0.5
    assert hundred.sheets["A-101"].scale_factor == 1.0

    small = fifty.sheets["A-101"].clusters[0]
    large = hundred.sheets["A-101"].clusters[0]
    assert _cloud_margin(small) == pytest.approx(CONFIG.cloud.margin * 0.5)
    assert _cloud_margin(large) == pytest.approx(CONFIG.cloud.margin)
    assert _badge_side(small) == pytest.approx(CONFIG.cloud.badge_side * 0.5, abs=1e-3)
    assert _badge_side(large) == pytest.approx(CONFIG.cloud.badge_side, abs=1e-3)


def _cloud_margin(cluster: Any) -> float:
    return cluster.bbox[0] - min(point[0] for point in cluster.cloud["points"])


def _badge_side(cluster: Any) -> float:
    left, right = cluster.badge_points[0], cluster.badge_points[1]
    return abs(right[0] - left[0])


def test_the_fold_reasons_are_exactly_the_ones_the_truth_names() -> None:
    """The four fold scenarios, read straight out of their truth files."""
    for scenario in (
        "S07_hatch_regen",
        "S08_layer_only",
        "S09_mtext_format_only",
        "S10_move_tiny",
    ):
        truth = truth_of(scenario)
        expected = [
            change["minor_reason"]
            for pair in truth["expected_pairs"]
            for change in pair.get("expected_changes") or []
        ]
        detected = [
            change.minor_reason
            for sheet in _run(scenario).sheets.values()
            for change in sheet.diff.changes
        ]
        assert sorted(detected) == sorted(expected), scenario


def test_every_change_carries_its_provenance() -> None:
    """CLAUDE.md rule 5: no record without ``{file, handle, path, space}``."""
    for scenario in SCENARIOS:
        for sheet in _run(scenario).sheets.values():
            for change in sheet.diff.changes:
                assert change.provenance, (scenario, change.seq)
                for side in ("before", "after"):
                    entry = change.provenance.get(side)
                    if entry is None:
                        continue
                    assert set(entry) == {"file", "handle", "path", "space"}
                    assert entry["space"] == "MODEL"
