"""S04 -- change one room TEXT's string: `text` 1."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of, set_text, union_bbox
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S04_text_change"
NEW_TEXT = "리빙룸"


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    text_before = before.room_texts[0]
    text_after = after.room_texts[0]
    bbox_before = bbox_of([text_before])
    old_text = text_after.dxf.text
    set_text(text_after, NEW_TEXT)
    bbox_after = bbox_of([text_after])
    bbox = union_bbox(bbox_before, bbox_after)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="실명 TEXT 1개의 문구를 바꾼다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="changed",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="text",
                        etype="TEXT",
                        layer="A-TEXT",
                        before_handle=text_before.dxf.handle,
                        after_handle=text_after.dxf.handle,
                        minor=False,
                        bbox=bbox,
                        note=f"room text '{old_text}' -> '{NEW_TEXT}'",
                    )
                ],
                expected_cluster_count=1,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
