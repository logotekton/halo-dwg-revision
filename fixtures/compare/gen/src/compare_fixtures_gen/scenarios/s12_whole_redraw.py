"""S12 -- the after drawing is redrawn from scratch in reverse creation order
(Defaults for ambiguity: entity steps reversed + layer/block table order
reversed, no randomness -- see `base_plan.build_base_plan(reversed_layout=True)`),
renumbering every handle, then S02 (move door) and S04 (text change) are
planted on top: `moved` 1, `text` 1, zero false positives elsewhere.
"""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of, insert_entities, move_insert, set_text, union_bbox
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S12_whole_redraw"
MOVE_DX = 1250.0
NEW_TEXT = "리빙룸"


def generate(out_root: Path) -> None:
    before = build_base_plan(reversed_layout=False)
    after = build_base_plan(reversed_layout=True)

    door_before = before.doors[0]
    door_after = after.doors[0]
    door_bbox_before = bbox_of(insert_entities(door_before.insert))
    move_insert(door_after.insert, MOVE_DX, 0.0)
    door_bbox_after = bbox_of(insert_entities(door_after.insert))
    door_bbox = union_bbox(door_bbox_before, door_bbox_after)

    text_before = before.room_texts[0]
    text_after = after.room_texts[0]
    text_bbox_before = bbox_of([text_before])
    set_text(text_after, NEW_TEXT)
    text_bbox_after = bbox_of([text_after])
    text_bbox = union_bbox(text_bbox_before, text_bbox_after)

    assert door_before.insert.dxf.handle != door_after.insert.dxf.handle, (
        "S12 must actually renumber handles -- reversed_layout had no effect"
    )

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="후 도면을 생성 순서를 뒤집어 통째로 다시 그리고(핸들 전부 변경), 그 위에 문 이동과 텍스트 변경을 심는다.",
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
                        before_handle=None,
                        after_handle=None,
                        minor=False,
                        bbox=door_bbox,
                        note="whole redraw: door D1 still moves 1250mm east (handles renumbered, matched by fingerprint)",
                    ),
                    expected_change(
                        kind="text",
                        etype="TEXT",
                        layer="A-TEXT",
                        before_handle=None,
                        after_handle=None,
                        minor=False,
                        bbox=text_bbox,
                        note="whole redraw: room text still changes (handles renumbered, matched by fingerprint)",
                    ),
                ],
                expected_cluster_count=2,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
        notes=(
            "handle 은 일부러 null 이다 -- 통째 재생성으로 모든 핸들이 바뀌어 truth.schema.json 의 "
            "'copies a whole file' 규칙을 따른다. bbox 로만 대조한다. 심지 않은 나머지는 오탐 0 이어야 한다."
        ),
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
