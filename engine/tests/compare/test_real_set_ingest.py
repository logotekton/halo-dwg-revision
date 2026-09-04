"""Real-drawing-set acceptance for ``compare/ingest_set.py`` (brief R1-03).

Opt-in only (``HALO_REAL_SET=1``): the real set (``samples/2026-09-02-실시도서``,
contract §12) is read-only, gitignored, and lives in the *main* checkout, not
this worktree (task instructions) -- ``_MAIN_CHECKOUT`` below walks up from
this worktree's own root (``/Users/ythong/Desktop/대명건설/.worktrees/<ID>``) to
its sibling ``halo-dwg-revision``. Skips gracefully when either the env var
or the folder is absent, so a normal ``pytest`` run (and CI) never needs it.

Uses ``00_표지`` (one small DWG, contract §12 count) rather than a larger
folder (``01_건축``'s 38 files) to keep an opt-in-but-still-automated run
fast, and sets ``before_dir == after_dir`` (Defaults for ambiguity: "전·후
폴더가 같으면 허용한다... 후 세트는 sha 캐시로 즉시 끝난다") to exercise the
sha256 cache against real drawing bytes instead of only the synthetic
fixtures ``test_ingest_set.py`` uses.

ZWCAD is not installed on the macOS development machine this runs on, so
``ingest.converter: auto`` naturally picks ``builtin``, which here means the
acad-ts CLI fallback (no desktop connected) -- the same path
``test_converter_fallback.py`` already exercises against synthetic fixtures.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from halo_engine.api.jobs import get_job_manager
from halo_engine.api.main import create_app
from halo_engine.bundle.create import BundleHandle, create_bundle
from halo_engine.compare import ingest_set
from halo_engine.compare.config import load_compare_config
from halo_engine.config import Settings
from halo_engine.db import repos
from halo_engine.model.drawing import ImportStatus

# engine/tests/compare/test_real_set_ingest.py -> tests -> engine -> worktree root
_WORKTREE_ROOT = Path(__file__).resolve().parents[3]
# The worktree convention (CLAUDE.md, docs/contracts/r1.md §0) is a sibling
# `.worktrees/<ID>` directory next to the main checkout -- so two levels up
# from the worktree root is the shared parent, and `halo-dwg-revision` next
# to it is the main checkout that actually holds `samples/` (gitignored,
# hence absent from every worktree).
_MAIN_CHECKOUT = _WORKTREE_ROOT.parent.parent / "halo-dwg-revision"
_REAL_SET_ROOT = (
    _MAIN_CHECKOUT / "samples" / "2026-09-02-실시도서" / "##실시도서(시공도면 수정)" / "00_표지"
)
ACAD_BRIDGE_BIN = _WORKTREE_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"
RUN_DATE = "2026-09-04"


def _skip_unless_enabled() -> None:
    if os.environ.get("HALO_REAL_SET") != "1":
        pytest.skip("set HALO_REAL_SET=1 to run against the real drawing set")
    if not _REAL_SET_ROOT.is_dir():
        pytest.skip(f"real sample set not present at {_REAL_SET_ROOT}")
    if not ACAD_BRIDGE_BIN.is_file():
        pytest.skip(
            f"{ACAD_BRIDGE_BIN} missing -- run `pnpm install && "
            "pnpm --filter @halo-cad/schema build && pnpm --filter @halo-cad/acad-bridge build`"
        )


async def test_real_00_cover_set_self_pair_ingests_and_caches(tmp_path: Path) -> None:
    _skip_unless_enabled()

    settings = Settings(
        data_dir=tmp_path / "data",
        dev=True,
        token="dev",
        converter_fallback="acad-ts",
        acad_bridge_bin=ACAD_BRIDGE_BIN,
    )
    app = create_app(settings)

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    bundle: BundleHandle = create_bundle(project_dir / ".halo", project_dir.name)
    app.state.bundle = bundle

    config = load_compare_config(bundle)
    ignore_patterns = list(config.ingest.ignore_patterns)

    def _create_side(session: Any, *, role: str) -> Any:
        drawing_set = repos.create_drawing_set(
            session, project_id=bundle.id, label=_REAL_SET_ROOT.name
        )
        drawing_set.role = role
        drawing_set.source_dir = str(_REAL_SET_ROOT)
        session.commit()
        session.refresh(drawing_set)
        for planned in ingest_set.plan_set_files(_REAL_SET_ROOT, ignore_patterns):
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
        before_set = _create_side(session, role="before")
        after_set = _create_side(session, role="after")
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

    started = time.monotonic()
    try:
        await ingest_set.run_compare_set_ingest(
            app, job=job, bundle=bundle, compare_set_id=compare_set_id
        )
        elapsed_s = time.monotonic() - started

        with bundle.session_factory() as session:
            compare_set = repos.get_compare_set(session, compare_set_id)
            assert compare_set is not None
            before_rows = repos.list_files_for_set(session, compare_set.before_set_id)
            after_rows = repos.list_files_for_set(session, compare_set.after_set_id)

            # contract §12: 00_표지 has exactly one sheet's DWG.
            assert len(before_rows) == 1, [r.original_name for r in before_rows]
            assert len(after_rows) == 1, [r.original_name for r in after_rows]

            before_row = before_rows[0]
            after_row = after_rows[0]
            assert before_row.import_status == ImportStatus.DONE.value, before_row.error_message
            assert after_row.import_status == ImportStatus.DONE.value, after_row.error_message
            assert before_row.converter == "builtin"  # no ZWCAD on this machine
            # Same file, same folder for both sides -> identical sha256 ->
            # the after side hits the cache instead of re-running acad-ts.
            assert before_row.sha256 == after_row.sha256
            assert after_row.converter_meta is not None
            assert after_row.converter_meta.get("cache_hit") is True

            assert compare_set.status == "ingested"
            assert compare_set.stats is not None
            print(
                f"\n[R1-03 real-set] 00_표지: 1 file/side, "
                f"before entity_count={before_row.entity_count}, elapsed={elapsed_s:.2f}s, "
                f"stats={compare_set.stats}"
            )
    finally:
        get_job_manager(app).shutdown()
