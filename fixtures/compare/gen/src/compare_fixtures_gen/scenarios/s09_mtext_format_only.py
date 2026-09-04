"""S09 -- change the legend MTEXT's formatting codes only (plain text
unchanged): `minor` 1, reason `mtext_format_only`."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S09_mtext_format_only"
NEW_RAW_TEXT = r"범례\P{\fArial;\b1;}A-WALL : 벽체\PA-DOOR : 문\PA-WIND : 창호"


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    mt_before = before.legend_mtext
    mt_after = after.legend_mtext
    bbox = bbox_of([mt_before])
    assert mt_before.plain_text() == mt_after.plain_text()

    mt_after.text = NEW_RAW_TEXT
    assert mt_after.plain_text() == mt_before.plain_text(), "S09 must not change the plain text"

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="범례 MTEXT의 서식 코드만 바꾼다(굵게 추가). 평문 텍스트는 그대로다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="same",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="modified",
                        etype="MTEXT",
                        layer="A-TEXT",
                        before_handle=mt_before.dxf.handle,
                        after_handle=mt_after.dxf.handle,
                        minor=True,
                        minor_reason="mtext_format_only",
                        bbox=bbox,
                        note="legend MTEXT formatting only (bold added); plain text unchanged",
                    )
                ],
                expected_cluster_count=0,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
