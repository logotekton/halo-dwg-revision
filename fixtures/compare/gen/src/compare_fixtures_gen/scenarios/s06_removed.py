"""S06 -- delete one column (outline polyline + solid hatch): `removed` 2,
cluster 1 (same location)."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions
from compare_fixtures_gen.plant import bbox_of
from compare_fixtures_gen.scenarios._util import write_pair
from compare_fixtures_gen.truth import build_truth, expected_change, expected_pair

SCENARIO_ID = "S06_removed"


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    col_before = before.columns[0]
    col_after = after.columns[0]
    bbox = bbox_of([col_before.poly, col_before.hatch])

    before_poly_handle = col_before.poly.dxf.handle
    before_hatch_handle = col_before.hatch.dxf.handle

    msp = after.doc.modelspace()
    msp.delete_entity(col_after.poly)
    msp.delete_entity(col_after.hatch)

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="기둥 1개(외곽선 폴리라인 + 솔리드 해치)를 삭제한다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="changed",
                match_method="number",
                expected_changes=[
                    expected_change(
                        kind="removed",
                        etype="LWPOLYLINE",
                        layer="A-COL",
                        before_handle=before_poly_handle,
                        after_handle=None,
                        minor=False,
                        bbox=bbox,
                        note="column outline removed",
                    ),
                    expected_change(
                        kind="removed",
                        etype="HATCH",
                        layer="A-COL",
                        before_handle=before_hatch_handle,
                        after_handle=None,
                        minor=False,
                        bbox=bbox,
                        note="column solid fill removed",
                    ),
                ],
                expected_cluster_count=1,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            )
        ],
        notes="폴리라인과 해치가 같은 위치라 클러스터 1개로 묶여야 한다.",
    )
    write_pair(out_root, SCENARIO_ID, before.doc, after.doc, truth)
