"""``compare/ingest_set.py`` -- planning, converter choice, ZWCAD + fallback,
same-converter enforcement, sample crosscheck (brief R1-03).

Real ZWCAD is never touched here: :func:`~halo_engine.compare.zwcad.detect`
is monkeypatched and every COM call goes through ``fake_com.FakeComBackend``
(the same seam ``tests/compare/test_zwcad.py`` uses), with the module-local
``zwcad.sys`` name (not the real, process-wide ``sys`` module -- see
``_FakeWin32Sys`` below) faked to ``platform == "win32"`` so
``ZwcadConverter`` accepts the fake backend at all. The
ZWCAD-failure/builtin-fallback/same-converter test needs a real DWG->DXF
conversion for the *builtin* half of the story (acad-ts, run as a subprocess
against the built CLI) -- skipped via ``acad_bridge_bin`` when that CLI has
not been built (``pnpm install && pnpm --filter @halo-cad/schema build &&
pnpm --filter @halo-cad/acad-bridge build``).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from halo_engine.api.jobs import get_job_manager
from halo_engine.api.main import create_app
from halo_engine.api.ws import ConnectionManager
from halo_engine.bundle.create import BundleHandle, create_bundle
from halo_engine.compare import ingest_set, zwcad
from halo_engine.compare.config import load_compare_config
from halo_engine.config import Settings
from halo_engine.db import repos
from halo_engine.model.drawing import DrawingFormat, ImportStatus

from .fake_com import FakeApp, FakeComBackend, FakeDocument, FakeDocuments

# engine/tests/compare/test_ingest_set.py -> tests -> engine -> repo root
REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_GENERATED = REPO_ROOT / "fixtures" / "generated"
ACAD_BRIDGE_BIN = REPO_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"
RUN_DATE = "2026-09-04"


def _require_generated(name: str) -> Path:
    path = FIXTURES_GENERATED / name
    if not path.is_file():
        pytest.skip(f"{path} missing -- run `cd fixtures/gen && uv run python -m fixtures_gen`")
    return path


def _require_acad_bridge() -> Path:
    if not ACAD_BRIDGE_BIN.is_file():
        pytest.skip(
            f"{ACAD_BRIDGE_BIN} missing -- run `pnpm install && "
            "pnpm --filter @halo-cad/schema build && pnpm --filter @halo-cad/acad-bridge build`"
        )
    return ACAD_BRIDGE_BIN


# ---------------------------------------------------------------------------
# plan_set_files
# ---------------------------------------------------------------------------


def test_plan_set_files_sorted_case_insensitive_and_excludes(tmp_path: Path) -> None:
    (tmp_path / "b.dwg").write_bytes(b"b")
    (tmp_path / "A.DXF").write_bytes(b"a")
    (tmp_path / "X_recover.dwg").write_bytes(b"x")
    (tmp_path / "notes.txt").write_bytes(b"not a drawing")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "C.dwg").write_bytes(b"c")  # one level deep only: never listed

    planned = ingest_set.plan_set_files(tmp_path, ["*_recover.dwg"])

    assert [p.name for p in planned] == ["A.DXF", "b.dwg", "X_recover.dwg"]
    assert [p.excluded for p in planned] == [False, False, True]
    assert planned[2].excluded_reason == "ignore_pattern"
    assert planned[0].excluded_reason is None
    assert planned[0].format is DrawingFormat.DXF
    assert planned[1].format is DrawingFormat.DWG


def test_plan_set_files_ignore_pattern_is_case_insensitive(tmp_path: Path) -> None:
    (tmp_path / "A.BAK").write_bytes(b"")
    (tmp_path / "a.bak.dwg").write_bytes(b"")  # does not match "*.bak"
    planned = ingest_set.plan_set_files(tmp_path, ["*.bak"])
    # ".BAK" alone is not a drawing extension so is not even listed; only the
    # ".dwg" file is a candidate, and it does not match "*.bak" itself.
    assert [p.name for p in planned] == ["a.bak.dwg"]
    assert planned[0].excluded is False


# ---------------------------------------------------------------------------
# norm_key
# ---------------------------------------------------------------------------


def test_norm_key_is_case_and_extension_insensitive() -> None:
    assert ingest_set.norm_key("A-101.DWG") == ingest_set.norm_key("a-101.dxf")
    assert ingest_set.norm_key("A-101.DWG") != ingest_set.norm_key("a-102.dxf")


# ---------------------------------------------------------------------------
# pick_converter
# ---------------------------------------------------------------------------


def _status(*, available: bool) -> zwcad.ZwcadStatus:
    return zwcad.ZwcadStatus(
        available=available,
        installed=available,
        version="2026" if available else None,
        prog_id="ZWCAD.Application" if available else None,
        reason=None if available else "not_registered",
    )


@pytest.mark.parametrize(
    ("option", "available", "expected"),
    [
        ("auto", True, "zwcad-com"),
        ("auto", False, "builtin"),
        ("zwcad", True, "zwcad-com"),
        ("zwcad", False, "zwcad-com"),
        ("builtin", True, "builtin"),
        ("builtin", False, "builtin"),
    ],
)
def test_pick_converter(option: str, available: bool, expected: str) -> None:
    assert ingest_set.pick_converter(_status(available=available), option) == expected


# ---------------------------------------------------------------------------
# enforce_same_converter
# ---------------------------------------------------------------------------


def test_enforce_same_converter_forces_the_zwcad_counterpart_to_builtin() -> None:
    files = [
        ingest_set.ConvertedFileInfo(
            role="before", row_id="b1", norm_key="a-101", converter="zwcad-com"
        ),
        ingest_set.ConvertedFileInfo(
            role="after", row_id="a1", norm_key="a-101", converter="builtin"
        ),
        ingest_set.ConvertedFileInfo(
            role="before", row_id="b2", norm_key="a-102", converter="zwcad-com"
        ),
        ingest_set.ConvertedFileInfo(
            role="after", row_id="a2", norm_key="a-102", converter="zwcad-com"
        ),
        # a DXF input / cache hit (converter=None): never triggers or receives enforcement.
        ingest_set.ConvertedFileInfo(role="before", row_id="b3", norm_key="a-103", converter=None),
        ingest_set.ConvertedFileInfo(
            role="after", row_id="a3", norm_key="a-103", converter="builtin"
        ),
    ]
    assert ingest_set.enforce_same_converter(files) == frozenset({"b1"})


def test_enforce_same_converter_is_empty_when_everyone_agrees() -> None:
    files = [
        ingest_set.ConvertedFileInfo(
            role="before", row_id="b1", norm_key="a-101", converter="zwcad-com"
        ),
        ingest_set.ConvertedFileInfo(
            role="after", row_id="a1", norm_key="a-101", converter="zwcad-com"
        ),
    ]
    assert ingest_set.enforce_same_converter(files) == frozenset()


# ---------------------------------------------------------------------------
# fonts_missing
# ---------------------------------------------------------------------------


def test_compute_fonts_missing_finds_only_names_not_on_disk(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    (project_dir / "fonts").mkdir(parents=True)
    (project_dir / "fonts" / "custom.shx").write_bytes(b"")
    bundle_root = tmp_path / "bundle"
    bundle_root.mkdir()

    missing = ingest_set.compute_fonts_missing(
        ["custom.shx", "CUSTOM.SHX", "not_installed_anywhere.ttf"],
        project_dir=project_dir,
        bundle_root=bundle_root,
    )
    assert missing == ["not_installed_anywhere.ttf"]


# ---------------------------------------------------------------------------
# sample crosscheck: the "not possible on this machine" branches
# ---------------------------------------------------------------------------


async def test_sample_crosscheck_skips_when_zwcad_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(zwcad, "detect", lambda: _status(available=False))
    result = await ingest_set._run_sample_crosscheck(
        loop=None,
        executor=None,
        connections=ConnectionManager(),
        bundle=None,  # type: ignore[arg-type]
        log=None,  # type: ignore[arg-type]
        before_rows=[],
        after_rows=[],
        crosscheck_sample=5,
        converter_fallback=None,
        acad_bridge_bin=None,
    )
    assert result == {"sampled": 0, "mismatched": 0, "skipped": "zwcad_unavailable"}


async def test_sample_crosscheck_skips_when_no_builtin_converter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(zwcad, "detect", lambda: _status(available=True))
    result = await ingest_set._run_sample_crosscheck(
        loop=None,
        executor=None,
        connections=ConnectionManager(),  # no WS clients
        bundle=None,  # type: ignore[arg-type]
        log=None,  # type: ignore[arg-type]
        before_rows=[],
        after_rows=[],
        crosscheck_sample=5,
        converter_fallback=None,  # no acad-ts fallback configured either
        acad_bridge_bin=None,
    )
    assert result == {"sampled": 0, "mismatched": 0, "skipped": "no_builtin_converter"}


async def test_sample_crosscheck_skips_when_sample_size_is_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(zwcad, "detect", lambda: _status(available=True))
    result = await ingest_set._run_sample_crosscheck(
        loop=None,
        executor=None,
        connections=ConnectionManager(),
        bundle=None,  # type: ignore[arg-type]
        log=None,  # type: ignore[arg-type]
        before_rows=[],
        after_rows=[],
        crosscheck_sample=0,
        converter_fallback="acad-ts",
        acad_bridge_bin=Path("/nonexistent/acad-bridge.mjs"),
    )
    assert result == {"sampled": 0, "mismatched": 0, "skipped": "crosscheck_sample_zero"}


async def test_sample_crosscheck_skips_when_nothing_was_zwcad_converted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(zwcad, "detect", lambda: _status(available=True))
    result = await ingest_set._run_sample_crosscheck(
        loop=None,
        executor=None,
        connections=ConnectionManager(),
        bundle=None,  # type: ignore[arg-type]
        log=None,  # type: ignore[arg-type]
        before_rows=[],
        after_rows=[],
        crosscheck_sample=5,
        converter_fallback="acad-ts",
        acad_bridge_bin=Path("/nonexistent/acad-bridge.mjs"),
    )
    assert result == {"sampled": 0, "mismatched": 0, "skipped": "no_zwcad_converted_files"}


# ---------------------------------------------------------------------------
# full orchestration: ZWCAD via FakeComBackend, a runtime failure falling
# back to builtin (acad-ts), and the same-converter rule reconverting the
# already-finished ZWCAD side.
# ---------------------------------------------------------------------------


def _good_zwcad_app(dxf_bytes: bytes) -> FakeApp:
    """A ZWCAD instance whose SaveAs always "succeeds" by writing real DXF bytes."""

    def hook(_document: FakeDocument, path: str, _version: int) -> None:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(dxf_bytes)

    return FakeApp(
        Documents=FakeDocuments(
            open_hook=lambda p, ro: FakeDocument(path=p, read_only=ro, saveas_hook=hook)
        )
    )


def _failing_zwcad_app() -> FakeApp:
    """A ZWCAD instance whose SaveAs always raises (simulated COM failure)."""

    def hook(_document: FakeDocument, _path: str, _version: int) -> None:
        raise RuntimeError("simulated ZWCAD failure")

    return FakeApp(
        Documents=FakeDocuments(
            open_hook=lambda p, ro: FakeDocument(path=p, read_only=ro, saveas_hook=hook)
        )
    )


class _FakeWin32Sys:
    """Proxies everything to the real ``sys`` module except ``.platform``.

    ``ZwcadConverter.__init__`` gates on ``sys.platform == "win32"``; faking
    that globally (``monkeypatch.setattr(sys, "platform", "win32")``) also
    fools ``multiprocessing``'s spawn start method, which the shared
    ``ProcessPoolExecutor`` genuinely depends on to launch worker processes
    on this (real, macOS/Linux) machine -- it breaks with a low-level
    ``TypeError`` deep in ``resource_tracker``. Patching ``zwcad.sys`` (the
    name as looked up *inside that one module*) instead leaves the process's
    real ``sys`` module, and therefore ``multiprocessing``, untouched.
    """

    platform = "win32"

    def __getattr__(self, name: str) -> Any:
        return getattr(sys, name)


def _patch_zwcad_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(zwcad, "sys", _FakeWin32Sys())


def _make_app(tmp_path: Path, **overrides: Any) -> Any:
    settings = Settings(data_dir=tmp_path / "data", dev=True, token="dev", **overrides)
    return create_app(settings)


async def _start_ingest(
    app: Any, before_dir: Path, after_dir: Path, project_dir: Path, *, zwcad_com: Any = None
) -> tuple[BundleHandle, str]:
    bundle = create_bundle(project_dir / ".halo", project_dir.name)
    app.state.bundle = bundle
    config = load_compare_config(bundle)
    ignore_patterns = list(config.ingest.ignore_patterns)

    def _create_side(session: Any, *, role: str, source_dir: Path) -> Any:
        drawing_set = repos.create_drawing_set(session, project_id=bundle.id, label=source_dir.name)
        drawing_set.role = role
        drawing_set.source_dir = str(source_dir)
        session.commit()
        session.refresh(drawing_set)
        for planned in ingest_set.plan_set_files(source_dir, ignore_patterns):
            row = repos.create_drawing_file(
                session,
                drawing_set_id=drawing_set.id,
                original_path=str(planned.path),
                original_name=planned.name,
                sha256="",
                format=planned.format.value,
                import_status=(
                    ImportStatus.EXCLUDED.value if planned.excluded else ImportStatus.PENDING.value
                ),
            )
            if planned.excluded:
                repos.update_drawing_file(session, row.id, excluded_reason=planned.excluded_reason)
        return drawing_set

    with bundle.session_factory() as session:
        before_set = _create_side(session, role="before", source_dir=before_dir)
        after_set = _create_side(session, role="after", source_dir=after_dir)
        compare_set = repos.create_compare_set(
            session,
            project_id=bundle.id,
            before_set_id=before_set.id,
            after_set_id=after_set.id,
            run_date=RUN_DATE,
            status="ingesting",
            options={},
        )
        compare_set_id = compare_set.id

    job_manager = get_job_manager(app)
    job = job_manager.create(compare_set_id=compare_set_id, kind="compare.ingest")
    await ingest_set.run_compare_set_ingest(
        app, job=job, bundle=bundle, compare_set_id=compare_set_id, zwcad_com=zwcad_com
    )
    return bundle, compare_set_id


async def test_zwcad_failure_falls_back_to_builtin_and_forces_same_converter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_zwcad_platform(monkeypatch)
    monkeypatch.setattr(zwcad, "detect", lambda: _status(available=True))

    acad_bridge_bin = _require_acad_bridge()
    good_dxf_bytes = _require_generated("F06.dxf").read_bytes()
    before_original_bytes = _require_generated("F06.dwg").read_bytes()
    after_original_bytes = _require_generated("F10_host.dwg").read_bytes()

    calls = {"n": 0}

    def app_factory(_prog_id: str) -> FakeApp:
        calls["n"] += 1
        # 1st ZwcadConverter() is the before side (succeeds); the 2nd is the
        # after side (fails), per the file-processing order (contract Goal 2:
        # "파일 순서: 전 세트 -> 후 세트").
        return _good_zwcad_app(good_dxf_bytes) if calls["n"] == 1 else _failing_zwcad_app()

    fake_com = FakeComBackend(app_factory=app_factory)

    project_dir = tmp_path / "project"
    before_dir = project_dir / "before"
    after_dir = project_dir / "after"
    before_dir.mkdir(parents=True)
    after_dir.mkdir(parents=True)
    # Same file name on both sides (norm_key match) but different bytes, so
    # the sha256 cache never short-circuits either side's conversion.
    (before_dir / "A-101.dwg").write_bytes(before_original_bytes)
    (after_dir / "A-101.dwg").write_bytes(after_original_bytes)

    app = _make_app(tmp_path, converter_fallback="acad-ts", acad_bridge_bin=acad_bridge_bin)
    try:
        bundle, compare_set_id = await _start_ingest(
            app, before_dir, after_dir, project_dir, zwcad_com=fake_com
        )

        with bundle.session_factory() as session:
            compare_set = repos.get_compare_set(session, compare_set_id)
            assert compare_set is not None
            before_rows = repos.list_files_for_set(session, compare_set.before_set_id)
            after_rows = repos.list_files_for_set(session, compare_set.after_set_id)
            before_row = before_rows[0]
            after_row = after_rows[0]

            # Exactly one hidden ZWCAD instance per side (contract Goal 2).
            assert len(fake_com.create_app_calls) == 2

            # After side: ZWCAD raised, builtin (acad-ts) picked it up.
            assert after_row.import_status == ImportStatus.DONE.value
            assert after_row.converter == "builtin"
            assert after_row.converter_meta is not None
            assert "fallback_reason" in after_row.converter_meta

            # Before side: ZWCAD succeeded first, but the same-converter rule
            # then re-converts it with builtin too, since its after-side
            # counterpart (same norm_key) ended up on builtin.
            assert before_row.import_status == ImportStatus.DONE.value
            assert before_row.converter == "builtin"
            assert before_row.converter_meta is not None
            assert before_row.converter_meta.get("same_converter_forced") is True

            assert compare_set.status == "ingested"
            assert compare_set.stats is not None
            assert compare_set.stats["converter"]["mismatch_files"] == 0
    finally:
        get_job_manager(app).shutdown()


def test_xref_search_paths_add_existing_xr_folders_only(tmp_path):
    """Contract r1.md §2 / brief R1-03 defaults: the set folder itself, then
    `<set>/XR` and `<set>/../XR` when they exist (case-insensitive folder name)."""
    from halo_engine.compare.ingest_set import _xref_search_paths

    project = tmp_path / "proj"
    set_dir = project / "REV2"
    set_dir.mkdir(parents=True)
    assert _xref_search_paths(set_dir) == [str(set_dir)]

    sibling_xr = project / "xr"
    sibling_xr.mkdir()
    assert _xref_search_paths(set_dir) == [str(set_dir), str(sibling_xr)]

    child_xr = set_dir / "XR"
    child_xr.mkdir()
    assert _xref_search_paths(set_dir) == [str(set_dir), str(child_xr), str(sibling_xr)]

    (project / "XR.txt").write_text("not a dir", encoding="utf-8")
    assert str(project / "XR.txt") not in _xref_search_paths(set_dir)
