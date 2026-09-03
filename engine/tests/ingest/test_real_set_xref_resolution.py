"""W3-06 addendum 2 acceptance check: "실세트 XREF 133건 중 XR/ 검색 경로로
해석되는 수를 보고서에(목표 133)".

Cheap by design: this only exercises :func:`resolve_xref_path` (filesystem
``exists()`` checks) against every declared XREF path in the real set, not
a full DWG->DXF conversion of every host (``test_xref_import.py`` in
``tests/api`` covers one host end to end through the real pipeline). Declared
paths are read via ``acad-bridge info --xrefs`` -- the engine itself never
parses a ``.dwg`` directly (CLAUDE.md rule 5), so this is the same
lower-cost second pass ADR-0002's amendment already uses acad-ts for
(styles/XREF metadata), not a new dependency.

Skipped entirely when the (gitignored, main-repo-only) real sample set or
the built acad-bridge CLI are not present -- both are environment
preconditions, not code correctness.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from halo_engine.ingest.xref import DEFAULT_IGNORE_PATTERNS, is_ignored_name, resolve_xref_path

# engine/tests/ingest/test_real_set_xref_resolution.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_MAIN_REPO_ROOT = _REPO_ROOT.parent.parent / "Free CAD for Mac OS"
_REAL_SET_ROOT = _MAIN_REPO_ROOT / "samples" / "2026-09-02-실시도서" / "##실시도서(시공도면 수정)"
_ACAD_BRIDGE_BIN = _REPO_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"


def _declared_xrefs(dwg_path: Path) -> list[dict[str, str]]:
    proc = subprocess.run(
        ["node", str(_ACAD_BRIDGE_BIN), "info", str(dwg_path), "--xrefs"],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    info = json.loads(proc.stdout)
    return list(info.get("xrefs", []))


def test_real_set_xref_paths_resolve_with_xr_as_search_path() -> None:
    if not _REAL_SET_ROOT.is_dir():
        pytest.skip(f"real sample set not present at {_REAL_SET_ROOT}")
    if not _ACAD_BRIDGE_BIN.is_file():
        pytest.skip(
            f"{_ACAD_BRIDGE_BIN} missing -- run `pnpm --filter @halo-cad/acad-bridge build`"
        )

    xr_dir = _REAL_SET_ROOT / "XR"
    assert xr_dir.is_dir()

    dwg_paths = sorted(
        p
        for p in _REAL_SET_ROOT.rglob("*")
        if p.is_file()
        and p.suffix.lower() == ".dwg"
        and not is_ignored_name(p.name, DEFAULT_IGNORE_PATTERNS)
    )
    assert dwg_paths, f"no .dwg files found under {_REAL_SET_ROOT}"

    total = 0
    resolved_count = 0
    unresolved: list[tuple[str, str]] = []
    for dwg_path in dwg_paths:
        for xref in _declared_xrefs(dwg_path):
            total += 1
            resolved = resolve_xref_path(
                xref["path"],
                host_dir=dwg_path.parent,
                search_paths=[xr_dir],
                ignore_patterns=DEFAULT_IGNORE_PATTERNS,
            )
            if resolved is not None:
                resolved_count += 1
            else:
                unresolved.append((dwg_path.name, xref["path"]))

    print(  # noqa: T201 - this is the report-facing measurement, not debug noise
        f"\nreal-set XREF resolution: {resolved_count}/{total} resolved with XR/ as search path",
        file=sys.stderr,
    )
    if unresolved:
        print(f"unresolved: {unresolved}", file=sys.stderr)  # noqa: T201

    assert total > 0
    # Brief addendum 2's target is 133/133 (every declared XREF path
    # resolves once XR/ is a search path). Asserted as "no misses" rather
    # than a pinned count, since the exact figure moves with the sample set
    # on disk -- the printed line above is what the report cites verbatim.
    assert resolved_count == total, (
        f"{total - resolved_count} XREF path(s) did not resolve: {unresolved}"
    )
