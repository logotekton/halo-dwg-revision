"""S05 -- add a new wall polyline + a new door INSERT, at least 3m apart:
`added` 2, cluster 2."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of, insert_entities
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S05_added"

#: rectangle wall segment (x0, y0, x1, y1), local == world at origin (0,0), denom 100.
NEW_WALL_RECT = (46000.0, 6400.0, 50000.0, 6600.0)
#: new door center; > 3000mm from the wall segment above.
NEW_DOOR_CENTER = (60000.0, 6500.0)


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()
    msp = after.doc.modelspace()

    x0, y0, x1, y1 = NEW_WALL_RECT
    pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    new_wall = msp.add_lwpolyline(pts, format="xy", close=True, dxfattribs={"layer": "A-WALL"})
    wall_bbox = bbox_of([new_wall])

    dx, dy = NEW_DOOR_CENTER
    new_door = msp.add_blockref("DOOR_900", (dx - 450.0, dy), dxfattribs={"layer": "A-DOOR"})
    new_door.add_auto_attribs({"TAG": "D7"})
    door_bbox = bbox_of(insert_entities(new_door))

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="벽 폴리라인 1개와 문 INSERT 1개를 서로 3m 이상 떨어진 자리에 신설한다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
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
                        note="new wall segment added",
                    ),
                    expected_change(
                        kind="added",
                        etype="INSERT",
                        layer="A-DOOR",
                        before_handle=None,
                        after_handle=new_door.dxf.handle,
                        minor=False,
                        bbox=door_bbox,
                        note="new door D7 added",
                    ),
                ],
                expected_cluster_count=2,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
        notes="새 벽과 새 문 중심 사이 거리는 약 11,550mm로 cluster.grow 임계값(약 1,682mm)보다 훨씬 커 별도 클러스터가 된다.",
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
