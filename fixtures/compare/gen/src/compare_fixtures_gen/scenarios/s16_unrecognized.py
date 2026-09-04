"""S16 -- the after set gains a file with no title block (`detail.dxf`):
that file's frame must come back `unrecognized`."""

from __future__ import annotations

from pathlib import Path

from compare_fixtures_gen.base_plan import build_base_plan, default_clean_regions, ensure_layers, new_doc, save
from compare_fixtures_gen.truth import build_truth, expected_pair, write_truth

SCENARIO_ID = "S16_unrecognized"


def generate(out_root: Path) -> None:
    before = build_base_plan()
    after = build_base_plan()

    detail_doc = new_doc()
    ensure_layers(detail_doc, ["A-WALL", "A-TEXT"])
    dmsp = detail_doc.modelspace()
    dmsp.add_line((0.0, 0.0), (5000.0, 0.0), dxfattribs={"layer": "A-WALL"})
    dmsp.add_line((5000.0, 0.0), (5000.0, 3000.0), dxfattribs={"layer": "A-WALL"})
    dmsp.add_text("상세도 D1", dxfattribs={"layer": "A-TEXT", "height": 150.0}).set_placement((0.0, 3200.0))

    truth = build_truth(
        scenario=SCENARIO_ID,
        description="후 세트에 표제란 없는 파일 detail.dxf를 추가한다. 그 파일은 unrecognized로 분류돼야 한다.",
        expected_pairs=[
            expected_pair(
                sheet_no="A-101",
                status="same",
                match_method="number",
                expected_changes=[],
                expected_cluster_count=0,
                clean_regions=default_clean_regions((0.0, 0.0), 100),
            ),
            expected_pair(
                sheet_no=None,
                status="unrecognized",
                match_method=None,
                expected_changes=[],
                expected_cluster_count=None,
                clean_regions=[],
            ),
        ],
        notes=(
            "detail.dxf에는 ATTRIB이 min_attribs(3) 이상인 블록이 없어 표제란 후보가 없다"
            "(frames.yaml titleblock.min_attribs). sheet_no는 알 수 없으므로 null이고 파일 위치로만 식별된다."
        ),
    )

    base = out_root / SCENARIO_ID
    save(before.doc, base / "before" / "A-101.dxf")
    save(after.doc, base / "after" / "A-101.dxf")
    save(detail_doc, base / "after" / "detail.dxf")
    write_truth(base / "truth.json", truth)
