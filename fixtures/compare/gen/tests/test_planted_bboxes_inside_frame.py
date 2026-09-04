"""Every planted change's ``bbox`` must fall inside its sheet's frame (brief
Constraints: "도곽 안 엔티티만 심는다"), and must not intersect any of that
pair's declared ``clean_regions`` (truth.schema.json: "a cluster whose box
intersects one of these is a false positive").

Frames and title blocks are re-read from the generated DXF with ezdxf --
independent of any generator-internal constant -- and matched to a
``sheet_no`` by finding the title-block INSERT whose insertion point falls
inside a frame candidate and reading its ``DWG_NO`` ATTRIB. Change bboxes are
defined in the *after* drawing's world coordinates
(docs/contracts/compare-dxf.md SS5), so matching is done against after-side
frames.
"""

from __future__ import annotations

import json
from pathlib import Path

import ezdxf
import pytest
from ezdxf import bbox as ez_bbox

GEN_ROOT = Path(__file__).resolve().parents[1]
COMPARE_ROOT = GEN_ROOT.parent

EPS = 0.5  # mm tolerance for rounding noise at box edges


def _scenario_dirs() -> list[Path]:
    return sorted(p for p in COMPARE_ROOT.iterdir() if p.is_dir() and p.name != "gen")


SCENARIO_DIRS = _scenario_dirs()


def _frame_candidates(doc) -> list[list[float]]:
    """4-point closed LWPOLYLINEs on layer TITLE -- the sheet frame outlines."""
    boxes = []
    for pl in doc.modelspace().query("LWPOLYLINE"):
        if pl.dxf.layer != "TITLE":
            continue
        if not pl.closed or len(pl) != 4:
            continue
        box = ez_bbox.extents([pl])
        boxes.append([box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y])
    return boxes


def _point_in_box(x: float, y: float, box: list[float]) -> bool:
    return box[0] - EPS <= x <= box[2] + EPS and box[1] - EPS <= y <= box[3] + EPS


def _frame_bbox_by_sheet_no(dxf_dir: Path, min_attribs: int) -> dict[str, list[float]]:
    result: dict[str, list[float]] = {}
    for dxf_path in sorted(dxf_dir.glob("*.dxf")):
        doc = ezdxf.readfile(str(dxf_path))
        frames = _frame_candidates(doc)
        titleblocks = [ins for ins in doc.modelspace().query("INSERT") if len(list(ins.attribs)) >= min_attribs]
        for frame_box in frames:
            for ins in titleblocks:
                ip = ins.dxf.insert
                if _point_in_box(ip.x, ip.y, frame_box):
                    attribs = {a.dxf.tag: a.dxf.text for a in ins.attribs}
                    sheet_no = attribs.get("DWG_NO")
                    if sheet_no:
                        result[sheet_no] = frame_box
                    break
    return result


def _box_in_box(inner: list[float], outer: list[float]) -> bool:
    return (
        inner[0] >= outer[0] - EPS
        and inner[1] >= outer[1] - EPS
        and inner[2] <= outer[2] + EPS
        and inner[3] <= outer[3] + EPS
    )


def _boxes_intersect(a: list[float], b: list[float]) -> bool:
    return a[0] < b[2] - EPS and a[2] > b[0] + EPS and a[1] < b[3] - EPS and a[3] > b[1] + EPS


@pytest.mark.parametrize("scenario_dir", SCENARIO_DIRS, ids=lambda p: p.name)
def test_expected_change_bboxes_are_inside_their_frame(scenario_dir: Path) -> None:
    truth = json.loads((scenario_dir / "truth.json").read_text(encoding="utf-8"))
    after_dir = scenario_dir / truth["after_dir"]
    frame_by_sheet = _frame_bbox_by_sheet_no(after_dir, min_attribs=3)

    for pair in truth["expected_pairs"]:
        changes = pair["expected_changes"]
        if not changes:
            continue
        sheet_no = pair["sheet_no"]
        assert sheet_no in frame_by_sheet, (
            f"{scenario_dir.name}: no after-side frame found for sheet {sheet_no!r} "
            f"(candidates: {list(frame_by_sheet)})"
        )
        frame_box = frame_by_sheet[sheet_no]
        for change in changes:
            assert "bbox" in change and change["bbox"], f"{scenario_dir.name}/{sheet_no}: change missing bbox"
            assert _box_in_box(change["bbox"], frame_box), (
                f"{scenario_dir.name}/{sheet_no}: change bbox {change['bbox']} escapes "
                f"frame {frame_box} ({change.get('note')})"
            )


@pytest.mark.parametrize("scenario_dir", SCENARIO_DIRS, ids=lambda p: p.name)
def test_clean_regions_do_not_intersect_expected_changes(scenario_dir: Path) -> None:
    truth = json.loads((scenario_dir / "truth.json").read_text(encoding="utf-8"))
    for pair in truth["expected_pairs"]:
        for region in pair["clean_regions"]:
            for change in pair["expected_changes"]:
                assert not _boxes_intersect(region, change["bbox"]), (
                    f"{scenario_dir.name}/{pair['sheet_no']}: clean_region {region} intersects "
                    f"planted change bbox {change['bbox']} ({change.get('note')})"
                )


@pytest.mark.parametrize("scenario_dir", SCENARIO_DIRS, ids=lambda p: p.name)
def test_at_least_two_clean_regions_when_pinned(scenario_dir: Path) -> None:
    """Definition of done / brief Goal 4: clean_regions has >= 2 entries for
    every pair that pins a change/cluster expectation (i.e. is not a bare
    removed/added/unrecognized placeholder with no expected_changes)."""
    truth = json.loads((scenario_dir / "truth.json").read_text(encoding="utf-8"))
    for pair in truth["expected_pairs"]:
        if pair["status"] in ("unrecognized",):
            continue
        assert len(pair["clean_regions"]) >= 2, (
            f"{scenario_dir.name}/{pair['sheet_no']}: expected >= 2 clean_regions, "
            f"got {len(pair['clean_regions'])}"
        )
