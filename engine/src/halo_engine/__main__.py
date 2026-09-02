"""Frozen-binary entry point for the halo_engine sidecar.

Thin wrapper around `halo_engine.cli:app` (W1-02's Typer CLI) so packaging
(`engine/halo-engine.spec`, W2-08) has a plain script to point PyInstaller's
Analysis at, and so `python -m halo_engine` works the same way. Deliberately
does not add behavior beyond `multiprocessing.freeze_support()`, which
PyInstaller-frozen executables need before any multiprocessing use (harmless,
required on Windows, a no-op on macOS/Linux) -- everything else stays in
cli.py so this file cannot drift out of sync with the dev-mode CLI.
"""

from __future__ import annotations

import multiprocessing

from halo_engine.cli import app


def main() -> None:
    multiprocessing.freeze_support()
    app()


if __name__ == "__main__":
    main()
