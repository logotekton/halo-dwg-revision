"""S07 -- recreate a hatch with the same boundary but a different starting
vertex (Defaults for ambiguity: same boundary vertices, rotated order) so its
handle changes: `minor`, reason `hatch_regen`, cluster 0."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import HATCH_SPECS, build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S07_hatch_regen"


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    h_before = before.hatches_ansi31[0]
    h_after = after.hatches_ansi31[0]
    bbox = bbox_of([h_before])
    before_handle = h_after.dxf.handle

    x0, y0, x1, y1 = HATCH_SPECS[0]
    pts_rotated = [(x0, y1), (x0, y0), (x1, y0), (x1, y1)]  # same boundary, different start vertex

    msp = after.doc.modelspace()
    msp.delete_entity(h_after)
    new_hatch = msp.add_hatch(dxfattribs={"layer": "A-HATCH", "color": 2})
    new_hatch.paths.add_polyline_path(pts_rotated, is_closed=True)
    new_hatch.set_pattern_fill("ANSI31", scale=40.0)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="해치 1개를 같은 경계로, 시작 정점만 다르게 다시 생성한다(핸들이 바뀐다).",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="same",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="modified",
                        etype="HATCH",
                        layer="A-HATCH",
                        before_handle=before_handle,
                        after_handle=new_hatch.dxf.handle,
                        minor=True,
                        minor_reason="hatch_regen",
                        bbox=bbox,
                        note="hatch re-generated with the same boundary, rotated start vertex",
                    )
                ],
                expected_cluster_count=0,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
        notes="경계 다각형은 동일하고(bbox 동일) 시작 정점 순서만 바뀌었다. minor.fold의 hatch_regen으로 접혀야 한다.",
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
