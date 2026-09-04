"""``compare/export.py``: the ``compare.export`` job and what it leaves behind.

The compare set is built here with ``repos`` directly instead of through the
ingest and comparison jobs. That is deliberate: what these tests are about is
the *output* -- the folder, the file names, the writer fallback, the change list
and ``run.json`` -- and running two 60-second jobs before every one of them would
turn a broken file name into a timeout. ``tests/api/test_compare_export.py``
drives the real pipeline end to end.

The clusters, the sidecar and the compare DXF are the genuine ones, produced by
the real comparison of a ``fixtures/compare`` scenario, so the geometry the
markup copies is not a fixture written by hand.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from halo_engine.bundle.create import BundleHandle, create_bundle
from halo_engine.compare import export as export_mod
from halo_engine.compare import zwcad
from halo_engine.compare.compare_dxf import build_sidecar, write_clusters_json, write_compare_dxf
from halo_engine.compare.config import load_compare_config
from halo_engine.compare.export import (
    WARN_ZWCAD_UNAVAILABLE,
    WRITER_DXF_ONLY,
    WRITER_ZWCAD,
    ChangeListRow,
    change_list_rows,
    markup_file_stem,
    resolve_output_dir,
    run_export,
    sanitize_file_name,
    write_changes_tsv,
)
from halo_engine.db import repos
from halo_engine.model.drawing import ImportStatus

from .fake_com import FakeComBackend
from .scenario_helpers import FIXTURES, SCHEMA_SRC, packaged_compare_config, run_scenario

CONFIG = packaged_compare_config()
RUN_DATE = "2026-09-04"
BEFORE_DIR_NAME = "변경전"
AFTER_DIR_NAME = "변경후"
RUN_SCHEMA_ID = "https://schema.halo-cad.internal/v0/compare/run.schema.json"


# --------------------------------------------------------------------------- a compare set


@dataclass
class Prepared:
    """One compared, reviewed compare set, ready to export."""

    project_dir: Path
    bundle: BundleHandle
    compare_set_id: str
    pair_ids: list[str]
    app: Any


class _FakeApp:
    """Just enough of a FastAPI app for the job envelope: ``state`` and nothing else.

    ``jobs.get_job_manager`` and ``ws.get_connection_manager`` both lazily put
    their instance on ``app.state``, so an object with a mutable ``state`` is a
    complete substitute -- and it keeps this module out of ``TestClient``, which
    would drag in the whole HTTP stack for a test about file names.
    """

    def __init__(self, settings: Any) -> None:
        class _State:
            pass

        self.state = _State()
        self.state.settings = settings


def _settings(tmp_path: Path) -> Any:
    from halo_engine.config import Settings

    # An acad-bridge path that does not exist: `auto` never reaches acad-ts, and
    # a test that wants it says so explicitly.
    return Settings(
        data_dir=tmp_path / "data",
        dev=True,
        token="dev",
        acad_bridge_bin=tmp_path / "no-acad-bridge.mjs",
    )


@lru_cache(maxsize=4)
def _scenario_artefacts(scenario: str) -> Any:
    """The real comparison of one scenario, computed once for the whole module."""
    return run_scenario(scenario)


def prepare(
    project_dir: Path,
    *,
    scenario: str = "S02_move_door",
    decisions: dict[str, str] | None = None,
) -> Prepared:
    """Build a compared compare set on disk and in the database.

    ``decisions`` maps 도면번호 to the verdict every cluster of that sheet gets
    (default: everything approved). Sheets not named keep ``pending``.
    """
    run = _scenario_artefacts(scenario)
    source = FIXTURES / scenario
    before_dir = project_dir / BEFORE_DIR_NAME
    after_dir = project_dir / AFTER_DIR_NAME
    shutil.copytree(source / run.truth["before_dir"], before_dir)
    shutil.copytree(source / run.truth["after_dir"], after_dir)

    bundle = create_bundle(project_dir / ".halo", project_dir.name)
    bundle.layout.ensure_dirs()
    config = load_compare_config(bundle)

    with bundle.session_factory() as session:
        sets = {}
        files: dict[str, str] = {}
        for role, folder in (("before", before_dir), ("after", after_dir)):
            drawing_set = repos.create_drawing_set(session, project_id=bundle.id, label=folder.name)
            drawing_set.role = role
            drawing_set.source_dir = str(folder)
            session.commit()
            sets[role] = drawing_set
            for path in sorted(folder.glob("*.dxf")):
                working = bundle.layout.cache_dxf_dir / f"{role}-{path.stem}.working.dxf"
                shutil.copyfile(path, working)
                row = repos.create_drawing_file(
                    session,
                    drawing_set_id=drawing_set.id,
                    original_path=str(path),
                    original_name=path.name,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    format="DXF",
                    import_status=ImportStatus.DONE.value,
                )
                repos.update_drawing_file(session, row.id, working_dxf_path=str(working))
                files[f"{role}:{path.name}"] = row.id

        compare_set = repos.create_compare_set(
            session,
            project_id=bundle.id,
            before_set_id=sets["before"].id,
            after_set_id=sets["after"].id,
            run_date=RUN_DATE,
            status="compared",
        )

        frame_rows: dict[str, dict[str, str]] = {"before": {}, "after": {}}
        for role in ("before", "after"):
            payload = []
            for sheet in run.sheets.values():
                frame = sheet.before_frame if role == "before" else sheet.after_frame
                frame.file_id = files[f"{role}:{frame.file_name}"]
                payload.append(frame.to_row())
            rows = repos.replace_frames(session, compare_set.id, role, payload)
            for sheet_no, row in zip(run.sheets, rows, strict=True):
                frame_rows[role][str(sheet_no)] = row.id

        pairs = repos.replace_pairs(
            session,
            compare_set.id,
            [
                {
                    "before_frame_id": frame_rows["before"][str(sheet_no)],
                    "after_frame_id": frame_rows["after"][str(sheet_no)],
                    "status": "changed" if sheet.clusters else "same",
                    "match_method": "number",
                    "score": 1.0,
                    "sort_key": str(sheet_no),
                }
                for sheet_no, sheet in run.sheets.items()
            ],
        )

        for pair, (sheet_no, sheet) in zip(pairs, run.sheets.items(), strict=True):
            out_dir = bundle.layout.compare_pair_dir(pair.id)
            out_dir.mkdir(parents=True, exist_ok=True)
            after_path = _source_of(after_dir, sheet.after_frame)
            before_path = _source_of(before_dir, sheet.before_frame)
            dxf = write_compare_dxf(
                before_doc=ezdxf.readfile(str(before_path)),
                after_doc=ezdxf.readfile(str(after_path)),
                before_frame=sheet.before_frame,
                after_frame=sheet.after_frame,
                changes=sheet.diff.changes,
                clusters=sheet.clusters,
                config=config,
                run_date=RUN_DATE,
                offset=sheet.diff.offset,
                out_path=out_dir / "compare.dxf",
                allowed_roots=[bundle.layout.root],
            )
            verdict = (decisions or {}).get(str(sheet_no), "approved")
            payload = build_sidecar(
                pair_id=pair.id,
                pair_key=sheet.after_frame.norm_key,
                run_date=RUN_DATE,
                layer=config.revision_layer(RUN_DATE),
                after_frame=sheet.after_frame,
                offset=sheet.diff.offset,
                changes=sheet.diff.changes,
                clusters=sheet.clusters,
                handle_to_cluster=dxf.handle_to_cluster,
                change_handles=dxf.change_handles,
                decisions={cluster.number: (verdict, None, None) for cluster in sheet.clusters},
            )
            sidecar = write_clusters_json(
                payload, out_dir / "clusters.json", allowed_roots=[bundle.layout.root]
            )
            repos.update_pair(
                session,
                pair.id,
                compare_dxf_path=str(dxf.path),
                clusters_json_path=str(sidecar),
            )
            repos.replace_changes(
                session, pair.id, [change.to_row() for change in sheet.diff.changes]
            )
            rows = repos.replace_clusters(
                session,
                pair.id,
                [cluster.to_row() for cluster in sheet.clusters],
                keep_decisions=False,
            )
            for row in rows:
                repos.update_cluster(session, pair.id, row.number, decision=verdict)

        pair_ids = [pair.id for pair in pairs]
        compare_set_id = compare_set.id

    return Prepared(
        project_dir=project_dir,
        bundle=bundle,
        compare_set_id=compare_set_id,
        pair_ids=pair_ids,
        app=_FakeApp(_settings(project_dir)),
    )


def _source_of(folder: Path, frame: Any) -> Path:
    return folder / frame.file_name


async def _export(prepared: Prepared, **kwargs: Any) -> Any:
    """Run one export job to completion and hand back the ``run`` row."""
    from halo_engine.api import jobs

    manager = jobs.get_job_manager(prepared.app)
    job = manager.create(compare_set_id=prepared.compare_set_id, kind="compare.export")
    return await run_export(
        prepared.app,
        job=job,
        bundle=prepared.bundle,
        compare_set_id=prepared.compare_set_id,
        run_date=RUN_DATE,
        **kwargs,
    )


@pytest.fixture
def prepared(project_dir: Path) -> Any:
    """One approved compare set, with the job manager's pool shut down afterwards."""
    ready = prepare(project_dir)
    yield ready
    manager = getattr(ready.app.state, "job_manager", None)
    if manager is not None:
        manager.shutdown()


def _stats(prepared: Prepared) -> dict[str, Any]:
    with prepared.bundle.session_factory() as session:
        row = repos.get_compare_set(session, prepared.compare_set_id)
        assert row is not None
        return dict(row.stats or {})


# --------------------------------------------------------------------------- output folder


def test_the_first_export_of_a_day_owns_the_plain_folder(tmp_path: Path) -> None:
    project = tmp_path / "한강자이"
    project.mkdir()
    path, layer = resolve_output_dir(project, RUN_DATE, CONFIG)
    assert path == project / CONFIG.output.dir_name / RUN_DATE
    assert layer == "REV-20260904"


def test_a_second_export_of_the_same_day_gets_its_own_folder_and_layer(tmp_path: Path) -> None:
    """Contract §11: 같은 날 두 번째 출력은 ``출력/<날짜>-2/``와 ``REV-<날짜>-2``."""
    project = tmp_path / "한강자이"
    (project / CONFIG.output.dir_name / RUN_DATE).mkdir(parents=True)
    path, layer = resolve_output_dir(project, RUN_DATE, CONFIG)
    assert path.name == f"{RUN_DATE}-2"
    assert layer == "REV-20260904-2"

    path.mkdir(parents=True)
    third, third_layer = resolve_output_dir(project, RUN_DATE, CONFIG)
    assert third.name == f"{RUN_DATE}-3"
    assert third_layer == "REV-20260904-3"


async def test_exporting_twice_writes_two_folders_and_two_layers(prepared: Prepared) -> None:
    """Brief Defaults for ambiguity: 같은 날 재출력은 새 폴더. Never an overwrite."""
    first = await _export(prepared)
    second = await _export(prepared)

    assert Path(first.output_dir).name == RUN_DATE
    assert Path(second.output_dir).name == f"{RUN_DATE}-2"
    assert first.layer_name == "REV-20260904"
    assert second.layer_name == "REV-20260904-2"

    first_file = Path(first.files[0]["path"])
    assert first_file.is_file(), "the first export's drawing is still there"
    assert Path(second.files[0]["path"]).parent != first_file.parent

    doc = ezdxf.readfile(str(Path(second.files[0]["path"])))
    assert "REV-20260904-2" in {layer.dxf.name for layer in doc.layers}


# --------------------------------------------------------------------------- file names


def test_the_file_name_follows_the_configured_pattern() -> None:
    stem = markup_file_stem(CONFIG, sheet_no="A-101", after_label=AFTER_DIR_NAME)
    assert stem == f"A-101_{AFTER_DIR_NAME}_markup"


def test_a_drawing_number_with_illegal_characters_is_still_a_file_name() -> None:
    assert sanitize_file_name("A-101/2:*?") == "A-101_2___"
    assert sanitize_file_name("   ") == "_"


async def test_the_exported_file_is_named_after_the_sheet_and_the_after_set(
    prepared: Prepared,
) -> None:
    run = await _export(prepared)
    assert len(run.files) == 1
    path = Path(run.files[0]["path"])
    assert path.stem == f"A-101_{AFTER_DIR_NAME}_markup"
    assert path.parent == Path(run.output_dir)


# --------------------------------------------------------------------------- writers


async def test_without_zwcad_the_run_writes_a_dxf_and_says_so(prepared: Prepared) -> None:
    """Brief §2: no DWG writer -> the markup DXF itself, ``writer: dxf-only``."""
    assert not zwcad.detect().available, "this test machine is not meant to have ZWCAD"
    run = await _export(prepared)

    assert run.status == "done"
    assert [entry["writer"] for entry in run.files] == [WRITER_DXF_ONLY]
    assert [entry["format"] for entry in run.files] == ["dxf"]
    assert Path(run.files[0]["path"]).suffix == ".dxf"
    assert WARN_ZWCAD_UNAVAILABLE in _stats(prepared)["export"]["warnings"]


async def test_with_zwcad_the_markup_goes_through_the_com_bridge(
    prepared: Prepared, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Contract §6.1: one hidden instance, ``convert_dxf_to_dwg`` per sheet.

    The COM layer is the fake one every ZWCAD test uses; what is proved here is
    the export's own side of the bargain -- that it asks for a DWG at all, with
    the markup DXF as the input and the output path it reported.
    """
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(
        zwcad,
        "detect",
        lambda: zwcad.ZwcadStatus(
            available=True, installed=True, version="2026", prog_id="ZWCAD.Application", reason=None
        ),
    )
    fake = FakeComBackend()
    run = await _export(prepared, zwcad_com=fake)

    assert [entry["writer"] for entry in run.files] == [WRITER_ZWCAD]
    assert [entry["format"] for entry in run.files] == ["dwg"]
    out_path = Path(run.files[0]["path"])
    assert out_path.suffix == ".dwg"
    assert out_path.is_file()

    assert len(fake.apps) == 1, "one hidden instance for the whole run"
    documents = fake.apps[0].Documents
    assert [Path(path).name for path, _read_only in documents.open_calls] == ["markup.dxf"]
    assert documents.open_calls[0][1] is True, "opened read-only"
    saved = documents.documents[0].saveas_calls
    assert [Path(path) for path, _version in saved] == [out_path]
    assert fake.apps[0].quit_calls == 1


def test_the_writer_falls_back_only_where_the_brief_says_it_may(tmp_path: Path) -> None:
    """``acad-ts`` is never chosen by ``auto``: it drops title-block INSERTs."""
    assert export_mod.choose_writer("auto", zwcad_available=True, acad_bridge_bin=None) == (
        WRITER_ZWCAD,
        [],
    )
    writer, warnings = export_mod.choose_writer(
        "auto", zwcad_available=False, acad_bridge_bin=tmp_path / "acad-bridge.mjs"
    )
    assert (writer, warnings) == (WRITER_DXF_ONLY, [WARN_ZWCAD_UNAVAILABLE])
    assert export_mod.choose_writer("dxf-only", zwcad_available=True, acad_bridge_bin=None) == (
        WRITER_DXF_ONLY,
        [],
    )
    writer, warnings = export_mod.choose_writer(
        "acad-ts", zwcad_available=True, acad_bridge_bin=tmp_path / "acad-bridge.mjs"
    )
    assert writer == export_mod.WRITER_ACAD_TS


def test_the_request_only_overrides_the_configured_writer_when_it_is_explicit() -> None:
    assert export_mod.effective_method("auto", CONFIG) == CONFIG.output.dwg_writer
    assert export_mod.effective_method("dxf-only", CONFIG) == "dxf-only"


# --------------------------------------------------------------------------- 승인·무시


async def test_a_sheet_with_nothing_approved_produces_no_drawing(project_dir: Path) -> None:
    """Brief Defaults for ambiguity: 무시 clusters reach the TSV, never the DWG."""
    prepared = prepare(project_dir, decisions={"A-101": "ignored"})
    try:
        run = await _export(prepared)
        assert run.files == []
        assert run.pair_ids == []
        assert run.approved_count == 0
        assert run.ignored_count == 1
        tsv = (Path(run.output_dir) / export_mod.CHANGES_TSV_NAME).read_text("utf-8")
        assert "무시" in tsv
    finally:
        manager = getattr(prepared.app.state, "job_manager", None)
        if manager is not None:
            manager.shutdown()


# --------------------------------------------------------------------------- changes.tsv


def test_the_change_list_has_the_contracts_columns(tmp_path: Path) -> None:
    rows = [
        ChangeListRow(
            sheet_no="A-101",
            sheet_title="1층 평면도",
            number=1,
            kind="moved",
            content="문 위치 변경",
            decision="approved",
            run_date=RUN_DATE,
        ),
        ChangeListRow(
            sheet_no="A-101",
            sheet_title="1층 평면도",
            number=2,
            kind="added",
            content="창 신설",
            decision="ignored",
            run_date=RUN_DATE,
        ),
    ]
    path = write_changes_tsv(rows, tmp_path / "changes.tsv", allowed_roots=[tmp_path])
    payload = path.read_bytes()

    assert not payload.startswith(b"\xef\xbb\xbf"), "UTF-8 without a BOM"
    assert b"\r\n" not in payload, "LF, never CRLF"
    lines = payload.decode("utf-8").split("\n")
    assert lines[0].split("\t") == export_mod.TSV_COLUMNS
    assert lines[1].split("\t") == [
        "A-101",
        "1층 평면도",
        "1",
        "이동",
        "문 위치 변경",
        "승인",
        RUN_DATE,
    ]
    assert lines[2].split("\t")[5] == "무시"
    assert lines[-1] == "", "a trailing newline"


def test_a_tab_inside_a_label_cannot_invent_a_column(tmp_path: Path) -> None:
    row = ChangeListRow(
        sheet_no="A-101",
        sheet_title="",
        number=1,
        kind="text",
        content="앞\t뒤\n다음 줄",
        decision="approved",
        run_date=RUN_DATE,
    )
    path = write_changes_tsv([row], tmp_path / "changes.tsv", allowed_roots=[tmp_path])
    lines = path.read_text("utf-8").rstrip("\n").split("\n")
    assert len(lines) == 2
    assert lines[1].split("\t")[4] == "앞 뒤 다음 줄"


async def test_the_exported_change_list_names_the_sheet_and_the_cluster(
    prepared: Prepared,
) -> None:
    run = await _export(prepared)
    path = Path(run.output_dir) / export_mod.CHANGES_TSV_NAME
    lines = path.read_text("utf-8").rstrip("\n").split("\n")
    assert lines[0].split("\t") == export_mod.TSV_COLUMNS
    assert len(lines) == 2
    cells = lines[1].split("\t")
    assert cells[0] == "A-101"
    assert cells[2] == "1"
    assert cells[3] == "이동"
    assert cells[5] == "승인"
    assert cells[6] == RUN_DATE


def test_the_change_list_is_ordered_by_sheet_then_number() -> None:
    """The list is read next to the drawings, so it follows the drawing order."""

    class _Plan:
        def __init__(self, sheet_no: str, numbers: list[int]) -> None:
            self.sheet_no = sheet_no
            self.sheet_title = ""
            self.decided = [
                {"number": number, "kind": "moved", "label": "x", "decision": "approved"}
                for number in numbers
            ]

    rows = change_list_rows([_Plan("A-101", [1, 2]), _Plan("A-102", [1])], RUN_DATE)  # type: ignore[arg-type]
    assert [(row.sheet_no, row.number) for row in rows] == [
        ("A-101", 1),
        ("A-101", 2),
        ("A-102", 1),
    ]


# --------------------------------------------------------------------------- run.json


@lru_cache(maxsize=1)
def _run_validator() -> Draft202012Validator:
    if not SCHEMA_SRC.is_dir():
        pytest.skip(f"{SCHEMA_SRC} missing")
    resources = []
    for path in SCHEMA_SRC.rglob("*.schema.json"):
        schema = json.loads(path.read_text(encoding="utf-8"))
        resources.append((schema["$id"], Resource.from_contents(schema, DRAFT202012)))
    return Draft202012Validator(
        {"$ref": RUN_SCHEMA_ID}, registry=Registry().with_resources(resources)
    )


def _assert_valid_run(payload: dict[str, Any]) -> None:
    errors = sorted(_run_validator().iter_errors(payload), key=lambda e: list(e.absolute_path))
    assert not errors, "; ".join(
        f"{'/'.join(str(part) for part in error.absolute_path) or '/'}: {error.message}"
        for error in errors
    )


async def test_run_json_is_written_next_to_the_drawings_and_validates(
    prepared: Prepared,
) -> None:
    run = await _export(prepared)
    path = Path(run.output_dir) / export_mod.RUN_JSON_NAME
    payload = json.loads(path.read_text("utf-8"))

    _assert_valid_run(payload)
    assert payload["schema_version"] == export_mod.SCHEMA_VERSION
    assert payload["id"] == run.id
    assert payload["status"] == "done"
    assert payload["layer_name"] == "REV-20260904"
    assert payload["pair_ids"] == prepared.pair_ids
    assert "created_at" not in payload, "a wall-clock stamp has no place in the output"


async def test_run_json_names_its_files_relative_to_its_own_folder(
    prepared: Prepared,
) -> None:
    """Brief Defaults for ambiguity: 출력 폴더 기준 상대 경로.

    The folder is copied to a site PC or attached to a mail; a path from the
    machine that produced it would be noise there.
    """
    run = await _export(prepared)
    payload = json.loads((Path(run.output_dir) / export_mod.RUN_JSON_NAME).read_text("utf-8"))
    assert payload["files"][0]["path"] == f"A-101_{AFTER_DIR_NAME}_markup.dxf"
    assert Path(run.output_dir) / payload["files"][0]["path"] == Path(run.files[0]["path"])


async def test_the_api_shape_of_a_run_carries_absolute_paths_and_its_timestamp(
    prepared: Prepared,
) -> None:
    run = await _export(prepared)
    payload = export_mod.run_payload(run, for_disk=False)
    _assert_valid_run(payload)
    assert Path(payload["files"][0]["path"]).is_absolute()
    assert "schema_version" not in payload
    assert payload["created_at"].endswith("+00:00")


# --------------------------------------------------------------------------- the record


async def test_the_run_row_records_what_was_produced(prepared: Prepared) -> None:
    run = await _export(prepared)
    assert run.status == "done"
    assert run.scope == "all"
    assert run.method == CONFIG.output.dwg_writer
    assert run.approved_count == 1
    assert run.ignored_count == 0
    assert run.pair_ids == prepared.pair_ids

    with prepared.bundle.session_factory() as session:
        stored = repos.get_run(session, run.id)
        assert stored is not None
        assert stored.status == "done"
        assert [entry["pair_id"] for entry in stored.files] == prepared.pair_ids


async def test_the_compare_set_comes_back_to_compared(prepared: Prepared) -> None:
    """Contract §3: ``compared`` -> ``exporting`` -> ``compared``."""
    await _export(prepared)
    with prepared.bundle.session_factory() as session:
        row = repos.get_compare_set(session, prepared.compare_set_id)
        assert row is not None
        assert row.status == "compared"
    assert _stats(prepared)["export"]["files"] == 1


async def test_the_intermediate_markup_stays_in_the_bundle(prepared: Prepared) -> None:
    """Contract §1: ``.halo/compare/<pair_id>/markup.dxf``."""
    await _export(prepared)
    markup = prepared.bundle.layout.compare_pair_dir(prepared.pair_ids[0]) / "markup.dxf"
    assert markup.is_file()


# --------------------------------------------------------------------------- 원본 불변


async def test_the_source_folders_are_untouched(prepared: Prepared) -> None:
    """CLAUDE.md rule 1. Hashed before and after, file by file."""
    before = _digest(prepared.project_dir / BEFORE_DIR_NAME)
    after = _digest(prepared.project_dir / AFTER_DIR_NAME)
    await _export(prepared)
    assert _digest(prepared.project_dir / BEFORE_DIR_NAME) == before
    assert _digest(prepared.project_dir / AFTER_DIR_NAME) == after


def _digest(folder: Path) -> dict[str, str]:
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


async def test_everything_written_lands_in_the_bundle_or_the_output_folder(
    prepared: Prepared,
) -> None:
    run = await _export(prepared)
    roots = [prepared.bundle.layout.root.resolve(), Path(run.output_dir).resolve()]
    written = [Path(entry["path"]) for entry in run.files]
    written.append(Path(run.output_dir) / export_mod.CHANGES_TSV_NAME)
    written.append(Path(run.output_dir) / export_mod.RUN_JSON_NAME)
    for path in written:
        assert any(root in path.resolve().parents for root in roots), path
