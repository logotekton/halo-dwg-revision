"""Typer CLI for the halo_engine sidecar (`docs/PLAN.md` §3: sidecar protocol)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import logging.handlers
import os
import socket
import sys
import threading
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from uvicorn.supervisors import ChangeReload

from halo_engine import __version__
from halo_engine.api.main import create_app
from halo_engine.config import Settings
from halo_engine.ingest.dxf_loader import load_dxf
from halo_engine.ingest.stats import compute_layer_stats
from halo_engine.ingest.working_dxf import build_working_dxf

app = typer.Typer(add_completion=False, no_args_is_help=True)

logger = logging.getLogger("halo_engine.cli")

_DEFAULT_DATA_DIR = Path.home() / ".halo-cad" / "engine"
_PARENT_WATCH_INTERVAL_S = 5.0


@app.callback()
def _main() -> None:
    """halo_engine — Halo CAD Python sidecar."""
    # A callback, even a no-op one, keeps Typer in "always require the
    # subcommand name" mode. Without it, a Typer app with a single
    # @app.command() collapses to a bare CLI (`halo-engine --port 0`
    # instead of `halo-engine serve --port 0`), which breaks the sidecar
    # protocol's documented invocation (docs/PLAN.md §3.1).


def _configure_logging(settings: Settings) -> None:
    """Human-readable log lines (not JSON) to stderr, plus a rotating file if --log-dir is set.

    stdout is reserved for the single READY handshake line.
    """
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if settings.dev else logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    if settings.log_dir is not None:
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            settings.log_dir / "halo-engine.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)


def _resolve_token(token_option: str | None, *, dev: bool) -> str:
    """env HALO_ENGINE_TOKEN > --token > ('dev' default, --dev only)."""
    token = os.environ.get("HALO_ENGINE_TOKEN") or token_option
    if token:
        return token
    if dev:
        return "dev"
    raise typer.BadParameter(
        "no token: set HALO_ENGINE_TOKEN, pass --token, or use --dev for the 'dev' default"
    )


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but is owned by someone else — treat as alive.
        return True
    return True


async def _watch_parent_async(parent_pid: int) -> None:
    """Every 5s, check HALO_ENGINE_PARENT_PID; exit immediately if it is gone."""
    while True:
        await asyncio.sleep(_PARENT_WATCH_INTERVAL_S)
        if not _pid_alive(parent_pid):
            logger.warning("parent pid %s is gone, exiting", parent_pid)
            os._exit(1)


def _watch_parent_thread(parent_pid: int) -> None:
    """Same check, for the --reload path where the supervisor blocks the main thread."""
    import time

    while True:
        time.sleep(_PARENT_WATCH_INTERVAL_S)
        if not _pid_alive(parent_pid):
            logger.warning("parent pid %s is gone, exiting", parent_pid)
            os._exit(1)


def _bind(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.listen(2048)
    return sock


def _print_ready(port: int) -> None:
    ready = {"event": "ready", "port": port, "pid": os.getpid(), "version": __version__}
    sys.stdout.write(json.dumps(ready) + "\n")
    sys.stdout.flush()


@app.command()
def stats(
    path: Annotated[Path, typer.Argument(help="DXF file to compute layer statistics for.")],
    out: Annotated[Path, typer.Option("--out", help="Output path for the LayerStatsDocument.")],
) -> None:
    """Compute a LayerStatsDocument for one DXF file (ADR-0002 6, W2-03).

    Prints only the output path to stdout.
    """
    load_result = load_dxf(path)
    file_sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
    doc_stats = compute_layer_stats(load_result.doc, file_sha256=file_sha256)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(doc_stats, sort_keys=True, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    typer.echo(str(out))


@app.command()
def ingest(
    path: Annotated[Path, typer.Argument(help="DXF file to ingest.")],
    out: Annotated[Path, typer.Option("--out", help="Output directory for the working DXF.")],
    search_path: Annotated[
        list[Path] | None,
        typer.Option("--search-path", help="Extra directory to search for XREFs (repeatable)."),
    ] = None,
) -> None:
    """Build the working-DXF canonical form of one DXF file (ADR-0002).

    Writes ``<sha256>.working.dxf`` (R2018 UTF-8, XREFs embedded),
    ``<sha256>.working.json`` (metadata: original sha256, codepage, audit
    error count, handle map / stats paths), ``<sha256>.stats.json``
    (LayerStatsDocument) and ``<sha256>.xref-handles.json`` (bound handle
    map) under ``--out``. Prints only the four output paths to stdout, one
    per line.
    """
    result = build_working_dxf(path, out, search_paths=search_path)
    for output_path in (
        result.working_dxf_path,
        result.working_meta_path,
        result.stats_path,
        result.handle_map_path,
    ):
        typer.echo(str(output_path))


@app.command()
def serve(
    data_dir: Annotated[
        Path, typer.Option("--data-dir", help="Engine data directory (bundles, cache, sqlite).")
    ] = _DEFAULT_DATA_DIR,
    dev: Annotated[
        bool, typer.Option("--dev", help="Dev mode: allows the 'dev' token default.")
    ] = False,
    port: Annotated[
        int, typer.Option("--port", help="Port to bind on 127.0.0.1 (0 = OS-assigned).")
    ] = 0,
    token: Annotated[
        str | None,
        typer.Option("--token", help="Bearer token; HALO_ENGINE_TOKEN env takes precedence."),
    ] = None,
    reload: Annotated[
        bool, typer.Option("--reload", help="Autoreload on source changes (dev workflow only).")
    ] = False,
    log_dir: Annotated[
        Path | None, typer.Option("--log-dir", help="Directory for rotating log files.")
    ] = None,
) -> None:
    """Bind 127.0.0.1:<port>, print the READY handshake line, then serve."""
    resolved_token = _resolve_token(token, dev=dev)
    settings = Settings(data_dir=data_dir, dev=dev, log_dir=log_dir, token=resolved_token)
    _configure_logging(settings)

    # A --reload worker re-imports the app factory in a fresh process, so hand
    # it the resolved settings via env rather than a Python object.
    os.environ["HALO_ENGINE_DATA_DIR"] = str(settings.data_dir)
    os.environ["HALO_ENGINE_DEV"] = "1" if settings.dev else "0"
    os.environ["HALO_ENGINE_TOKEN"] = settings.token or ""
    if settings.log_dir is not None:
        os.environ["HALO_ENGINE_LOG_DIR"] = str(settings.log_dir)

    sock = _bind(port)
    actual_port = sock.getsockname()[1]
    _print_ready(actual_port)
    logger.info(
        "halo_engine %s listening on 127.0.0.1:%s (pid=%s)", __version__, actual_port, os.getpid()
    )

    parent_pid_env = os.environ.get("HALO_ENGINE_PARENT_PID")

    if reload:
        config = uvicorn.Config(
            "halo_engine.api.main:create_app",
            factory=True,
            host="127.0.0.1",
            port=actual_port,
            reload=True,
            log_config=None,
        )
        server = uvicorn.Server(config)
        if parent_pid_env:
            threading.Thread(
                target=_watch_parent_thread, args=(int(parent_pid_env),), daemon=True
            ).start()
        ChangeReload(config, target=server.run, sockets=[sock]).run()
        return

    fastapi_app = create_app(settings)
    config = uvicorn.Config(fastapi_app, host="127.0.0.1", port=actual_port, log_config=None)
    server = uvicorn.Server(config)
    fastapi_app.state.server = server

    async def _serve() -> None:
        watcher: asyncio.Task[None] | None = None
        if parent_pid_env:
            watcher = asyncio.create_task(_watch_parent_async(int(parent_pid_env)))
        try:
            await server.serve(sockets=[sock])
        finally:
            if watcher is not None:
                watcher.cancel()

    asyncio.run(_serve())


if __name__ == "__main__":
    app()
