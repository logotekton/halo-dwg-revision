"""pid_alive must work on POSIX and Windows without side effects."""

from __future__ import annotations

import os
import subprocess
import sys

from halo_engine.procutil import pid_alive


def test_own_process_is_alive() -> None:
    assert pid_alive(os.getpid()) is True


def test_exited_child_is_not_alive() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    assert pid_alive(proc.pid) is False


def test_probe_does_not_kill_target() -> None:
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert pid_alive(proc.pid) is True
        # A second probe must not have terminated it (os.kill(pid, 0) would on Windows).
        assert proc.poll() is None
    finally:
        proc.kill()
        proc.wait(timeout=30)


def test_invalid_pid_is_not_alive() -> None:
    assert pid_alive(0) is False
    assert pid_alive(-1) is False
