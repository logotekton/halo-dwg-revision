"""End-to-end tests for `halo-engine serve`, exercising the real sidecar protocol.

Spawns the installed console script as a subprocess (as Electron would),
reads the READY handshake off stdout, hits /health, then shuts it down.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator

import httpx
import pytest

from halo_engine.procutil import pid_alive

READY_TIMEOUT_S = 20.0
SHUTDOWN_TIMEOUT_S = 5.0
PARENT_WATCH_TIMEOUT_S = 15.0  # watcher polls every 5s; leave margin


def _spawn(*extra_args: str, env_overrides: dict[str, str] | None = None) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env.pop("HALO_ENGINE_TOKEN", None)
    env.pop("HALO_ENGINE_PARENT_PID", None)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.Popen(
        ["halo-engine", "serve", "--port", "0", "--token", "t", *extra_args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )


def _read_ready_line(proc: subprocess.Popen[str]) -> dict[str, object]:
    assert proc.stdout is not None
    line = proc.stdout.readline()
    if not line:
        stderr = proc.stderr.read() if proc.stderr else ""
        raise AssertionError(f"engine produced no stdout before exiting; stderr={stderr!r}")
    return json.loads(line)


def _terminate(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=SHUTDOWN_TIMEOUT_S)


@pytest.fixture
def engine_proc() -> Iterator[subprocess.Popen[str]]:
    proc = _spawn()
    try:
        yield proc
    finally:
        _terminate(proc)


def test_ready_line_then_health(engine_proc: subprocess.Popen[str]) -> None:
    ready = _read_ready_line(engine_proc)
    assert ready["event"] == "ready"
    assert isinstance(ready["port"], int) and ready["port"] > 0
    # On Windows `halo-engine` is a .exe launcher that spawns python as a child, so the
    # READY pid (the real server) differs from Popen.pid (the launcher). Electron must
    # therefore kill the process tree on shutdown (docs/contracts/wave-2.md).
    assert pid_alive(ready["pid"])
    if sys.platform != "win32":
        assert ready["pid"] == engine_proc.pid
    assert ready["version"] == "0.0.1"

    base = f"http://127.0.0.1:{ready['port']}"
    resp = httpx.get(f"{base}/api/v1/system/health", timeout=5)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_shutdown_exits_within_timeout(engine_proc: subprocess.Popen[str]) -> None:
    ready = _read_ready_line(engine_proc)
    base = f"http://127.0.0.1:{ready['port']}"

    resp = httpx.post(
        f"{base}/api/v1/system/shutdown", headers={"Authorization": "Bearer t"}, timeout=5
    )
    assert resp.status_code == 200

    exit_code = engine_proc.wait(timeout=SHUTDOWN_TIMEOUT_S)
    assert exit_code == 0


def test_parent_pid_watch_exits_when_parent_dead() -> None:
    # A pid guaranteed not to be alive: spawn a trivial subprocess and reap it.
    dummy = subprocess.Popen([sys.executable, "-c", "pass"])
    dummy.wait(timeout=5)
    dead_pid = dummy.pid

    proc = _spawn(env_overrides={"HALO_ENGINE_PARENT_PID": str(dead_pid)})
    try:
        ready = _read_ready_line(proc)
        assert ready["event"] == "ready"

        deadline = time.monotonic() + PARENT_WATCH_TIMEOUT_S
        exit_code: int | None = None
        while time.monotonic() < deadline:
            exit_code = proc.poll()
            if exit_code is not None:
                break
            time.sleep(0.2)

        assert exit_code is not None, "engine did not exit after its parent pid died"
        assert exit_code != 0
    finally:
        _terminate(proc)
