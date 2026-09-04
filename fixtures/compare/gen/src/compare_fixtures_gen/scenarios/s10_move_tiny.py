"""S10 -- move a door 0.005mm (below the 0.01mm minor-move tolerance):
`minor` 1, reason `move_le_0_01`."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of, insert_entities, move_insert, union_bbox
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S10_move_tiny"
MOVE_DX = 0.005


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    door_before = before.doors[1]  # D2 -- independent of S02's D1
    door_after = after.doors[1]
    bbox_before = bbox_of(insert_entities(door_before.insert))
    move_insert(door_after.insert, MOVE_DX, 0.0)
    bbox_after = bbox_of(insert_entities(door_after.insert))
    bbox = union_bbox(bbox_before, bbox_after)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="문 INSERT 1개(D2)를 0.005mm만 동쪽으로 이동한다(0.01mm 이하 접힘 규칙).",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="same",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="moved",
                        etype="INSERT",
                        layer="A-DOOR",
                        before_handle=door_before.insert.dxf.handle,
                        after_handle=door_after.insert.dxf.handle,
                        minor=True,
                        minor_reason="move_le_0_01",
                        bbox=bbox,
                        note="door D2 moved 0.005mm east (within compare.yaml minor.move_tolerance)",
                    )
                ],
                expected_cluster_count=0,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
