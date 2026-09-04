"""결정론 for the markup drawing: same sheet, same review, same date, same bytes.

Contract §8 names ``markup.dxf`` alongside ``compare.dxf``, and the reason is
the same one ``test_determinism.py`` gives: a re-export after fixing one sheet's
review must differ from the previous export *only* where the drawing actually
differs. It is also how the 이력 (week 2) will be able to tell "이 도면은 그대로"
from "다시 뽑았다".

The markup writer starts from a file rather than from a fresh document, so the
hazards are the ones ``compare_dxf.serialize`` already handles -- the two GUIDs,
the four time stamps, the ezdxf marker and the CLASSES section, all of which are
regenerated during ``write``. The subprocess case is what proves it: the export
job builds every sheet's markup in a ``ProcessPoolExecutor`` worker, a fresh
interpreter with its own ``PYTHONHASHSEED``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from halo_engine.compare.compare_dxf import build_sidecar
from halo_engine.compare.markup import MARKUP_DXF_NAME, write_markup_dxf

from .scenario_helpers import FIXTURES, packaged_compare_config, run_scenario

CONFIG = packaged_compare_config()
RUN_DATE = "2026-09-04"

#: A move, a whole redraw, a two-sheet file and a 1:50 sheet -- the four shapes
#: the export has to reproduce byte for byte.
DETERMINISM_SCENARIOS = ["S02_move_door", "S12_whole_redraw", "S13_multi_sheet", "S17_scale_50"]


def _markup(scenario: str, out: Path, run_date: str = RUN_DATE) -> bytes:
    """Compare one scenario from scratch, approve everything and write the markup."""
    run = run_scenario(scenario)
    sheet = next(
        (item for item in run.sheets.values() if item.clusters), next(iter(run.sheets.values()))
    )
    payload = build_sidecar(
        pair_id="01J8QK00000000000000000MRK",
        pair_key=sheet.after_frame.norm_key,
        run_date=run_date,
        layer=CONFIG.revision_layer(run_date),
        after_frame=sheet.after_frame,
        offset=sheet.diff.offset,
        changes=sheet.diff.changes,
        clusters=sheet.clusters,
        handle_to_cluster={},
        change_handles={},
    )
    clusters = payload["clusters"]
    for cluster in clusters:
        cluster["decision"] = "approved"

    after = sorted((FIXTURES / scenario / run.truth["after_dir"]).glob("*.dxf"))[0]
    out.mkdir(parents=True, exist_ok=True)
    result = write_markup_dxf(
        after_working_dxf=after,
        clusters=clusters,
        frame=sheet.after_frame,
        run_date=run_date,
        layer_name=CONFIG.revision_layer(run_date),
        config=CONFIG,
        out_path=out / MARKUP_DXF_NAME,
        allowed_roots=[out],
    )
    assert result is not None, scenario
    return result.path.read_bytes()


@pytest.mark.parametrize("scenario", DETERMINISM_SCENARIOS)
def test_writing_the_markup_twice_gives_the_same_bytes(scenario: str, tmp_path: Path) -> None:
    assert _markup(scenario, tmp_path / "first") == _markup(scenario, tmp_path / "second")


def test_a_different_run_date_changes_the_layer_the_date_column_and_the_stamps(
    tmp_path: Path,
) -> None:
    """Contract §11: ``run_date`` is an input, and it is the only thing a later
    export of an unchanged sheet may move."""
    monday = _markup("S02_move_door", tmp_path / "monday", "2026-09-04")
    tuesday = _markup("S02_move_door", tmp_path / "tuesday", "2026-09-05")
    assert monday != tuesday
    assert b"REV-20260904" in monday
    assert b"2026-09-04" in monday
    assert b"REV-20260905" in tuesday
    assert b"2026-09-05" in tuesday


def test_the_markup_is_the_same_in_a_fresh_process(tmp_path: Path) -> None:
    """The export builds every sheet's markup in a process-pool worker (contract §6.2).

    A worker is a new interpreter with its own hash seed, so anything that walks
    a ``set`` while writing produces a different -- and still individually valid
    -- file in every worker. Two explicit seeds is the cheapest guard against
    that coming back.
    """
    script = textwrap.dedent(
        """
        import hashlib, sys
        from pathlib import Path
        sys.path.insert(0, sys.argv[1])
        from markup_shim import markup
        print(hashlib.sha256(markup(sys.argv[2], Path(sys.argv[3]))).hexdigest())
        """
    )
    shim = tmp_path / "markup_shim.py"
    shim.write_text(
        "from tests.compare.test_markup_determinism import _markup as markup\n", encoding="utf-8"
    )
    runner = tmp_path / "run.py"
    runner.write_text(script, encoding="utf-8")

    engine_root = Path(__file__).resolve().parents[2]
    digests = []
    for seed in ("0", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(engine_root)}
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            [sys.executable, str(runner), str(tmp_path), "S02_move_door", str(tmp_path / seed)],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            cwd=str(engine_root),
        )
        assert completed.returncode == 0, completed.stderr
        digests.append(completed.stdout.strip())
    assert digests[0] == digests[1], digests
