"""S08 -- move 3 wall entities to a new layer (geometry unchanged): `minor` 3,
reason `layer_only`, cluster 0."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions, ensure_layers
from compare_fixtures_gen.plant import bbox_of
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S08_layer_only"
WALL_NAMES = ["part_v1", "part_v2", "part_h"]
NEW_LAYER = "A-WALL2"


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()
    ensure_layers(after.doc, [NEW_LAYER])

    changes = []
    for name in WALL_NAMES:
        w_before = before.walls[name]
        w_after = after.walls[name]
        bbox = bbox_of([w_before])
        w_after.dxf.layer = NEW_LAYER
        changes.append(
            expected_change(
                kind="modified",
                etype="LWPOLYLINE",
                layer="A-WALL",
                before_handle=w_before.dxf.handle,
                after_handle=w_after.dxf.handle,
                minor=True,
                minor_reason="layer_only",
                bbox=bbox,
                note=f"wall '{name}' moved from A-WALL to {NEW_LAYER} (layer only, geometry unchanged)",
            )
        )

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="벽 3개의 레이어만 A-WALL2로 바꾼다(기하 동일).",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="same",
                match_method="number",
                expected_changes=changes,
                expected_cluster_count=0,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
