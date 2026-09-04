"""결정론: the same inputs and the same ``run_date`` must give the same bytes.

Contract §8 and §11. This is not a stylistic preference -- it is what lets a
site engineer diff this week's markup against last week's and see only what
actually changed, and it is the only way to tell "the drawing was revised" from
"the tool felt like laying the file out differently today".

Three things had to be handled to get here, and each has a test below:

* ``ezdxf``'s ``Importer`` collects the tables it needs in ``set``s, so the
  LAYER table came out in ``PYTHONHASHSEED`` order. Fixed by importing every
  table whole, in source order, before any entity.
* ``ezdxf`` regenerates ``$FINGERPRINTGUID`` and ``$VERSIONGUID`` while writing.
* ``ezdxf`` stamps the wall clock into two ``DICTIONARYVAR`` objects.

The subprocess test is the one that would have caught the first: inside one
process the hash seed is fixed, and the bug only showed when the comparison ran
in a fresh worker of the job runner's process pool.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import ezdxf
import pytest

from halo_engine.compare.cluster import build_clusters
from halo_engine.compare.compare_dxf import (
    build_sidecar,
    dumps_sidecar,
    write_compare_dxf,
)
from halo_engine.compare.config import scale_factor
from halo_engine.compare.diff import diff_pair

from .scenario_helpers import FIXTURES, packaged_compare_config, run_scenario

CONFIG = packaged_compare_config()
RUN_DATE = "2026-09-04"

#: The brief's list: a move, a whole redraw and a two-sheet file.
DETERMINISM_SCENARIOS = ["S02_move_door", "S12_whole_redraw", "S13_multi_sheet"]


def _artefacts(scenario: str, out: Path, run_date: str = RUN_DATE) -> tuple[bytes, bytes]:
    """Compare one scenario's first sheet from scratch and return both files' bytes."""
    run = run_scenario(scenario)
    sheet = next(iter(run.sheets.values()))
    before = sorted((FIXTURES / scenario / run.truth["before_dir"]).glob("*.dxf"))[0]
    after = sorted((FIXTURES / scenario / run.truth["after_dir"]).glob("*.dxf"))[0]

    result = diff_pair(
        ezdxf.readfile(str(before)),
        ezdxf.readfile(str(after)),
        sheet.before_frame,
        sheet.after_frame,
        CONFIG,
    )
    factor = scale_factor(sheet.after_frame.scale_denominator)
    clusters = build_clusters(result.changes, sheet.after_frame, CONFIG, factor)

    out.mkdir(parents=True, exist_ok=True)
    dxf = write_compare_dxf(
        before_doc=ezdxf.readfile(str(before)),
        after_doc=ezdxf.readfile(str(after)),
        before_frame=sheet.before_frame,
        after_frame=sheet.after_frame,
        changes=result.changes,
        clusters=clusters,
        config=CONFIG,
        run_date=run_date,
        offset=result.offset,
        out_path=out / "compare.dxf",
        allowed_roots=[out],
    )
    payload = build_sidecar(
        pair_id="01J8QK00000000000000000PAI",
        pair_key=sheet.after_frame.norm_key,
        run_date=run_date,
        layer=CONFIG.revision_layer(run_date),
        after_frame=sheet.after_frame,
        offset=result.offset,
        changes=result.changes,
        clusters=clusters,
        handle_to_cluster=dxf.handle_to_cluster,
        change_handles=dxf.change_handles,
    )
    return dxf.path.read_bytes(), dumps_sidecar(payload)


@pytest.mark.parametrize("scenario", DETERMINISM_SCENARIOS)
def test_comparing_twice_gives_byte_identical_files(scenario: str, tmp_path: Path) -> None:
    first_dxf, first_json = _artefacts(scenario, tmp_path / "first")
    second_dxf, second_json = _artefacts(scenario, tmp_path / "second")
    assert first_dxf == second_dxf
    assert first_json == second_json


@pytest.mark.parametrize("scenario", DETERMINISM_SCENARIOS)
def test_a_different_run_date_changes_only_the_layer_and_the_stamps(
    scenario: str, tmp_path: Path
) -> None:
    """Contract §8: ``run_date`` names the revision layer and dates the header.

    Everything else -- the geometry, the cloud marks, the numbering, the change
    list -- is a property of the two drawings and must not move because the
    export happens on a different day.
    """
    monday_dxf, monday_json = _artefacts(scenario, tmp_path / "monday", "2026-09-04")
    tuesday_dxf, tuesday_json = _artefacts(scenario, tmp_path / "tuesday", "2026-09-05")

    changed = _differing_lines(monday_dxf, tuesday_dxf)
    assert changed, "a different run date must at least rename the revision layer"
    assert all(
        "REV-2026090" in line or _is_header_stamp(line) for line in changed
    ), changed

    monday = json.loads(monday_json)
    tuesday = json.loads(tuesday_json)
    assert monday["layer"] == "REV-20260904"
    assert tuesday["layer"] == "REV-20260905"
    for payload in (monday, tuesday):
        payload.pop("layer")
        payload.pop("run_date")
    assert monday == tuesday


def _differing_lines(left: bytes, right: bytes) -> list[str]:
    left_lines = left.decode("utf-8").split("\n")
    right_lines = right.decode("utf-8").split("\n")
    assert len(left_lines) == len(right_lines), "the two files are not the same shape"
    return [
        f"{a} | {b}" for a, b in zip(left_lines, right_lines, strict=True) if a != b
    ]


def _is_header_stamp(line: str) -> bool:
    """A julian-day header value or the pinned ezdxf marker."""
    left, right = (part.strip() for part in line.split("|", 1))
    if left.startswith("1.") and "@" in left:
        return True
    try:
        float(left)
        float(right)
    except ValueError:
        return False
    return True


def test_the_comparison_is_the_same_in_a_fresh_process(tmp_path: Path) -> None:
    """The job runner compares in a ``ProcessPoolExecutor`` worker (contract §6.2).

    A worker is a new interpreter with its own ``PYTHONHASHSEED``, so anything
    that iterates a ``set`` while building the file produces a different -- and
    still individually valid -- drawing in every worker. Running the comparison
    twice under two explicit seeds is the cheapest way to keep that from coming
    back.
    """
    script = textwrap.dedent(
        """
        import hashlib, sys
        from pathlib import Path
        sys.path.insert(0, sys.argv[1])
        from scenario_helpers_shim import artefacts
        dxf, sidecar = artefacts(sys.argv[2], Path(sys.argv[3]))
        print(hashlib.sha256(dxf).hexdigest())
        print(hashlib.sha256(sidecar).hexdigest())
        """
    )
    shim = tmp_path / "scenario_helpers_shim.py"
    shim.write_text(
        "from tests.compare.test_determinism import _artefacts as artefacts\n", encoding="utf-8"
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
