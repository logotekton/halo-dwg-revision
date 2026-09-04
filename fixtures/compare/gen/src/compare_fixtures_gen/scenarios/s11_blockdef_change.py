"""S11 -- change one line's length inside the shared `DOOR_900` block
definition (affects all 6 placed instances D1..D6 at once): `blockdef` 1
(instance count 6).

Defaults for ambiguity: the truth lists one representative `expected_change`
(the block definition change itself, matched by D1's bbox) rather than one
entry per instance -- the DB/sidecar schema has no per-change "instance
count" field, and the `note` records the instance count as prose for a
failing assertion to print, per docs/contracts/r1.md SS4 `RevisionTruth`.
`expected_cluster_count` is left unpinned (null): the 6 instances are spread
across the whole sheet and whether the compare engine's proximity rule folds
any of them into a shared cluster is not specified by the brief.
"""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import (
    DOOR_PANEL_LEN,
    DOOR_SPECS,
    build_base_plan,
    default_clean_regions,
    door_panel_line,
)
from compare_fixtures_gen.plant import bbox_of, insert_entities
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S11_blockdef_change"
SHORTEN_BY = 50.0


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    d0_before = before.doors[0]
    d0_after = after.doors[0]
    bbox = bbox_of(insert_entities(d0_before.insert))

    line = door_panel_line(after.doc)
    old_end = line.dxf.end
    line.dxf.end = (old_end.x - SHORTEN_BY, old_end.y, old_end.z)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="DOOR_900 블록 정의 내부 문짝 LINE 길이를 900mm에서 850mm로 줄인다(인스턴스 6개 전체에 영향).",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="changed",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="blockdef",
                        etype="INSERT",
                        layer="A-DOOR",
                        before_handle=d0_before.insert.dxf.handle,
                        after_handle=d0_after.insert.dxf.handle,
                        minor=False,
                        bbox=bbox,
                        note=(
                            f"DOOR_900 panel LINE shortened {DOOR_PANEL_LEN:.0f}->"
                            f"{DOOR_PANEL_LEN - SHORTEN_BY:.0f}mm; affects all "
                            f"{len(DOOR_SPECS)} instances (D1..D6)"
                        ),
                    )
                ],
                expected_cluster_count=None,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
        notes="대표로 D1 인스턴스 하나만 expected_change로 적었다(schema에 인스턴스 수 필드가 없다). note에 영향받는 인스턴스 수를 적었다.",
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
