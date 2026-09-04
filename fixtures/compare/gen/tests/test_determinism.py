"""Determinism: running the generator twice must produce byte-identical DXF
and truth.json files. Exercises the *real* process entry point
(``python -m compare_fixtures_gen``) via subprocess -- the brief's
acceptance command -- so the ``PYTHONHASHSEED`` re-exec guard in
``compare_fixtures_gen.cli.run`` is covered too, not just the in-process
``main()`` used by other tests.
"""

from __future__ import annotations

import filecmp
import subprocess
import sys
from pathlib import Path

GEN_ROOT = Path(__file__).resolve().parents[1]


def _run(out_dir: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "compare_fixtures_gen", "--out", str(out_dir)],
        cwd=GEN_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr


def _all_files(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())


def test_two_runs_are_byte_identical(tmp_path: Path) -> None:
    out_a = tmp_path / "a"
    out_b = tmp_path / "b"

    _run(out_a)
    _run(out_b)

    files_a = _all_files(out_a)
    files_b = _all_files(out_b)
    assert files_a == files_b
    assert files_a, "expected at least one generated file"

    _match, mismatch, errors = filecmp.cmpfiles(out_a, out_b, files_a, shallow=False)
    assert mismatch == [], f"non-deterministic bytes: {mismatch}"
    assert errors == []


def test_committed_output_matches_regeneration() -> None:
    """The committed ``fixtures/compare/S*/**`` must equal what the generator
    produces right now -- this is what ``git status --short fixtures/compare``
    checks in CI/the acceptance command, exercised here without relying on git."""
    committed_root = GEN_ROOT.parent  # fixtures/compare/
    scenario_dirs = sorted(
        p.name for p in committed_root.iterdir() if p.is_dir() and p.name != "gen"
    )
    assert scenario_dirs, "no committed scenario directories found"

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        regenerated = Path(tmp)
        _run(regenerated)

        for scenario in scenario_dirs:
            committed_files = _all_files(committed_root / scenario)
            regen_files = _all_files(regenerated / scenario)
            assert committed_files == regen_files, f"{scenario}: file set differs"
            _match, mismatch, errors = filecmp.cmpfiles(
                committed_root / scenario, regenerated / scenario, committed_files, shallow=False
            )
            assert mismatch == [], f"{scenario}: non-deterministic bytes: {mismatch}"
            assert errors == []
