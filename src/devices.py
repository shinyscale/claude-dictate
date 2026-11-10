"""
Microphone lookup by name.

PortAudio hands out device *indexes*, and Windows renumbers them whenever a
device is plugged in, unplugged, or a driver updates -- so a saved index can
silently point at a different input next week. The saved *name* is stable.

Pure functions only (no pyaudio import), so they are testable anywhere.
"""

from typing import List, Optional


def _norm(name: str) -> str:
    return " ".join((name or "").lower().split())


def match_device(devices: List[dict], name: Optional[str]) -> Optional[int]:
    """Index of the input device called `name`, or None if it isn't there.

    `devices` is AudioRecorder.get_input_devices() output: dicts with
    'index' and 'name', in PortAudio order. Windows lists every microphone
    once per audio API (MME, DirectSound, WASAPI, WDM-KS); MME comes first,
    resamples to whatever rate we ask for, and truncates names to 31
    characters. So: exact match first, then prefix match in either direction
    (saved full name vs truncated listing, or the reverse), then substring.
    The lowest index wins each round, which on Windows is the MME entry.
    """
    want = _norm(name)
    if not want:
        return None
    named = [(d["index"], _norm(d.get("name", ""))) for d in devices]
    named = [(i, n) for i, n in named if n]

    for i, n in named:
        if n == want:
            return i
    for i, n in named:
        if n.startswith(want) or want.startswith(n):
            return i
    for i, n in named:
        if want in n:
            return i
    return None
