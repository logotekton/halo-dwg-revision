"""``python -m fixtures_gen`` -- deterministic synthetic DXF fixture generator."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from fixtures_gen.pipeline import ALL_FIXTURE_IDS, generate


def _reexec_with_fixed_hash_seed() -> None:
    """Guarantee byte-identical output across runs regardless of how this
    process was started.

    ezdxf's DXF writer orders a handful of auxiliary OBJECTS-section entries
    (default PaperSpace ``LAYOUT``/``ACDBPLACEHOLDER`` bookkeeping) by
    iterating an internal ``set``/``dict`` whose order depends on Python's
    per-process string hash seed. ``ezdxf.options.write_fixed_meta_data_for_testing``
    (see :mod:`fixtures_gen.common`) fixes timestamps and GUIDs, but not this.
    Since ``PYTHONHASHSEED`` can only take effect before the interpreter
    starts, and the brief's documented invocation
    (``uv run python -m fixtures_gen ...``) does not set it, this re-execs
    the *same* process argv with ``PYTHONHASHSEED=0`` injected, once, before
    doing any work. Verified empirically -- see fixtures/README.md Decisions.

    Only called from the real process entry points (:func:`run`, i.e. the
    ``python -m fixtures_gen`` / ``fixtures-gen`` console-script paths) --
    never from :func:`main`, so tests can call ``main(argv)`` directly
    without triggering a re-exec that would drop their custom ``argv``.
    """
    if os.environ.get("PYTHONHASHSEED") == "0":
        return
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = "0"
    os.execve(sys.executable, [sys.executable, "-m", "fixtures_gen", *sys.argv[1:]], env)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="fixtures_gen", description="Generate Halo CAD synthetic DXF fixtures (W1-03)."
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("fixtures/generated"),
        help="output directory for DXF files",
    )
    parser.add_argument(
        "--truth", type=Path, default=Path("fixtures/truth"), help="output directory for truth JSON"
    )
    parser.add_argument(
        "--only", type=str, default=None, help="comma-separated fixture ids, e.g. F06 or F06,F09"
    )
    parser.add_argument(
        "--large",
        action="store_true",
        help="also generate F12 (~1,000,000 entities); never commit its output",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Pure entry point: build and run the requested fixtures. No process
    re-exec here -- see :func:`run` for the actual ``python -m fixtures_gen``
    entry point that guarantees a fixed hash seed first.
    """
    args = parse_args(argv)

    if args.only:
        ids = [x.strip().upper() for x in args.only.split(",") if x.strip()]
        for fid in ids:
            if fid not in ALL_FIXTURE_IDS:
                print(f"unknown fixture id: {fid}", file=sys.stderr)
                raise SystemExit(2)
    else:
        ids = list(ALL_FIXTURE_IDS)

    out_dir: Path = args.out
    truth_dir: Path = args.truth

    for fid in ids:
        result_path = generate(fid, out_dir, truth_dir, large=args.large)
        if result_path is None:
            print(f"{fid}: skipped (pass --large to generate)")
        else:
            print(f"{fid}: {result_path}")


def run() -> None:
    """Real process entry point (``python -m fixtures_gen`` and the
    ``fixtures-gen`` console script both call this)."""
    _reexec_with_fixed_hash_seed()
    main()


if __name__ == "__main__":
    run()
