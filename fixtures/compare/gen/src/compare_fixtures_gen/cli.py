"""``python -m compare_fixtures_gen`` -- deterministic synthetic revision-pair
(before/after DXF + truth.json) generator (R1-07).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from compare_fixtures_gen.scenarios import ALL_SCENARIO_IDS, SCENARIOS


def _reexec_with_fixed_hash_seed() -> None:
    """Guarantee byte-identical output across runs regardless of how this
    process was started.

    Same rationale and fix as ``fixtures/gen/src/fixtures_gen/cli.py``
    (see fixtures/README.md "Decisions" #1): ezdxf orders a handful of
    auxiliary OBJECTS-section entries by iterating an internal set/dict whose
    order depends on Python's per-process string hash seed.
    ``ezdxf.options.write_fixed_meta_data_for_testing`` fixes timestamps and
    GUIDs, but not this. Since the brief's documented invocation does not set
    ``PYTHONHASHSEED``, re-exec the same argv with it pinned to ``0``, once,
    before doing any work.

    Only called from the real process entry point (:func:`run`) -- never
    from :func:`main`, so tests can call ``main(argv)`` directly with a
    custom ``argv`` without triggering a re-exec that would drop it.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    os.execve(sys.executable, [sys.executable, "-m", "compare_fixtures_gen", *sys.argv[1:]], env)


def _resolve_ids(only: str) -> list[str]:
    tokens = [x.strip() for x in only.split(",") if x.strip()]
    short_to_full = {sid.split("_", 1)[0].upper(): sid for sid in ALL_SCENARIO_IDS}
    resolved: list[str] = []
    for tok in tokens:
        tok_upper = tok.upper()
        if tok_upper in SCENARIOS:
            resolved.append(tok_upper)
        elif tok_upper in short_to_full:
            resolved.append(short_to_full[tok_upper])
        else:
            print(f"unknown scenario id: {tok}", file=sys.stderr)
            raise SystemExit(2)
    return resolved


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="compare_fixtures_gen",
        description="Generate Halo CAD synthetic revision-pair fixtures (R1-07).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".."),
        help="output directory for fixtures/compare/<scenario>/{before,after,truth.json} (default: ..)",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="comma-separated scenario ids, e.g. S03 or S03_dim_value or S02,S05",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Pure entry point: build and run the requested scenarios. No process
    re-exec here -- see :func:`run` for the real ``python -m compare_fixtures_gen``
    entry point that guarantees a fixed hash seed first."""
    args = parse_args(argv)
    ids = _resolve_ids(args.only) if args.only else list(ALL_SCENARIO_IDS)
    out_root: Path = args.out

    for sid in ids:
        SCENARIOS[sid].generate(out_root)
        print(f"{sid}: {out_root / sid}")


def run() -> None:
    """Real process entry point (``python -m compare_fixtures_gen`` and the
    ``compare-fixtures-gen`` console script both call this)."""
    _reexec_with_fixed_hash_seed()
    main()


if __name__ == "__main__":
    run()
