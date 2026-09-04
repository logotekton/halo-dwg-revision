"""S03 -- move a linear dimension's measurement point so its value changes
(Defaults for ambiguity: definition-point move, no text override): `dimension` 1.
"""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of, union_bbox
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S03_dim_value"
MOVE_DX = 500.0


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    dim_before = before.dimensions[2].dimension  # "room_a_width"
    dim_after = after.dimensions[2].dimension
    bbox_before = bbox_of([dim_before])
    measurement_before = dim_after.get_measurement()

    p3 = dim_after.dxf.defpoint3
    dim_after.dxf.defpoint3 = (p3.x + MOVE_DX, p3.y, p3.z)
    dim_after.render()
    measurement_after = dim_after.get_measurement()

    bbox_after = bbox_of([dim_after])
    bbox = union_bbox(bbox_before, bbox_after)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="치수 1개(room_a_width)의 두 번째 측정점을 옮겨 측정값을 바꾼다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="changed",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="dimension",
                        etype="DIMENSION",
                        layer="A-DIM",
                        before_handle=dim_before.dxf.handle,
                        after_handle=dim_after.dxf.handle,
                        minor=False,
                        bbox=bbox,
                        note=f"room_a_width measurement {measurement_before:.0f} -> {measurement_after:.0f}mm",
                    )
                ],
                expected_cluster_count=1,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
        notes="정의점(defpoint3)만 옮기고 render()로 다시 그렸다. text override는 쓰지 않았다(브리프 Defaults).",
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
