"""``compare/markup.py``: the drawing the site actually receives.

Checked against ``docs/contracts/compare-dxf.md`` §2 (what a markup drawing is),
§5 (cloud and badge geometry) and §6 (the revision table), because R1-10 and the
user's Windows check have no other statement of what the file should contain.

The clusters these tests hand the writer are the *real* sidecar objects: one
scenario is compared, ``clusters.json`` is written, and the decisions are set on
the file the way the review screen sets them. So "the cloud is where the sidecar
says" is a comparison between two files rather than between a function and a
restatement of itself.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from ezdxf.document import Drawing

from halo_engine.bundle.guard import OriginalWriteGuardError
from halo_engine.compare.cluster import badge_geometry
from halo_engine.compare.compare_dxf import (
    APPID,
    build_sidecar,
    write_clusters_json,
    write_compare_dxf,
)
from halo_engine.compare.config import scale_factor
from halo_engine.compare.markup import (
    ELLIPSIS,
    MARKUP_DXF_NAME,
    WARN_TABLE_OUTSIDE_FRAME,
    RevisionRow,
    approved_clusters,
    draw_revision_table,
    fit_text,
    titleblock_bbox,
    write_markup_dxf,
)

from .scenario_helpers import FIXTURES, packaged_compare_config, run_scenario

CONFIG = packaged_compare_config()
RUN_DATE = "2026-09-04"
LAYER = CONFIG.revision_layer(RUN_DATE)


# --------------------------------------------------------------------------- fixtures


def _tmp_root() -> Path:
    import tempfile

    root = Path(tempfile.gettempdir()) / "halo-r1-09-markup"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _side(scenario: str, folder: str) -> Path:
    return sorted((FIXTURES / scenario / folder).glob("*.dxf"))[0]


def _sheet(run: Any) -> Any:
    """The sheet these tests mark up: the first one that actually changed.

    ``S13`` holds two 도곽 in one drawing and only the second one was revised;
    a markup of the unchanged sheet would have nothing to draw.
    """
    for sheet in run.sheets.values():
        if sheet.clusters:
            return sheet
    return next(iter(run.sheets.values()))


@lru_cache(maxsize=8)
def _compared(scenario: str) -> tuple[Path, dict[str, Any]]:
    """Compare one scenario's first sheet and hand back its 후 DXF and sidecar.

    Cached: every test in this module works from the same comparison, and
    comparing ``S13`` twice costs more than the whole module otherwise does.
    """
    run = run_scenario(scenario)
    sheet = _sheet(run)
    out = _tmp_root() / scenario
    out.mkdir(parents=True, exist_ok=True)
    after = _side(scenario, run.truth["after_dir"])

    result = write_compare_dxf(
        before_doc=ezdxf.readfile(str(_side(scenario, run.truth["before_dir"]))),
        after_doc=ezdxf.readfile(str(after)),
        before_frame=sheet.before_frame,
        after_frame=sheet.after_frame,
        changes=sheet.diff.changes,
        clusters=sheet.clusters,
        config=CONFIG,
        run_date=RUN_DATE,
        offset=sheet.diff.offset,
        out_path=out / "compare.dxf",
        allowed_roots=[out],
    )
    payload = build_sidecar(
        pair_id="01J8QK00000000000000000MRK",
        pair_key=sheet.after_frame.norm_key,
        run_date=RUN_DATE,
        layer=LAYER,
        after_frame=sheet.after_frame,
        offset=sheet.diff.offset,
        changes=sheet.diff.changes,
        clusters=sheet.clusters,
        handle_to_cluster=result.handle_to_cluster,
        change_handles=result.change_handles,
    )
    write_clusters_json(payload, out / "clusters.json", allowed_roots=[out])
    return after, json.loads((out / "clusters.json").read_text(encoding="utf-8"))


def _frame(scenario: str) -> Any:
    return _sheet(run_scenario(scenario)).after_frame


def _clusters(scenario: str, decisions: dict[int, str] | None = None) -> list[dict[str, Any]]:
    """The sidecar's clusters with the review applied (default: everything approved)."""
    _after, payload = _compared(scenario)
    clusters = json.loads(json.dumps(payload["clusters"]))  # a copy per test
    for cluster in clusters:
        cluster["decision"] = (decisions or {}).get(int(cluster["number"]), "approved")
    return list(clusters)


def _write(
    scenario: str,
    tmp_path: Path,
    *,
    decisions: dict[int, str] | None = None,
    clusters: list[dict[str, Any]] | None = None,
) -> Any:
    after, _payload = _compared(scenario)
    return write_markup_dxf(
        after_working_dxf=after,
        clusters=clusters if clusters is not None else _clusters(scenario, decisions),
        frame=_frame(scenario),
        run_date=RUN_DATE,
        layer_name=LAYER,
        config=CONFIG,
        out_path=tmp_path / MARKUP_DXF_NAME,
        allowed_roots=[tmp_path],
    )


def _revision_entities(doc: Drawing) -> list[Any]:
    return [entity for entity in doc.modelspace() if entity.dxf.layer == LAYER]


def _role(entity: Any) -> str:
    if not entity.has_xdata(APPID):
        return ""
    for _code, value in entity.get_xdata(APPID):
        if str(value).startswith("role="):
            return str(value).removeprefix("role=")
    return ""


# --------------------------------------------------------------------------- the layer


def test_the_revision_layer_carries_the_configured_colour(tmp_path: Path) -> None:
    """Contract §2: ``REV-<YYYYMMDD>``, ``cloud.color`` (1, red)."""
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    doc = ezdxf.readfile(str(result.path))
    assert LAYER in doc.layers
    assert doc.layers.get(LAYER).dxf.color == CONFIG.cloud.color


def test_the_whole_after_drawing_is_copied_not_just_the_frame(tmp_path: Path) -> None:
    """Contract §2: 마크업 = 후 작업용 DXF 사본 + REV 레이어 + 표.

    ``S13`` holds two sheets in one file. The compare DXF of A-101 contains only
    A-101; the *markup* of A-101 still contains the whole drawing, because it is
    the file the office will open in place of the original.
    """
    result = _write("S13_multi_sheet", tmp_path)
    assert result is not None
    source = ezdxf.readfile(str(_compared("S13_multi_sheet")[0]))
    doc = ezdxf.readfile(str(result.path))

    source_layers = {layer.dxf.name for layer in source.layers}
    assert source_layers <= {layer.dxf.name for layer in doc.layers}

    copied = [entity for entity in doc.modelspace() if entity.dxf.layer != LAYER]
    assert len(copied) == len(list(source.modelspace()))


def test_the_markup_never_carries_the_comparison_layers(tmp_path: Path) -> None:
    """Contract §2: ``__CMP_*`` is review scaffolding and stays out of the output."""
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    doc = ezdxf.readfile(str(result.path))
    assert not [name for name in (layer.dxf.name for layer in doc.layers) if "__CMP" in name]


# --------------------------------------------------------------------------- 승인만


def test_only_approved_clusters_are_drawn(tmp_path: Path) -> None:
    """Brief DoD: 무시·대기 clusters get neither a cloud nor a table row."""
    scenario = "S12_whole_redraw"
    numbers = sorted(int(c["number"]) for c in _clusters(scenario))
    assert len(numbers) >= 2, "this scenario is meant to produce several clusters"
    approved, *rest = numbers

    for verdict in ("ignored", "pending"):
        decisions = {number: verdict for number in rest}
        decisions[approved] = "approved"
        result = _write(scenario, tmp_path / verdict, decisions=decisions)
        assert result is not None
        assert result.numbers == [approved]

        doc = ezdxf.readfile(str(result.path))
        badges = [
            entity
            for entity in _revision_entities(doc)
            if entity.dxftype() == "TEXT" and _role(entity) == "badge_text"
        ]
        assert [entity.dxf.text for entity in badges] == [str(approved)]
        assert result.table is not None
        assert [row.number for row in result.table.rows] == [approved]


def test_a_sheet_with_nothing_approved_produces_no_file(tmp_path: Path) -> None:
    """Contract §6: the 도곽 drops out of the export entirely."""
    decisions = {int(c["number"]): "ignored" for c in _clusters("S02_move_door")}
    result = _write("S02_move_door", tmp_path, decisions=decisions)
    assert result is None
    assert not (tmp_path / MARKUP_DXF_NAME).exists()


def test_approved_clusters_come_back_in_number_order() -> None:
    clusters = [{"number": 3, "decision": "approved"}, {"number": 1, "decision": "approved"}]
    assert [c["number"] for c in approved_clusters(clusters)] == [1, 3]


# --------------------------------------------------------------------------- clouds


def test_the_cloud_has_the_sidecars_own_vertices(tmp_path: Path) -> None:
    """Contract §5: screen C and the printed sheet must show the same cloud.

    Compared vertex by vertex against ``clusters.json`` -- recomputing the
    polyline here would only prove that the same code was run twice.
    """
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    doc = ezdxf.readfile(str(result.path))
    clouds = [entity for entity in _revision_entities(doc) if _role(entity) == "cloud"]
    assert len(clouds) == 1

    expected = _clusters("S02_move_door")[0]["cloud"]["points"]
    drawn = [
        (round(point[0], 3), round(point[1], 3), round(point[4], 3))
        for point in clouds[0].get_points("xyseb")
    ]
    assert drawn == [(round(p[0], 3), round(p[1], 3), round(p[2], 3)) for p in expected]
    assert clouds[0].closed


def test_the_badge_is_a_closed_triangle_with_the_cluster_number(tmp_path: Path) -> None:
    """Contract §5: equilateral triangle, apex up, the number at its centroid."""
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    doc = ezdxf.readfile(str(result.path))
    cluster = _clusters("S02_move_door")[0]
    factor = scale_factor(_frame("S02_move_door").scale_denominator)
    badge = badge_geometry(cluster["bbox"], CONFIG, factor)

    shapes = [entity for entity in _revision_entities(doc) if _role(entity) == "badge_shape"]
    assert len(shapes) == 1
    assert shapes[0].closed
    assert [(round(x, 3), round(y, 3)) for x, y in shapes[0].get_points("xy")] == [
        (round(x, 3), round(y, 3)) for x, y in badge.points
    ]

    texts = [entity for entity in _revision_entities(doc) if _role(entity) == "badge_text"]
    assert len(texts) == 1
    assert texts[0].dxf.text == str(cluster["number"])
    assert round(texts[0].dxf.height, 3) == round(badge.text_height, 3)
    placement = texts[0].get_placement()[1]
    assert (round(placement.x, 3), round(placement.y, 3)) == tuple(cluster["badge"]["center"])


def test_every_revision_entity_carries_its_cluster_and_role(tmp_path: Path) -> None:
    """Contract §4: ``cluster=<number>``, ``role=<cloud|badge_shape|badge_text>``."""
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    doc = ezdxf.readfile(str(result.path))
    roles = []
    for entity in _revision_entities(doc):
        if not entity.has_xdata(APPID):
            continue
        tags = [str(value) for _code, value in entity.get_xdata(APPID)]
        assert tags[0] == "cluster=1"
        roles.append(tags[1].removeprefix("role="))
    assert sorted(roles) == ["badge_shape", "badge_text", "cloud"]


# --------------------------------------------------------------------------- the table


def _table_texts(doc: Drawing) -> list[str]:
    return [
        entity.dxf.text
        for entity in doc.modelspace()
        if entity.dxf.layer == LAYER and entity.dxftype() == "TEXT" and not entity.has_xdata(APPID)
    ]


def test_the_table_has_a_header_row_and_one_row_per_approved_cluster(tmp_path: Path) -> None:
    """Contract §6: 머리글 행은 ``revtable.columns``, 행 = 승인된 클러스터."""
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    assert result.table is not None
    assert [row.number for row in result.table.rows] == [1]
    assert len(result.table.row_y) == len(result.table.rows) + 2

    doc = ezdxf.readfile(str(result.path))
    texts = _table_texts(doc)
    assert texts[: len(CONFIG.revtable.columns)] == CONFIG.revtable.columns
    assert "1" in texts
    assert RUN_DATE in texts


def test_the_row_text_is_the_users_label_when_there_is_one(tmp_path: Path) -> None:
    """Contract §6: 내용 = ``user_label``이 있으면 그것, 없으면 ``label``."""
    clusters = _clusters("S02_move_door")
    clusters[0]["user_label"] = "문 위치 변경"
    result = _write("S02_move_door", tmp_path, clusters=clusters)
    assert result is not None
    assert result.table is not None
    assert result.table.rows[0].content == "문 위치 변경"
    assert "문 위치 변경" in _table_texts(ezdxf.readfile(str(result.path)))


def test_the_automatic_label_is_used_when_the_user_typed_nothing(tmp_path: Path) -> None:
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    assert result.table is not None
    assert result.table.rows[0].content == _clusters("S02_move_door")[0]["label"]


def test_the_tables_top_right_corner_meets_the_title_blocks_top_left(tmp_path: Path) -> None:
    """Contract §6: ``revtable.anchor = titleblock_left``, growing left and down."""
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    assert result.table is not None
    doc = ezdxf.readfile(str(result.path))
    box, warnings = titleblock_bbox(doc, _frame("S02_move_door"))
    assert box is not None and not warnings

    table = result.table
    assert table.right == pytest.approx(box[0])
    assert table.top == pytest.approx(box[3])
    assert table.left < table.right
    assert table.bottom < table.top


def test_the_table_is_drawn_with_lines_and_text_only(tmp_path: Path) -> None:
    """Brief Constraints: no TABLE entity, no proxy -- ZWCAD has to read this."""
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    doc = ezdxf.readfile(str(result.path))
    kinds = {entity.dxftype() for entity in _revision_entities(doc) if not entity.has_xdata(APPID)}
    assert kinds == {"LINE", "TEXT"}


def test_the_table_grid_matches_the_configured_widths_and_heights(tmp_path: Path) -> None:
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    table = result.table
    assert table is not None
    widths = [b - a for a, b in zip(table.column_x, table.column_x[1:], strict=False)]
    assert widths == pytest.approx(CONFIG.revtable.col_widths)
    heights = [a - b for a, b in zip(table.row_y, table.row_y[1:], strict=False)]
    assert heights == pytest.approx([CONFIG.revtable.row_height] * len(heights))


def test_a_long_content_is_cut_to_the_column_with_an_ellipsis() -> None:
    """Contract §6: 긴 내용은 열 너비에 맞춰 잘라 ``…``."""
    long_text = "가" * 200
    fitted = fit_text(long_text, CONFIG.revtable.text_height, CONFIG.revtable.col_widths[1])
    assert fitted.endswith(ELLIPSIS)
    assert len(fitted) < len(long_text)
    assert fit_text("짧음", CONFIG.revtable.text_height, CONFIG.revtable.col_widths[1]) == "짧음"


def test_a_table_that_would_leave_the_frame_is_still_drawn_and_warned_about() -> None:
    """Brief Defaults for ambiguity: draw it anyway, raise ``revtable_outside_frame``."""
    frame = _frame("S02_move_door")
    doc = ezdxf.readfile(str(_compared("S02_move_door")[0]))
    narrow = type(frame)(**{**frame.__dict__, "bbox": [0.0, 0.0, 1.0, 1.0]})

    table, warnings = draw_revision_table(
        doc,
        frame=narrow,
        rows=[RevisionRow(number=1, content="내용")],
        run_date=RUN_DATE,
        layer_name=LAYER,
        config=CONFIG,
        factor=1.0,
    )
    assert table is not None
    assert WARN_TABLE_OUTSIDE_FRAME in warnings


# --------------------------------------------------------------------------- 축척


def test_a_1_to_50_sheet_draws_everything_half_size(tmp_path: Path) -> None:
    """Contract §5-§6: every size is a ``compare.yaml`` value x ``scale_factor``."""
    frame = _frame("S17_scale_50")
    assert frame.scale_denominator == 50
    assert scale_factor(frame.scale_denominator) == 0.5

    result = _write("S17_scale_50", tmp_path)
    assert result is not None
    table = result.table
    assert table is not None
    assert table.right - table.left == pytest.approx(sum(CONFIG.revtable.col_widths) * 0.5)
    heights = [a - b for a, b in zip(table.row_y, table.row_y[1:], strict=False)]
    assert heights == pytest.approx([CONFIG.revtable.row_height * 0.5] * len(heights))

    doc = ezdxf.readfile(str(result.path))
    text = next(entity for entity in _revision_entities(doc) if _role(entity) == "badge_text")
    assert text.dxf.height == pytest.approx(CONFIG.cloud.badge_text_height * 0.5)


# --------------------------------------------------------------------------- guards


def test_the_drawing_passes_its_own_audit(tmp_path: Path) -> None:
    """Brief Constraints: ``audit()`` 오류 0."""
    result = _write("S02_move_door", tmp_path)
    assert result is not None
    assert [warning for warning in result.warnings if warning.startswith("audit:")] == []
    assert not ezdxf.readfile(str(result.path)).audit().errors


def test_writing_outside_the_allowed_roots_is_refused(tmp_path: Path) -> None:
    """CLAUDE.md rule 1: the write guard, not a code review, keeps originals safe."""
    after, _payload = _compared("S02_move_door")
    with pytest.raises(OriginalWriteGuardError):
        write_markup_dxf(
            after_working_dxf=after,
            clusters=_clusters("S02_move_door"),
            frame=_frame("S02_move_door"),
            run_date=RUN_DATE,
            layer_name=LAYER,
            config=CONFIG,
            out_path=after.parent / "markup.dxf",
            allowed_roots=[tmp_path],
        )
    assert not (after.parent / "markup.dxf").exists()


def test_the_source_drawing_is_never_touched(tmp_path: Path) -> None:
    after, _payload = _compared("S02_move_door")
    before_bytes = after.read_bytes()
    _write("S02_move_door", tmp_path)
    assert after.read_bytes() == before_bytes
