"""Determinism: running the generator twice must produce byte-identical DXF
and truth JSON. Exercises the *real* process entry point (``python -m
fixtures_gen``) via subprocess -- exactly the brief's acceptance command --
so the ``PYTHONHASHSEED`` re-exec guard in ``fixtures_gen.cli.run`` is
covered too, not just the in-process ``main()`` used by other tests.

F11/F12 are intentionally excluded here to keep the test fast; their
determinism relies on the exact same save path (:func:`fixtures_gen.common.save`)
as every other fixture, which *is* covered.
"""

from __future__ import annotations

import filecmp
import subprocess
import sys
from pathlib import Path

GEN_ROOT = Path(__file__).resolve().parents[1]
FAST_FIXTURES = "F01,F02,F03,F04,F05,F06,F07,F08,F09,F10"


def _run(out_dir: Path, truth_dir: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fixtures_gen",
            "--out",
            str(out_dir),
            "--truth",
            str(truth_dir),
            "--only",
            FAST_FIXTURES,
        ],
        cwd=GEN_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def test_two_runs_are_byte_identical(tmp_path: Path) -> None:
    out_a, truth_a = tmp_path / "a" / "generated", tmp_path / "a" / "truth"
    out_b, truth_b = tmp_path / "b" / "generated", tmp_path / "b" / "truth"

    _run(out_a, truth_a)
    _run(out_b, truth_b)

    dxf_a = sorted(p.name for p in out_a.glob("*.dxf"))
    dxf_b = sorted(p.name for p in out_b.glob("*.dxf"))
    assert dxf_a == dxf_b
    assert dxf_a, "expected at least one generated DXF file"

    _match, mismatch, errors = filecmp.cmpfiles(out_a, out_b, dxf_a, shallow=False)
    assert mismatch == [], f"non-deterministic DXF bytes: {mismatch}"
    assert errors == []

    json_a = sorted(p.name for p in truth_a.glob("*.json"))
    json_b = sorted(p.name for p in truth_b.glob("*.json"))
    assert json_a == json_b
    _match, mismatch, errors = filecmp.cmpfiles(truth_a, truth_b, json_a, shallow=False)
    assert mismatch == [], f"non-deterministic truth JSON: {mismatch}"
    assert errors == []
