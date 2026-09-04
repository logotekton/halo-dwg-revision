"""S15 -- the whole after file is translated by (+50000, +20000): the sheet
is `same` once compared in frame-local coordinates."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_pair

SCENARIO_ID = "S15_frame_shift"
SHIFT = (50000.0, 20000.0)


def generate(out_root: Path) -> None:
    before = build_base_plan(origin=(0.0, 0.0))
    after = build_base_plan(origin=SHIFT)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="후 파일 전체를 (+50000, +20000) 평행이동한다. 도곽 로컬 좌표 기준으로는 변경이 없어야 한다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="same",
                match_method="number",
                expected_changes=[],
                expected_cluster_count=0,
                clean_regions=default_clean_regions(SHIFT, 100),
            )
        ],
        notes=(
            "build_base_plan(origin=SHIFT)로 전체 콘텐츠를 다시 그려 실제 평행이동한 도면을 만들었다. "
            "엔진은 frame_offset = after.bbox.min - before.bbox.min 만큼 되돌려 후 좌표계로 맞춘 뒤 "
            "비교해야 한다(docs/contracts/compare-dxf.md SS1)."
        ),
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
