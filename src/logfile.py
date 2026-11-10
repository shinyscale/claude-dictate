"""
A log file for the tray daemon.

Started from a shortcut or at sign-in, the daemon has no console: every
print() -- "refine failed", "faster-whisper unavailable", a traceback --
went nowhere. This sends stdout and stderr to a file next to the config,
with a timestamp on each line, while still echoing to a console when one
exists.
"""

import os
import sys
import threading
from datetime import datetime
from pathlib import Path

MAX_BYTES = 1_000_000  # on startup, a bigger log is moved aside to .old


def log_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "ClaudeDictate"
    else:
        base = Path.home() / ".config" / "claude-dictate"
    base.mkdir(parents=True, exist_ok=True)
    return base / "dictate.log"


class _Tee:
    """File-like object: timestamps whole lines into the log, passes the
    original text through to the real stream if there is one."""

    def __init__(self, logfile, passthrough):
        self._log = logfile
        self._out = passthrough
        self._buf = ""
        self._lock = threading.Lock()

    def write(self, text):
        if not isinstance(text, str):
            text = str(text)
        if self._out is not None:
            try:
                self._out.write(text)
            except Exception:
                pass
        with self._lock:
            self._buf += text
            while "\n" in self._buf:
                line, self._buf = self._buf.split("\n", 1)
                stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                try:
                    self._log.write(f"{stamp} {line}\n")
                    self._log.flush()
                except Exception:
                    pass
        return len(text)

    def flush(self):
        if self._out is not None:
            try:
                self._out.flush()
            except Exception:
                pass

    def isatty(self):
        return False


def start_logging() -> Path:
    """Route stdout/stderr through the log file. Safe to call once at
    daemon startup; never raises (logging must not stop dictation)."""
    path = log_path()
    try:
        if path.exists() and path.stat().st_size > MAX_BYTES:
            old = path.with_suffix(".log.old")
            if old.exists():
                old.unlink()
            path.rename(old)
        f = open(path, "a", encoding="utf-8", errors="replace")
        # pythonw.exe has no console: sys.stdout / sys.stderr are None there.
        sys.stdout = _Tee(f, sys.stdout)
        sys.stderr = _Tee(f, sys.stderr)
        print(f"[Log] Claude Dictate starting (pid {os.getpid()})")
    except Exception:
        pass
    return path


def open_log() -> None:
    """Show the log in the default text editor."""
    path = log_path()
    try:
        if not path.exists():
            path.write_text("", encoding="utf-8")
        if os.name == "nt":
            os.startfile(str(path))  # noqa: only exists on Windows
        else:
            import subprocess
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.Popen([opener, str(path)])
    except Exception as e:
        print(f"[Log] Could not open the log: {e}")
