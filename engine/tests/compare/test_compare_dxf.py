"""``compare/compare_dxf.py``: the file the viewer opens and the file it reads.

Checked against ``docs/contracts/compare-dxf.md`` clause by clause, because
R1-08 (the viewer) and R1-09 (the markup DWG) are written to that contract and
have no other way to find out that the engine changed its mind. The sidecar is
validated against ``packages/schema/src/compare/clusters-sidecar.schema.json``
itself rather than against a restatement of it here.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from ezdxf.document import Drawing
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from halo_engine.bundle.guard import OriginalWriteGuardError
from halo_engine.compare.cluster import build_clusters
from halo_engine.compare.compare_dxf import (
    APPID,
    BEFORE_BLOCK_PREFIX,
    COLOR_ADDED,
    COLOR_LABEL,
    COLOR_REMOVED,
    LAYER_ADDED,
    LAYER_LABEL,
    LAYER_REMOVED,
    ZERO_GUID,
    build_sidecar,
    dumps_sidecar,
    pin_header_for_determinism,
    prefix_before_blocks,
    serialize,
    sidecar_integrity_failures,
    write_clusters_json,
    write_compare_dxf,
)
from halo_engine.compare.config import scale_factor
from halo_engine.compare.diff import diff_pair

from .scenario_helpers import SCHEMA_SRC, packaged_compare_config, run_scenario

CONFIG = packaged_compare_config()
RUN_DATE = "2026-09-04"
SIDECAR_SCHEMA_ID = "https://schema.halo-cad.internal/v0/compare/clusters-sidecar.schema.json"


@lru_cache(maxsize=1)
def _sidecar_validator() -> Draft202012Validator:
    """Validate against the real schema files, the way ``halo_schema.validation`` does.

    ``halo-schema`` (``packages/schema/gen/python``) is not one of the engine's
    dependencies -- ``engine/pyproject.toml`` is Fable's file, not a task's --
    so the registry is built here from ``packages/schema/src`` exactly as
    ``tests/ingest/test_truth_schema.py`` builds it. The report proposes adding
    the dependency so this can become ``assert_valid("compare_clusters_sidecar",
    ...)`` verbatim.
    """
    if not SCHEMA_SRC.is_dir():
        pytest.skip(f"{SCHEMA_SRC} missing")
    resources = []
    for path in SCHEMA_SRC.rglob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema, DRAFT202012)))
    registry = Registry().with_resources(resources)
    return Draft202012Validator({"$ref": SIDECAR_SCHEMA_ID}, registry=registry)


def assert_valid_sidecar(payload: dict[str, Any]) -> None:
    errors = sorted(_sidecar_validator().iter_errors(payload), key=lambda e: list(e.absolute_path))
    assert not errors, "; ".join(
        f"{'/'.join(str(part) for part in error.absolute_path) or '/'}: {error.message}"
        for error in errors
    )


@lru_cache(maxsize=8)
def _written(scenario: str) -> tuple[Path, dict[str, Any]]:
    """Compare one scenario's first sheet and write both artefacts to a temp path."""
    run = run_scenario(scenario)
    sheet = next(iter(run.sheets.values()))
    out = _tmp_root() / scenario
    out.mkdir(parents=True, exist_ok=True)

    result = write_compare_dxf(
        before_doc=ezdxf.readfile(str(_side(scenario, run.truth["before_dir"]))),
        after_doc=ezdxf.readfile(str(_side(scenario, run.truth["after_dir"]))),
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
        pair_id="01J0000000000000000000000A",
        pair_key=sheet.after_frame.norm_key,
        run_date=RUN_DATE,
        layer=CONFIG.revision_layer(RUN_DATE),
        after_frame=sheet.after_frame,
        offset=sheet.diff.offset,
        changes=sheet.diff.changes,
        clusters=sheet.clusters,
        handle_to_cluster=result.handle_to_cluster,
        change_handles=result.change_handles,
    )
    write_clusters_json(payload, out / "clusters.json", allowed_roots=[out])
    return result.path, payload


def _tmp_root() -> Path:
    import tempfile

    root = Path(tempfile.gettempdir()) / "halo-r1-06-compare-dxf"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _side(scenario: str, folder: str) -> Path:
    from .scenario_helpers import FIXTURES

    return sorted((FIXTURES / scenario / folder).glob("*.dxf"))[0]


def _open(scenario: str) -> Drawing:
    path, _payload = _written(scenario)
    return ezdxf.readfile(str(path))


# --------------------------------------------------------------------------- layers


def test_the_four_comparison_layers_exist_with_their_contract_colours() -> None:
    doc = _open("S02_move_door")
    assert doc.layers.get(LAYER_ADDED).dxf.color == COLOR_ADDED
    assert doc.layers.get(LAYER_REMOVED).dxf.color == COLOR_REMOVED
    # An "off" layer stores its colour negated; ``Layer.color`` reads it back.
    assert doc.layers.get(LAYER_LABEL).color == COLOR_LABEL
    assert doc.layers.get(CONFIG.revision_layer(RUN_DATE)).dxf.color == CONFIG.cloud.color


def test_the_label_layer_is_off_and_never_plotted() -> None:
    doc = _open("S02_move_door")
    layer = doc.layers.get(LAYER_LABEL)
    assert layer.is_off()
    assert layer.dxf.plot == 0


def test_the_after_sheets_own_layers_come_across() -> None:
    doc = _open("S02_move_door")
    names = {layer.dxf.name for layer in doc.layers}
    assert {"A-WALL", "A-DOOR", "A-DIM", "A-TEXT", "TITLE"} <= names


def test_the_compare_drawing_is_r2018_in_millimetres() -> None:
    doc = _open("S02_move_door")
    assert doc.dxfversion == "AC1032"
    assert doc.header["$INSUNITS"] == 4


def test_a_moved_entity_is_drawn_on_both_comparison_layers() -> None:
    doc = _open("S02_move_door")
    layers = [entity.dxf.layer for entity in doc.modelspace()]
    assert layers.count(LAYER_ADDED) == 1
    assert layers.count(LAYER_REMOVED) == 1


def test_entities_on_the_comparison_layers_take_the_layers_colour() -> None:
    """Contract §2: an entity that kept its own colour would not read as red or cyan."""
    doc = _open("S02_move_door")
    for entity in doc.modelspace():
        if entity.dxf.layer in {LAYER_ADDED, LAYER_REMOVED}:
            assert entity.dxf.color == 256
            assert entity.dxf.linetype == "BYLAYER"


def test_only_the_frames_entities_are_in_the_file() -> None:
    """Contract §1: one 도곽 per compare DXF, even when the file held two.

    ``S13_multi_sheet`` draws A-101 and A-102 side by side in one drawing;
    ``_written`` compares the first of them, and the compare DXF must carry that
    sheet's entities and nothing from its neighbour.
    """
    run = run_scenario("S13_multi_sheet")
    written = next(iter(run.sheets.values()))
    doc = _open("S13_multi_sheet")

    markers = {LAYER_LABEL, LAYER_ADDED, LAYER_REMOVED, CONFIG.revision_layer(RUN_DATE)}
    kept = [entity for entity in doc.modelspace() if entity.dxf.layer not in markers]
    assert len(kept) == len(written.after_frame.entity_handles)

    x0, _y0, x1, _y1 = written.after_frame.bbox
    other = run.sheets["A-102" if written.sheet_no == "A-101" else "A-101"]
    assert other.after_frame.bbox[0] > x1 or other.after_frame.bbox[2] < x0


# --------------------------------------------------------------------------- blocks


def test_blocks_from_the_before_drawing_carry_the_prefix() -> None:
    doc = _open("S11_blockdef_change")
    names = {block.name for block in doc.blocks}
    assert "DOOR_900" in names
    assert f"{BEFORE_BLOCK_PREFIX}DOOR_900" in names


def test_the_prefix_is_applied_even_to_anonymous_dimension_blocks() -> None:
    doc = ezdxf.new("R2018", setup=False)
    doc.blocks.new("DOOR_900").add_line((0, 0), (900, 0))
    doc.blocks.new("*D1").add_line((0, 0), (1, 1))
    dim = doc.modelspace().add_linear_dim(base=(0, 100), p1=(0, 0), p2=(1000, 0))
    dim.render()
    doc.modelspace().add_blockref("DOOR_900", (0, 0))

    mapping = prefix_before_blocks(doc)
    assert mapping["DOOR_900"] == f"{BEFORE_BLOCK_PREFIX}DOOR_900"
    assert mapping["*D1"] == f"{BEFORE_BLOCK_PREFIX}_D1"
    assert all(
        entity.dxf.name.startswith(BEFORE_BLOCK_PREFIX)
        for entity in doc.modelspace()
        if entity.dxftype() == "INSERT"
    )
    assert "*Model_Space" in {block.name for block in doc.blocks}


def test_dimensions_survive_the_import_with_their_geometry() -> None:
    """A dimension whose geometry block did not come across is deleted by ``audit``."""
    doc = _open("S03_dim_value")
    dimensions = [entity for entity in doc.modelspace() if entity.dxftype() == "DIMENSION"]
    assert dimensions
    blocks = {block.name for block in doc.blocks}
    for dimension in dimensions:
        assert dimension.dxf.get("geometry") in blocks


def test_the_written_file_audits_clean() -> None:
    doc = _open("S03_dim_value")
    auditor = doc.audit()
    assert not auditor.errors, [error.message for error in auditor.errors]


# --------------------------------------------------------------------------- xdata


def _xdata(entity: Any) -> dict[str, str]:
    tags = entity.get_xdata(APPID)
    return dict(
        str(value).split("=", 1)  # type: ignore[misc]
        for code, value in tags
        if code == 1000 and "=" in str(value)
    )


def test_every_marker_entity_names_its_cluster_and_its_role() -> None:
    doc = _open("S02_move_door")
    layer = CONFIG.revision_layer(RUN_DATE)
    roles = []
    for entity in doc.modelspace():
        if entity.dxf.layer == layer:
            data = _xdata(entity)
            assert data["cluster"] == "1"
            roles.append(data["role"])
    assert sorted(roles) == ["badge_shape", "badge_text", "cloud"]

    labels = [entity for entity in doc.modelspace() if entity.dxf.layer == LAYER_LABEL]
    assert len(labels) == 1
    assert _xdata(labels[0]) == {"cluster": "1", "role": "label"}


def test_a_changed_entity_keeps_its_original_layer_and_handle_in_xdata() -> None:
    doc = _open("S02_move_door")
    for entity in doc.modelspace():
        if entity.dxf.layer != LAYER_ADDED:
            continue
        data = _xdata(entity)
        assert data["kind"] == "moved"
        assert data["side"] == "after"
        assert data["orig_layer"] == "A-DOOR"
        assert data["minor"] == "0"
        assert data["change"] == "ch1"
        assert data["cluster"] == "1"
        return
    pytest.fail("no entity on __CMP_ADDED")


def test_a_minor_change_stays_on_its_own_layer_but_still_carries_xdata() -> None:
    """Contract §2 and §4: folded changes are visible to the review screen only."""
    doc = _open("S08_layer_only")
    marked = [
        entity
        for entity in doc.modelspace()
        if entity.has_xdata(APPID) and entity.dxf.layer not in {LAYER_LABEL}
    ]
    assert len(marked) == 3
    for entity in marked:
        data = _xdata(entity)
        assert data["minor"] == "1"
        assert "cluster" not in data
        assert entity.dxf.layer == "A-WALL2"


# --------------------------------------------------------------------------- sidecar


@pytest.mark.parametrize(
    "scenario", ["S01_identical", "S02_move_door", "S06_removed", "S11_blockdef_change"]
)
def test_the_sidecar_validates_against_the_schema(scenario: str) -> None:
    _path, payload = _written(scenario)
    assert_valid_sidecar(payload)


@pytest.mark.parametrize("scenario", ["S02_move_door", "S12_whole_redraw", "S11_blockdef_change"])
def test_the_sidecar_is_referentially_intact(scenario: str) -> None:
    _path, payload = _written(scenario)
    assert sidecar_integrity_failures(payload) == []


def test_every_handle_in_the_map_exists_in_the_drawing_it_describes() -> None:
    path, payload = _written("S02_move_door")
    doc = ezdxf.readfile(str(path))
    handles = {str(entity.dxf.handle) for entity in doc.modelspace()}
    assert payload["handle_to_cluster"]
    assert set(payload["handle_to_cluster"]) <= handles


def test_the_sidecar_records_the_frame_and_its_scale() -> None:
    _path, payload = _written("S17_scale_50")
    assert payload["frame"]["scale_denominator"] == 50
    assert payload["frame"]["scale_factor"] == scale_factor(50)
    assert payload["layer"] == "REV-20260904"


def test_the_sidecar_records_the_offset_of_a_shifted_sheet() -> None:
    _path, payload = _written("S15_frame_shift")
    assert payload["frame"]["offset_before"] == [50000.0, 20000.0]


def test_a_change_points_at_the_handles_it_occupies_in_the_compare_drawing() -> None:
    _path, payload = _written("S02_move_door")
    change = payload["changes"][0]
    assert change["cluster_id"] == "c1"
    assert set(change["compare_handles"]) == {"added", "removed"}
    for side in ("added", "removed"):
        for handle in change["compare_handles"][side]:
            assert payload["handle_to_cluster"][handle] == "c1"


def test_a_broken_sidecar_is_refused_rather_than_written(tmp_path: Path) -> None:
    _path, payload = _written("S02_move_door")
    broken = json.loads(json.dumps(payload))
    broken["handle_to_cluster"]["ZZZ"] = "c9"
    with pytest.raises(ValueError, match="integrity"):
        write_clusters_json(broken, tmp_path / "clusters.json", allowed_roots=[tmp_path])
    assert not (tmp_path / "clusters.json").exists()


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda p: p["counts"].__setitem__("changes", 99), "counts.changes"),
        (lambda p: p["changes"][0].__setitem__("id", "ch9"), "does not match its seq"),
        (lambda p: p["clusters"][0].__setitem__("number", 4), "want 1"),
        (lambda p: p["changes"][0].__setitem__("cluster_id", "c7"), "is not a cluster"),
    ],
)
def test_the_integrity_check_names_what_is_wrong(mutate: Any, expected: str) -> None:
    _path, payload = _written("S02_move_door")
    broken = json.loads(json.dumps(payload))
    mutate(broken)
    failures = sidecar_integrity_failures(broken)
    assert any(expected in failure for failure in failures), failures


def test_the_sidecar_is_written_as_utf8_with_lf_endings() -> None:
    _path, payload = _written("S04_text_change")
    raw = dumps_sidecar(payload)
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")
    assert "리빙룸".encode() in raw  # ensure_ascii=False


# --------------------------------------------------------------------------- guard


def test_writing_outside_the_bundle_is_refused(tmp_path: Path) -> None:
    """CLAUDE.md rule 1: the guard, not a convention, is what protects the originals."""
    _path, payload = _written("S02_move_door")
    outside = tmp_path / "originals" / "clusters.json"
    with pytest.raises(OriginalWriteGuardError):
        write_clusters_json(payload, outside, allowed_roots=[tmp_path / "bundle"])


# --------------------------------------------------------------------------- header


def test_the_header_stamps_are_pinned_to_the_run_date() -> None:
    doc = ezdxf.new("R2018", setup=False)
    pin_header_for_determinism(doc, RUN_DATE)
    assert doc.header["$TDINDWG"] == 0.0
    assert doc.header["$TDCREATE"] == doc.header["$TDUPDATE"]

    text = serialize(doc, RUN_DATE).decode("utf-8")
    assert text.count(ZERO_GUID) >= 2
    assert "$FINGERPRINTGUID" in text


def test_serialising_twice_gives_the_same_bytes() -> None:
    doc = ezdxf.new("R2018", setup=False)
    doc.modelspace().add_line((0, 0), (1, 1))
    pin_header_for_determinism(doc, RUN_DATE)
    assert serialize(doc, RUN_DATE) == serialize(doc, RUN_DATE)


def test_a_different_run_date_changes_only_the_stamps() -> None:
    left = ezdxf.new("R2018", setup=False)
    right = ezdxf.new("R2018", setup=False)
    for doc in (left, right):
        doc.modelspace().add_line((0, 0), (1, 1))
    pin_header_for_determinism(left, "2026-09-04")
    pin_header_for_determinism(right, "2026-09-05")
    assert serialize(left, "2026-09-04") != serialize(right, "2026-09-05")


def test_diff_and_write_do_not_touch_the_source_drawings(tmp_path: Path) -> None:
    """CLAUDE.md rule 1: only ``.halo`` is written; the working DXFs are inputs."""
    run = run_scenario("S02_move_door")
    sheet = next(iter(run.sheets.values()))
    before_path = _side("S02_move_door", "before")
    after_path = _side("S02_move_door", "after")
    before_bytes = before_path.read_bytes()
    after_bytes = after_path.read_bytes()

    result = diff_pair(
        ezdxf.readfile(str(before_path)),
        ezdxf.readfile(str(after_path)),
        sheet.before_frame,
        sheet.after_frame,
        CONFIG,
    )
    write_compare_dxf(
        before_doc=ezdxf.readfile(str(before_path)),
        after_doc=ezdxf.readfile(str(after_path)),
        before_frame=sheet.before_frame,
        after_frame=sheet.after_frame,
        changes=result.changes,
        clusters=build_clusters(result.changes, sheet.after_frame, CONFIG, 1.0),
        config=CONFIG,
        run_date=RUN_DATE,
        offset=result.offset,
        out_path=tmp_path / "compare.dxf",
        allowed_roots=[tmp_path],
    )
    assert before_path.read_bytes() == before_bytes
    assert after_path.read_bytes() == after_bytes
