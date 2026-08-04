"""
Shared dictation history for Claude Dictate.

One append-only markdown file, written by whichever process produced the
text: the tray daemon and the GUI editor both funnel through here (via
ClaudeDictate), so the GUI's history panel can show a unified view of the
session regardless of where a dictation happened.

Entry format (kept identical to what the daemon has always written, so
existing history files parse cleanly):

    ## 2026-08-04 14:20:14 — raw

    the dictated text...
"""

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List

SESSION_MARK = "session start"

_HEADER = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) — (.+)$")


def history_path() -> Path:
    """History lives next to the config, not in the repo or clipboard."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "ClaudeDictate"
    else:
        base = Path.home() / ".config" / "claude-dictate"
    base.mkdir(parents=True, exist_ok=True)
    return base / "history.md"


def append_entry(kind: str, text: str) -> None:
    """Append one entry. Never raises: history is a safety net, not a
    reason to fail the dictation that produced it."""
    try:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(history_path(), "a", encoding="utf-8") as f:
            f.write(f"\n## {stamp} — {kind}\n\n{text}\n")
    except Exception as e:
        print(f"[History] write failed: {e}")


def mark_session_start() -> None:
    """Daemon startup writes this; the GUI panel shows entries after the
    most recent marker as 'the current session'."""
    append_entry(SESSION_MARK, "")


def read_entries() -> List[Dict[str, str]]:
    """All entries, oldest first, as {time, kind, text} dicts."""
    path = history_path()
    if not path.exists():
        return []

    entries: List[Dict[str, str]] = []
    current = None
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                m = _HEADER.match(line.rstrip("\n"))
                if m:
                    if current is not None:
                        current["text"] = current["text"].strip()
                        entries.append(current)
                    current = {"time": m.group(1), "kind": m.group(2), "text": ""}
                elif current is not None:
                    current["text"] += line
        if current is not None:
            current["text"] = current["text"].strip()
            entries.append(current)
    except Exception as e:
        print(f"[History] read failed: {e}")
    return entries


def read_session_entries() -> List[Dict[str, str]]:
    """Entries since the most recent session-start marker. Falls back to
    today's entries when no marker exists (e.g. GUI opened without the
    daemon ever running)."""
    entries = read_entries()
    for i in range(len(entries) - 1, -1, -1):
        if entries[i]["kind"] == SESSION_MARK:
            return [e for e in entries[i + 1:] if e["kind"] != SESSION_MARK]
    today = date.today().isoformat()
    return [
        e for e in entries
        if e["time"].startswith(today) and e["kind"] != SESSION_MARK
    ]
