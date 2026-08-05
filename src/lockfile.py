"""
Cross-process coordination for Claude Dictate.

The tray daemon and the GUI editor are separate processes that both know
how to bind the global record hotkey. If both bind it, every dictation is
recorded and transcribed twice (with subtly different text, since the two
recordings don't stop on the same audio frame). The daemon drops a PID
lock so the GUI can tell a live daemon is already listening.
"""

import ctypes
import os
from pathlib import Path


def _lock_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "ClaudeDictate"
    else:
        base = Path.home() / ".config" / "claude-dictate"
    base.mkdir(parents=True, exist_ok=True)
    return base / "daemon.lock"


def write_daemon_lock() -> None:
    try:
        _lock_path().write_text(str(os.getpid()), encoding="ascii")
    except Exception:
        pass


def clear_daemon_lock() -> None:
    try:
        _lock_path().unlink(missing_ok=True)
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except Exception:
            return False
    # Windows os.kill can't probe; ask the kernel directly.
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION, False, pid
    )
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    return False


def daemon_running() -> bool:
    """True if a live tray daemon (other than this process) holds the lock.
    A stale lock from a crashed daemon reads as not-running."""
    try:
        pid = int(_lock_path().read_text(encoding="ascii").strip())
    except Exception:
        return False
    return pid != os.getpid() and _pid_alive(pid)
