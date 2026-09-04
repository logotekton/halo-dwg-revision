"""S14 -- before has A-101 + A-102, after has A-102 + A-103:
A-101 `removed`, A-102 `same`, A-103 `added`."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import (
    PAPER_W,
    build_base_plan,
    default_clean_regions,
    frame_bbox,
    new_doc,
)
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_pair

SCENARIO_ID = "S14_sheet_added_removed"
SHEET_GAP = 6000.0
ORIGIN_0 = (0.0, 0.0)
ORIGIN_1 = (PAPER_W * 100.0 + SHEET_GAP, 0.0)


def generate(out_root: Path) -> None:
    before_doc = new_doc()
    build_base_plan(origin=ORIGIN_0, sheet_no="A-101", doc=before_doc)
    build_base_plan(origin=ORIGIN_1, sheet_no="A-102", doc=before_doc)

    after_doc = new_doc()
    build_base_plan(origin=ORIGIN_1, sheet_no="A-102", doc=after_doc)
    # A-103 reuses ORIGIN_0's slot -- a different file, so no geometric clash
    # with A-101 (which only exists in the before file).
    build_base_plan(origin=ORIGIN_0, sheet_no="A-103", doc=after_doc)

    whole_frame_removed = [
        *default_clean_regions(ORIGIN_0, 100),
        frame_bbox(ORIGIN_0, 100),
    ]

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="전에는 A-101/A-102, 후에는 A-102/A-103. A-101은 removed, A-103은 added, A-102는 same이어야 한다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="removed",
                match_method=None,
                expected_changes=[],
                expected_cluster_count=0,
                clean_regions=whole_frame_removed,
            ),
            expected_pair(
                sheet_no="A-102",
                status="same",
                match_method="number",
                expected_changes=[],
                expected_cluster_count=0,
                clean_regions=default_clean_regions(ORIGIN_1, 100),
            ),
            expected_pair(
                sheet_no="A-103",
                status="added",
                match_method=None,
                expected_changes=[],
                expected_cluster_count=0,
                clean_regions=whole_frame_removed,
            ),
        ],
        notes=(
            "A-101(전 파일)과 A-103(후 파일)은 같은 좌표 슬롯(ORIGIN_0)을 재사용하지만 서로 다른 "
            "파일에 있어 겹치지 않는다. added/removed 도곽은 change/cluster 레코드를 만들지 않아 "
            "expected_cluster_count=0이고 clean_regions에 도곽 전체를 넣었다."
        ),
    )
    write_pair(
        out_root, SCENARIO_ID, before_doc, after_doc, truth, before_name="plan.dxf", after_name="plan.dxf"
    )
