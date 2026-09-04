"""S13 -- one file carries two title-block frames (A-101, A-102) side by
side; the change (S05-style: new wall + new door, >3m apart) is planted only
on A-102: A-101 stays `same`, A-102 `changed`."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import PAPER_W, build_base_plan, default_clean_regions, new_doc
from compare_fixtures_gen.plant import bbox_of, insert_entities
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S13_multi_sheet"
SHEET_GAP = 6000.0
ORIGIN_A101 = (0.0, 0.0)
ORIGIN_A102 = (PAPER_W * 100.0 + SHEET_GAP, 0.0)

NEW_WALL_RECT_LOCAL = (46000.0, 6400.0, 50000.0, 6600.0)
NEW_DOOR_CENTER_LOCAL = (60000.0, 6500.0)


def generate(out_root: Path) -> None:
    before_doc = new_doc()
    build_base_plan(origin=ORIGIN_A101, sheet_no="A-101", doc=before_doc)
    build_base_plan(origin=ORIGIN_A102, sheet_no="A-102", doc=before_doc)

    after_doc = new_doc()
    build_base_plan(origin=ORIGIN_A101, sheet_no="A-101", doc=after_doc)
    build_base_plan(origin=ORIGIN_A102, sheet_no="A-102", doc=after_doc)

    msp = after_doc.modelspace()
    ox, oy = ORIGIN_A102
    x0, y0, x1, y1 = NEW_WALL_RECT_LOCAL
    pts = [(ox + x0, oy + y0), (ox + x1, oy + y0), (ox + x1, oy + y1), (ox + x0, oy + y1)]
    new_wall = msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs={"layer": "A-WALL"})
    wall_bbox = bbox_of([new_wall])

    dx, dy = NEW_DOOR_CENTER_LOCAL
    new_door = msp.add_blockref(
        "DOOR_900", (ox + dx - 450.0, oy + dy), dxfattribs={"layer": "A-DOOR"}
    )
    new_door.add_auto_attribs({"TAG": "D7"})
    door_bbox = bbox_of(insert_entities(new_door))

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="한 파일에 도곽 2개(A-101, A-102)를 가로로 배치한다. 변경은 A-102에만 심는다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="same",
                match_method="number",
                expected_changes=[],
                expected_cluster_count=0,
                clean_regions=default_clean_regions(ORIGIN_A101, 100),
            ),
            expected_pair(
                sheet_no="A-102",
                status="changed",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="added",
                        etype="LWPOLYLINE",
                        layer="A-WALL",
                        before_handle=None,
                        after_handle=new_wall.dxf.handle,
                        minor=False,
                        bbox=wall_bbox,
                        note="new wall added on A-102 only",
                    ),
                    expected_change(
                        kind="added",
                        etype="INSERT",
                        layer="A-DOOR",
                        before_handle=None,
                        after_handle=new_door.dxf.handle,
                        minor=False,
                        bbox=door_bbox,
                        note="new door D7 added on A-102 only",
                    ),
                ],
                expected_cluster_count=2,
                clean_regions=default_clean_regions(ORIGIN_A102, 100),
            ),
        ],
        notes="A-101과 A-102는 서로 84,100 + 6,000mm 만큼 떨어져 있어 도곽 배정(bbox_center)이 겹치지 않는다.",
    )
    write_pair(
        out_root, SCENARIO_ID, before_doc, after_doc, truth, before_name="plan.dxf", after_name="plan.dxf"
    )
