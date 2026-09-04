"""Running one ``fixtures/compare`` scenario and checking it against its truth file.

The synthetic revision pairs (R1-07) are the acceptance criterion for the
comparison engine: "심은 변경 100% 검출, 접기 규칙 정확, 통째 사본 오탐 0". The
answers live in each scenario's ``truth.json``, so the tests here never restate
an expectation -- a test that carries its own copy of the answer stops being
evidence the moment the two disagree (the same rule
``tests/api/test_compare_pairs.py`` follows for matching).

Kept out of ``conftest.py`` on purpose: these are plain functions the test
modules import by name, not pytest fixtures (the split ``tests/validate``
uses).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ezdxf
import pytest
import yaml
from ezdxf.document import Drawing

from halo_engine.compare.cluster import ClusterRecord, build_clusters
from halo_engine.compare.config import (
    DEFAULT_COMPARE_YAML,
    DEFAULT_FRAMES_YAML,
    CompareConfig,
    FramesConfig,
    scale_factor,
)
from halo_engine.compare.diff import ChangeRecord, DiffResult, diff_pair
from halo_engine.compare.frames import (
    KIND_TITLEBLOCK,
    FrameRecord,
    assign_entities,
    extract_frames,
)

# engine/tests/compare/scenario_helpers.py -> engine/tests -> engine -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES = REPO_ROOT / "fixtures" / "compare"
SCHEMA_SRC = REPO_ROOT / "packages" / "schema" / "src"

#: Every scenario R1-07 generates, in the order its README lists them.
SCENARIOS = [
    "S01_identical",
    "S02_move_door",
    "S03_dim_value",
    "S04_text_change",
    "S05_added",
    "S06_removed",
    "S07_hatch_regen",
    "S08_layer_only",
    "S09_mtext_format_only",
    "S10_move_tiny",
    "S11_blockdef_change",
    "S12_whole_redraw",
    "S13_multi_sheet",
    "S14_sheet_added_removed",
    "S15_frame_shift",
    "S16_unrecognized",
    "S17_scale_50",
]

#: ``provenance.file`` is a ``drawing_file`` ULID or a sha256
#: (``common/provenance.schema.json``). These stand in for the row ids the
#: router passes, so a sidecar built in a unit test validates like a real one.
BEFORE_FILE_ID = "01J8QK00000000000000000BEF"
AFTER_FILE_ID = "01J8QK000000000000000AFTER"

#: Minimum overlap accepted between a detected box and the truth's box (brief
#: DoD). Containment either way also passes: the truth records the box of the
#: entity that was planted, and a detected `moved` box is the union of the two
#: positions, which contains it but does not overlap it by half.
BBOX_IOU_MIN = 0.5


def packaged_compare_config() -> CompareConfig:
    """The shipped ``compare.yaml``. Every threshold in the tests comes from here."""
    return CompareConfig.model_validate(yaml.safe_load(DEFAULT_COMPARE_YAML.read_text("utf-8")))


def packaged_frames_config() -> FramesConfig:
    return FramesConfig.model_validate(yaml.safe_load(DEFAULT_FRAMES_YAML.read_text("utf-8")))


def truth_of(scenario: str) -> dict[str, Any]:
    path = FIXTURES / scenario / "truth.json"
    if not path.is_file():
        pytest.skip(
            f"{path} missing -- run `cd fixtures/compare/gen && "
            "uv run python -m compare_fixtures_gen --out ..`"
        )
    return dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass
class SheetComparison:
    """One 도곽 짝 of one scenario, compared."""

    sheet_no: str | None
    before_frame: FrameRecord
    after_frame: FrameRecord
    diff: DiffResult
    clusters: list[ClusterRecord]
    scale_factor: float

    @property
    def real_changes(self) -> list[ChangeRecord]:
        return [change for change in self.diff.changes if not change.minor]

    @property
    def status(self) -> str:
        return "changed" if self.diff.has_real_changes else "same"


@dataclass
class ScenarioRun:
    """Everything one scenario produced, keyed the way its truth file is."""

    scenario: str
    truth: dict[str, Any]
    before_doc: Drawing
    after_doc: Drawing
    sheets: dict[str | None, SheetComparison]
    unrecognized: list[str]
    """``sheet_no``-less frames: files with no title block (``S16``)."""


def _load(path: Path, file_id: str, config: FramesConfig) -> tuple[Drawing, list[FrameRecord]]:
    doc = ezdxf.readfile(str(path))
    frames = extract_frames(doc, file_id=file_id, config=config)
    assign_entities(doc, frames)
    for frame in frames:
        frame.file_name = path.name
    return doc, frames


def run_scenario(scenario: str) -> ScenarioRun:
    """Extract 도곽 from both sides, pair them by drawing number and compare each.

    Deliberately *not* the API path: these tests are about the comparison
    rules, and going through ingest and matching for every scenario would make
    a rule failure look like a matching failure.
    ``tests/api/test_compare_clusters.py`` drives the real pipeline instead.
    """
    truth = truth_of(scenario)
    compare_config = packaged_compare_config()
    frames_config = packaged_frames_config()
    root = FIXTURES / scenario

    # A scenario can hold several files per side (``S16`` adds a second 후
    # drawing), and one file can hold several 도곽 (``S13``), so every frame is
    # carried with the document it was read from.
    before_frames: list[tuple[Drawing, FrameRecord]] = []
    after_frames: list[tuple[Drawing, FrameRecord]] = []
    for path in sorted((root / truth["before_dir"]).glob("*.dxf")):
        doc, frames = _load(path, BEFORE_FILE_ID, frames_config)
        before_frames.extend((doc, frame) for frame in frames)
    for path in sorted((root / truth["after_dir"]).glob("*.dxf")):
        doc, frames = _load(path, AFTER_FILE_ID, frames_config)
        after_frames.extend((doc, frame) for frame in frames)
    assert before_frames and after_frames, scenario
    before_doc = before_frames[0][0]
    after_doc = after_frames[0][0]

    by_number = {
        frame.sheet_no: (doc, frame)
        for doc, frame in before_frames
        if frame.kind == KIND_TITLEBLOCK
    }
    sheets: dict[str | None, SheetComparison] = {}
    unrecognized = [
        frame.file_name for _doc, frame in after_frames if frame.kind != KIND_TITLEBLOCK
    ]

    for after_own_doc, after_frame in after_frames:
        if after_frame.kind != KIND_TITLEBLOCK:
            continue
        found = by_number.get(after_frame.sheet_no)
        if found is None:
            continue
        before_own_doc, before_frame = found
        result = diff_pair(
            before_own_doc, after_own_doc, before_frame, after_frame, compare_config
        )
        factor = scale_factor(after_frame.scale_denominator)
        sheets[after_frame.sheet_no] = SheetComparison(
            sheet_no=after_frame.sheet_no,
            before_frame=before_frame,
            after_frame=after_frame,
            diff=result,
            clusters=build_clusters(result.changes, after_frame, compare_config, factor),
            scale_factor=factor,
        )

    return ScenarioRun(
        scenario=scenario,
        truth=truth,
        before_doc=before_doc,
        after_doc=after_doc,
        sheets=sheets,
        unrecognized=unrecognized,
    )


# --------------------------------------------------------------------------- boxes


def intersects(a: list[float], b: list[float]) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])


def _area(box: list[float]) -> float:
    return max(box[2] - box[0], 0.0) * max(box[3] - box[1], 0.0)


def _contains(outer: list[float], inner: list[float], slack: float = 1.0) -> bool:
    return (
        outer[0] - slack <= inner[0]
        and outer[1] - slack <= inner[1]
        and outer[2] + slack >= inner[2]
        and outer[3] + slack >= inner[3]
    )


def iou(a: list[float], b: list[float]) -> float:
    if not intersects(a, b):
        return 0.0
    overlap = [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]
    union = _area(a) + _area(b) - _area(overlap)
    return _area(overlap) / union if union > 0 else 1.0


def boxes_agree(detected: list[float], expected: list[float]) -> bool:
    """The brief's box rule: ``IoU >= 0.5``, or one box contains the other.

    Containment is not a loophole. A `moved` change's box is the union of the
    two positions and the truth records the one the fixture planted; a
    `blockdef` change's box spans every instance and the truth records the
    representative one. Both are right answers that no overlap ratio would
    accept.
    """
    return (
        iou(detected, expected) >= BBOX_IOU_MIN
        or _contains(detected, expected)
        or _contains(expected, detected)
    )


# --------------------------------------------------------------------------- truth


def match_expected(
    changes: list[ChangeRecord], expected: dict[str, Any]
) -> ChangeRecord | None:
    """The change that answers one ``expected_changes`` entry, or ``None``.

    Handles are compared when the truth knows them; a whole-sheet redraw
    renumbers everything, so ``S12``'s entries carry ``null`` handles and are
    matched on kind, type and box alone (contract §4).
    """
    for change in changes:
        if change.kind != expected["kind"]:
            continue
        if expected.get("etype") and change.etype != expected["etype"]:
            continue
        if bool(change.minor) != bool(expected.get("minor")):
            continue
        if change.minor_reason != expected.get("minor_reason"):
            continue
        if expected.get("layer") and change.layer not in {
            expected["layer"],
            *(_layer_alternatives(expected["layer"])),
        }:
            continue
        if expected.get("before_handle") and change.before_handle != expected["before_handle"]:
            continue
        if expected.get("after_handle") and change.after_handle != expected["after_handle"]:
            continue
        if expected.get("bbox") and not boxes_agree(change.bbox, expected["bbox"]):
            continue
        return change
    return None


def _layer_alternatives(layer: str) -> set[str]:
    """``change.layer`` is the 후 layer; a ``layer_only`` truth names the 전 one.

    ``fixtures/compare/S08_layer_only`` says ``A-WALL`` because that is where
    the walls started; the contract says a change reports the layer it is on
    *now* (``change.schema.json``: "the after layer when there is an after
    side"), which is ``A-WALL2``. Both are the same fact.
    """
    return {f"{layer}2", layer.removesuffix("2")}


__all__ = [
    "BBOX_IOU_MIN",
    "FIXTURES",
    "REPO_ROOT",
    "SCENARIOS",
    "SCHEMA_SRC",
    "ScenarioRun",
    "SheetComparison",
    "boxes_agree",
    "intersects",
    "iou",
    "match_expected",
    "packaged_compare_config",
    "packaged_frames_config",
    "run_scenario",
    "truth_of",
]
