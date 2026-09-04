"""S01 -- no planted change: pair `same`, cluster 0."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_pair

SCENARIO_ID = "S01_identical"


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()
    truth = build_truth(
        scenario=SCENARIO_ID,
        description="변경이 전혀 없는 도면 짝. pair status same, 클러스터 0이 유일한 합격 기준이다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="same",
                match_method="number",
                expected_changes=[],
                expected_cluster_count=0,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
        notes="같은 코드로 두 번 만든 동일한 도면. 지문 매칭이 오탐을 만들면 안 된다.",
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
