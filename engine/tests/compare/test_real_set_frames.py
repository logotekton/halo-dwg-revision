"""도곽 수 실측: how many sheets ``compare/frames.py`` finds in the real set.

Opt-in (``HALO_REAL_SET=1``) and **assert-free on the counts**. The ledger's
numbers -- 전기 104, 기계 51, 통신 28, 소방기계 45, 소방전기 28, 건축 99
(contract §12, ``docs/spikes/real-dwg-measurement.md`` §0-1, where they were
measured against the printed PDFs page for page) -- are the acceptance
criterion for the **Windows** build, where ZWCAD writes the working DXF. What
this test can produce on macOS is the acad-ts conversion, which the same spike
measured as losing ATTRIBs on 45 of 68 files (§3.2). Failing a run over a
number the converter, not the extractor, is responsible for would be noise, so
this prints a table and leaves the判定 to the user's installer run
(``docs/gates/R1.md``).

Two configurations are measured side by side, because the difference between
them is the whole reason ``frames.yaml`` has a ``block_name_patterns`` key:

* **default** -- title blocks are found by their ATTRIB tags. This is what a
  correctly converted file gives.
* **named block** -- ``block_name_patterns: ["*TITLE BLOCK*"]``, the real set's
  own stamp (spike §1: 375 ``TITLE BLOCK-V`` INSERTs). It finds the sheets even
  when the conversion dropped their attributes.

Run it with a generous timeout; acad-ts opening a 20 MB DWG is minutes, not
seconds::

    cd engine && HALO_REAL_SET=1 uv run pytest tests/compare/test_real_set_frames.py -q -s
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import ezdxf
import pytest
import yaml

from halo_engine.compare.config import DEFAULT_FRAMES_YAML, FramesConfig
from halo_engine.compare.frames import (
    KIND_TITLEBLOCK,
    KIND_UNRECOGNIZED,
    assign_entities,
    extract_frames,
)
from halo_engine.ingest import pipeline

# engine/tests/compare/test_real_set_frames.py -> tests -> engine -> worktree root.
_WORKTREE_ROOT = Path(__file__).resolve().parents[3]
#: `samples/` is gitignored, so a task worktree has no copy: fall back to the
#: main checkout beside `.worktrees/<ID>` (same rule as test_real_set_ingest).
_MAIN_CHECKOUT = _WORKTREE_ROOT.parent.parent / "halo-dwg-revision"
_SUBPATH = Path("samples") / "2026-09-02-실시도서" / "##실시도서(시공도면 수정)"
_REAL_SET_ROOT = next(
    (
        candidate
        for candidate in (_WORKTREE_ROOT / _SUBPATH, _MAIN_CHECKOUT / _SUBPATH)
        if candidate.is_dir()
    ),
    _WORKTREE_ROOT / _SUBPATH,
)
ACAD_BRIDGE_BIN = _WORKTREE_ROOT / "packages" / "acad-bridge" / "bin" / "acad-bridge.mjs"

#: Folder -> the ledger's sheet count (contract §12). 건축 is 99 because two of
#: its 101 frames are the `_recover` duplicate the ingest excludes.
LEDGER_COUNTS: dict[str, int] = {
    "03_전기": 104,
    "02_기계": 51,
    "04_통신": 28,
    "05_소방_기계": 45,
    "06_소방_전기": 28,
    "01_건축": 99,
}

#: Files the ingest never converts (``compare.yaml`` ``ingest.ignore_patterns``).
IGNORE_PATTERNS = ["*_recover.dwg", "*.bak", "*.dwl", "*.dwl2"]

#: Only the disciplines named in ``HALO_REAL_SET_FOLDERS`` (comma separated),
#: or all of them. 01_건축 alone is 38 drawings, so a first run usually names
#: one folder.
_SELECTED = [name for name in (os.environ.get("HALO_REAL_SET_FOLDERS") or "").split(",") if name]


def _frames_config(**titleblock: Any) -> FramesConfig:
    data = yaml.safe_load(DEFAULT_FRAMES_YAML.read_text("utf-8"))
    data["titleblock"].update(titleblock)
    return FramesConfig.model_validate(data)


def _skip_unless_enabled() -> None:
    if os.environ.get("HALO_REAL_SET") != "1":
        pytest.skip("set HALO_REAL_SET=1 to run against the real drawing set")
    if not _REAL_SET_ROOT.is_dir():
        pytest.skip(f"real sample set not present at {_REAL_SET_ROOT}")
    if not ACAD_BRIDGE_BIN.is_file():
        pytest.skip(f"{ACAD_BRIDGE_BIN} missing -- run `pnpm install && pnpm build`")


def _drawings(folder: Path) -> list[Path]:
    import fnmatch

    return sorted(
        path
        for path in folder.iterdir()
        if path.suffix.lower() == ".dwg"
        and not any(fnmatch.fnmatch(path.name.lower(), p) for p in IGNORE_PATTERNS)
    )


def _working_dxf(dwg: Path, cache: Path) -> tuple[str, float]:
    """Convert one DWG and build its working DXF, XR/ on the search path.

    The same two ``ingest/pipeline.py`` steps the ingest job runs, called
    directly: this test is measuring the extractor, and going through the job
    runner would add a database and a process pool to no purpose.
    """
    started = time.monotonic()
    converted = pipeline.run_acad_ts_fallback(
        str(dwg), str(cache / f"{dwg.stem}.converted.dxf"), str(ACAD_BRIDGE_BIN)
    )
    working = pipeline.build_working_dxf_step(
        converted.dxf_path,
        str(cache),
        [str(dwg.parent), str(_REAL_SET_ROOT / "XR")],
        str(ACAD_BRIDGE_BIN),
        IGNORE_PATTERNS,
    )
    return working.working_dxf_path, time.monotonic() - started


def test_real_set_sheet_counts_by_discipline(tmp_path: Path) -> None:
    _skip_unless_enabled()

    folders = [
        _REAL_SET_ROOT / name
        for name in (_SELECTED or LEDGER_COUNTS)
        if (_REAL_SET_ROOT / name).is_dir()
    ]
    default_config = _frames_config()
    named_config = _frames_config(block_name_patterns=["*TITLE BLOCK*"])

    rows: list[tuple[str, int, int, int, int, float]] = []
    skipped: list[tuple[str, str]] = []
    slowest: list[tuple[str, int, float]] = []

    for folder in folders:
        default_frames = 0
        named_frames = 0
        unrecognized = 0
        files = 0
        elapsed_total = 0.0
        cache = tmp_path / folder.name
        cache.mkdir(parents=True, exist_ok=True)

        for dwg in _drawings(folder):
            try:
                working_path, convert_s = _working_dxf(dwg, cache)
                doc = ezdxf.readfile(working_path)
            except Exception as exc:  # noqa: BLE001 - a skipped file is a result
                skipped.append((f"{folder.name}/{dwg.name}", f"{type(exc).__name__}: {exc}"))
                continue

            files += 1
            elapsed_total += convert_s

            default = extract_frames(doc, file_id="F", config=default_config)
            named = extract_frames(doc, file_id="F", config=named_config)
            default_frames += sum(1 for f in default if f.kind == KIND_TITLEBLOCK)
            named_frames += sum(1 for f in named if f.kind == KIND_TITLEBLOCK)
            unrecognized += sum(1 for f in default if f.kind == KIND_UNRECOGNIZED)

            best = named if named[0].kind == KIND_TITLEBLOCK else default
            entity_count = len(doc.modelspace())
            started = time.monotonic()
            assign_entities(doc, best)
            assign_s = time.monotonic() - started
            slowest.append((f"{folder.name}/{dwg.name}", entity_count, assign_s))

        rows.append(
            (
                folder.name,
                files,
                default_frames,
                named_frames,
                unrecognized,
                elapsed_total,
            )
        )

    print("\n[R1-04 real-set] 도곽 수 (mac / acad-ts 변환; 정본은 Windows ZWCAD)")
    print(f"{'공종':<16}{'파일':>5}{'기본':>7}{'블록명':>8}{'미인식':>8}{'장부':>7}{'변환 s':>9}")
    for name, files, default_frames, named_frames, unrecognized, elapsed in rows:
        print(
            f"{name:<16}{files:>5}{default_frames:>7}{named_frames:>8}"
            f"{unrecognized:>8}{LEDGER_COUNTS.get(name, 0):>7}{elapsed:>9.1f}"
        )

    if skipped:
        print(f"\n건너뛴 파일 {len(skipped)}개 (acad-ts 변환/읽기 실패):")
        for name, reason in skipped:
            print(f"  - {name}: {reason[:140]}")

    if slowest:
        print("\nassign_entities 상위 5 (엔티티 수 기준):")
        for name, entity_count, seconds in sorted(slowest, key=lambda r: -r[1])[:5]:
            print(f"  - {name}: {entity_count} entities, {seconds:.2f}s")

    # The only hard assertion: the run produced a table at all. The counts
    # themselves are judged on Windows (module docstring).
    assert rows, "no discipline folder was readable"
