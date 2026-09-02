"""Cross-platform process helpers.

``os.kill(pid, 0)`` is the classic POSIX liveness probe, but on Windows
``os.kill`` with any signal other than CTRL_C/CTRL_BREAK calls
``TerminateProcess`` — it would kill the parent Electron process instead of
checking it. Use this module instead of ``os.kill(pid, 0)`` everywhere.
"""

from __future__ import annotations

import os
import sys


def pid_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` exists (and has not exited)."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists but owned by someone else.
        return True
    return True


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259
    _ERROR_ACCESS_DENIED = 5

    def _pid_alive_windows(pid: int) -> bool:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            # ERROR_INVALID_PARAMETER means no such process; ACCESS_DENIED means it exists.
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        try:
            exit_code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return int(exit_code.value) == _STILL_ACTIVE
            return True
        finally:
            kernel32.CloseHandle(handle)

else:

    def _pid_alive_windows(pid: int) -> bool:  # pragma: no cover - never called off Windows
        raise RuntimeError("windows-only helper")
