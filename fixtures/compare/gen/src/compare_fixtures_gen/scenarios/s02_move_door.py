"""S02 -- move one door INSERT (D1) 1,250mm east: `moved` 1, cluster 1."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of, insert_entities, move_insert, union_bbox
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S02_move_door"
MOVE_DX = 1250.0


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    door_before = before.doors[0]
    door_after = after.doors[0]
    bbox_before = bbox_of(insert_entities(door_before.insert))
    move_insert(door_after.insert, MOVE_DX, 0.0)
    bbox_after = bbox_of(insert_entities(door_after.insert))
    bbox = union_bbox(bbox_before, bbox_after)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="문 INSERT 1개(D1)를 동쪽으로 1,250mm 이동한다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="changed",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="moved",
                        etype="INSERT",
                        layer="A-DOOR",
                        before_handle=door_before.insert.dxf.handle,
                        after_handle=door_after.insert.dxf.handle,
                        minor=False,
                        bbox=bbox,
                        note="door D1 moved 1250mm east",
                    )
                ],
                expected_cluster_count=1,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
