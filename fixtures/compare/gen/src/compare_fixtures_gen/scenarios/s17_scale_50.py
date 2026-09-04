"""S17 -- SCALE="1:50" title block (A1 x 50 frame) with an S02-style door
move: `moved` 1, `scale_denominator` 50."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of, insert_entities, move_insert, union_bbox
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S17_scale_50"
SCALE_DENOM = 50
MOVE_DX = 1250.0


def generate(out_root: Path) -> None:
    before = build_base_plan(scale_denom=SCALE_DENOM)
    after = build_base_plan(scale_denom=SCALE_DENOM)

    door_before = before.doors[0]
    door_after = after.doors[0]
    bbox_before = bbox_of(insert_entities(door_before.insert))
    move_insert(door_after.insert, MOVE_DX, 0.0)
    bbox_after = bbox_of(insert_entities(door_after.insert))
    bbox = union_bbox(bbox_before, bbox_after)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="SCALE=1:50 도곽(A1x50 = 42,050x29,700mm)에서 문 1개를 1,250mm 동쪽으로 이동한다.",
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
                        note="door D1 moved 1250mm east on a 1:50 sheet",
                    )
                ],
                expected_cluster_count=1,
                clean_regions=default_clean_regions((0.0, 0.0), SCALE_DENOM),
            )
        ],
        notes=(
            "scale_denominator=50 -> scale_factor=0.5(docs/contracts/compare-dxf.md SS5). "
            "이 truth는 좌표·frame 인식만 보증하고, 클라우드/배지 크기 산정은 R1-06 책임이다."
        ),
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
