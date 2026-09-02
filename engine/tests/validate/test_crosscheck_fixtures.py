"""Crosscheck against the committed fixture truth, including the corruption case.

``fixtures/truth/F##.json`` is a real ``LayerStatsDocument`` (W2-03), so it
doubles as a realistic input here without re-parsing any DXF: these tests are
about the *comparer*, not about the parsers. The full three-parser sweep over
the DXF bytes is ``tools/crosscheck.sh`` /
``docs/spikes/crosscheck-fixtures.md``.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from halo_engine.model import Severity
from halo_engine.validate.crosscheck import DEFAULT_WHITELIST, compare, load_whitelist

FIXTURE_IDS = [
    "F01",
    "F02",
    "F03",
    "F04",
    "F05",
    "F06",
    "F07",
    "F08",
    "F09",
    "F10_grid",
    "F10_host",
]


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("fixture_id", FIXTURE_IDS)
def test_a_document_compared_with_itself_is_green(truth_dir: Path, fixture_id: str) -> None:
    document = load(truth_dir / f"{fixture_id}.json")
    other = copy.deepcopy(document)
    other["producer"] = {"name": "viewer.mlightcad", "version": "1.14.3"}
    report = compare(document, other, whitelist=load_whitelist(DEFAULT_WHITELIST))
    assert report.status is Severity.GREEN, report.model_dump()
    assert report.red_layers == []


def drop_lines(document: dict[str, Any], layer: str, removed: int) -> dict[str, Any]:
    """Corrupted copy: ``removed`` LINEs deleted from ``layer``'s bucket and totals."""
    corrupted = copy.deepcopy(document)
    for bucket in corrupted["buckets"]:
        if bucket["layer"] != layer:
            continue
        aggregate = bucket["aggregate"]
        aggregate["count_by_type"]["LINE"] -= removed
        aggregate["entity_count"] -= removed
    corrupted["totals"]["count_by_type"]["LINE"] -= removed
    corrupted["totals"]["entity_count"] -= removed
    corrupted["producer"] = {"name": "viewer.mlightcad", "version": "1.14.3"}
    return corrupted


def test_f06_with_two_lines_removed_is_red_with_the_briefs_reason(truth_dir: Path) -> None:
    """Brief W2-04: "F06 stats에서 LINE 2개 제거 -> RED with reason count_by_type.LINE 24→22".

    F06's 24 LINEs are split across two layers (S-BEAM 17, X-GRID 7), so the
    brief's ``24→22`` is the document total; the layer that lost them reports
    ``17→15``. Both are asserted here.
    """
    document = load(truth_dir / "F06.json")
    assert document["totals"]["count_by_type"]["LINE"] == 24, "fixture drifted; update this test"
    beams = next(b for b in document["buckets"] if b["layer"] == "S-BEAM")
    assert beams["aggregate"]["count_by_type"]["LINE"] == 17

    report = compare(
        document,
        drop_lines(document, "S-BEAM", 2),
        whitelist=load_whitelist(DEFAULT_WHITELIST),
    )
    assert report.status is Severity.RED
    assert report.red_layers == ["S-BEAM"]
    assert [d.detail for d in report.totals.differences] == ["count_by_type.LINE 24→22"]
    beam_result = next(x for x in report.layers if x.layer == "S-BEAM")
    assert [d.detail for d in beam_result.differences] == ["count_by_type.LINE 17→15"]
    assert beam_result.differences[0].whitelist_id is None, "counts are never whitelisted"


def test_cli_writes_json_and_markdown_and_exits_zero_on_red(
    truth_dir: Path, tmp_path: Path
) -> None:
    """The brief's acceptance command chains with `&&`, so RED must still exit 0."""
    document = load(truth_dir / "F06.json")
    reference = tmp_path / "f06.ezdxf.json"
    broken = tmp_path / "f06.broken.json"
    reference.write_text(json.dumps(document), encoding="utf-8")
    broken.write_text(json.dumps(drop_lines(document, "S-BEAM", 2)), encoding="utf-8")

    stem = tmp_path / "rep"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "halo_engine",
            "crosscheck",
            "--ref",
            str(reference),
            "--other",
            str(broken),
            "--out",
            str(stem),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == "RED"

    markdown = (tmp_path / "rep.md").read_text(encoding="utf-8")
    assert "RED" in markdown
    assert "count_by_type.LINE 24→22" in markdown

    report = json.loads((tmp_path / "rep.json").read_text(encoding="utf-8"))
    assert report["status"] == "RED"
    assert report["red_layers"] == ["S-BEAM"]


def test_cli_fail_on_red_exits_one(truth_dir: Path, tmp_path: Path) -> None:
    document = load(truth_dir / "F06.json")
    reference = tmp_path / "ref.json"
    broken = tmp_path / "broken.json"
    reference.write_text(json.dumps(document), encoding="utf-8")
    broken.write_text(json.dumps(drop_lines(document, "S-BEAM", 2)), encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "halo_engine",
            "crosscheck",
            "--ref",
            str(reference),
            "--other",
            str(broken),
            "--out",
            str(tmp_path / "rep"),
            "--fail-on-red",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1


def test_comparison_is_well_under_one_second(truth_dir: Path) -> None:
    """Brief: "성능: 문서 크기와 무관하게 <1초"."""
    import time

    document = load(truth_dir / "F11.json")  # ~200k entities' worth of aggregates
    other = copy.deepcopy(document)
    entries = load_whitelist(DEFAULT_WHITELIST)
    started = time.perf_counter()
    compare(document, other, whitelist=entries)
    assert time.perf_counter() - started < 1.0
