"""
Background tray daemon for Claude Dictate.

No main window. Hold the hotkey anywhere, release, and the refined
transcript is pasted directly into whatever window has focus.
"""

import ctypes
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import requests

import customtkinter as ctk
from pynput.keyboard import Controller, Key

from .theme import resolve_fonts
from .tray import SystemTray, is_tray_available, get_tray_error
from .overlay import FloatingOverlay
from ..main import ClaudeDictate, HotkeyListener
from ..config import AppConfig
from ..history import append_entry, mark_session_start


# Spoken at the very end of a dictation, this asks for the LLM pass on just
# this one dictation, regardless of the configured paste mode. Trailing-only
# and tightly worded so ordinary sentences can't trip it.
_REFINE_CMD = re.compile(r"\brefine\s+(?:this|that|it)\b[\s.!?]*$", re.IGNORECASE)


def _strip_refine_command(text: str) -> tuple:
    """(refine_requested, text with the spoken command removed)."""
    m = _REFINE_CMD.search(text)
    if not m:
        return False, text
    return True, text[:m.start()].rstrip()


def _foreground_window() -> tuple:
    """(hwnd, title) of the window that currently owns keyboard focus."""
    if os.name != "nt":
        return (None, "")
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return (hwnd, buf.value)
    except Exception:
        return (None, "")


class DictateDaemon:
    """Tray-resident daemon: hold hotkey -> record -> transcribe -> refine -> paste."""

    def __init__(self):
        self.config = AppConfig.load().to_flat_dict()

        self.app = ClaudeDictate(self.config)
        self.app.recorder.on_level_update = self._on_audio_level
        self.app.on_status_update = self._on_status

        # A marker per daemon launch is what defines "this session" for the
        # GUI's history panel.
        mark_session_start()

        # Both models pay their load cost at startup, off the main thread, so
        # the first hotkey press doesn't stall behind a whisper VRAM load or
        # an LM Studio JIT model load.
        threading.Thread(target=self._warm_backends, daemon=True).start()

        self.keyboard = Controller()

        # Hidden root hosts the Tk mainloop and the overlay Toplevel; it is
        # never shown. CTk only supports one root per process, so the full
        # editor/settings window is launched as a separate process instead
        # of a second root (see _open_editor).
        self.root = ctk.CTk()
        self.root.withdraw()

        # Needs a live Tk interpreter to enumerate installed families, so it
        # runs after the root exists and before any widget is built.
        resolve_fonts()

        self.overlay = FloatingOverlay(self.root)
        self.hotkey_listener: Optional[HotkeyListener] = None
        self.system_tray: Optional[SystemTray] = None

        self._bind_hotkey()
        self._init_tray()

    # -- warmup --

    def _warm_backends(self) -> None:
        t0 = time.time()
        if self.app.transcriber.preload():
            print(f"[Daemon] Whisper model warm ({time.time() - t0:.1f}s)")

        r = self.app.refiner
        try:
            t0 = time.time()
            if r.backend == "ollama":
                requests.post(
                    f"{r.base_url}/api/generate",
                    json={"model": r.model, "prompt": "hi",
                          "options": {"num_predict": 1}},
                    timeout=180,
                )
            else:
                requests.post(
                    f"{r.base_url}/chat/completions",
                    json={"model": r.model,
                          "messages": [{"role": "user", "content": "hi"}],
                          "max_tokens": 1},
                    timeout=180,
                )
            print(f"[Daemon] LLM '{r.model}' warm ({time.time() - t0:.1f}s)")
        except Exception as e:
            print(f"[Daemon] LLM warmup skipped: {e}")

    # -- audio cues --

    # Short tones so the paste/held/error outcome is knowable without looking
    # at the overlay (e.g. dictating into a full-screen app). Frequencies form
    # tiny musical gestures: rising = success, falling = withheld, low = error.
    _CUES = {
        "start":  ((880, 60),),
        "pasted": ((988, 50), (1319, 70)),
        "held":   ((659, 70), (494, 90)),
        "empty":  ((440, 80),),
        "error":  ((311, 200),),
    }

    def _cue(self, kind: str) -> None:
        if os.name != "nt" or not self.config.get("audio_cues", False):
            return
        tones = self._CUES.get(kind)
        if not tones:
            return

        def play() -> None:
            try:
                import winsound
                for freq, ms in tones:
                    winsound.Beep(freq, ms)
            except Exception:
                pass

        threading.Thread(target=play, daemon=True).start()

    # -- hotkey --

    def _bind_hotkey(self) -> None:
        hotkey = self.config.get("hotkey", "ctrl+shift")
        self.hotkey_listener = HotkeyListener(
            hotkey_combo=hotkey,
            on_activate=self._start_recording,
            on_deactivate=self._stop_recording,
        )
        self.hotkey_listener.start()
        print(f"[Daemon] Hold-to-talk hotkey bound: {hotkey}")

    def _start_recording(self) -> None:
        self.app.start_recording()
        self._cue("start")
        if self.system_tray and self.system_tray.is_running:
            self.system_tray.update_icon(recording=True)
        self.root.after(0, self.overlay.show_recording)

    def _stop_recording(self) -> None:
        if self.system_tray and self.system_tray.is_running:
            self.system_tray.update_icon(recording=False)
        # The window focused at hotkey release is where the user was just
        # dictating -- the only legitimate paste target.
        target = _foreground_window()
        # Transcription/refinement/paste happen off the hotkey-listener thread
        # so a slow LLM response can't block the next hotkey press.
        threading.Thread(
            target=self._process_recording, args=(target,), daemon=True
        ).start()

    def _process_recording(self, target: tuple) -> None:
        # Each leg of the round trip is announced before it starts, so the
        # slowest moment is never the least communicative one. Raw/refined
        # history entries are written inside ClaudeDictate, giving the daemon
        # and the GUI editor one shared session log.
        target_hwnd, target_title = target
        try:
            self.root.after(0, self.overlay.show_transcribing)
            t0 = time.time()
            transcript = self.app.stop_recording()
            t_transcribe = time.time() - t0
            if not transcript:
                self._cue("empty")
                self.root.after(0, self.overlay.show_empty)
                return

            # Saying "refine this" at the end of a dictation requests the LLM
            # pass for just this one, whatever the configured mode.
            refine_requested, transcript = _strip_refine_command(transcript)
            if refine_requested and not transcript:
                # The whole dictation was the command itself.
                self._cue("empty")
                self.root.after(0, self.overlay.show_empty)
                return

            t_refine = 0.0
            final_text = transcript
            if refine_requested or self.config.get("paste_mode", "raw") == "refined":
                self.root.after(0, self.overlay.show_refining)
                t0 = time.time()
                refined = self.app.refine_text(transcript, style="clean")
                t_refine = time.time() - t0
                # Refine is best-effort: if the backend is unreachable, still
                # paste the raw transcript rather than losing the dictation.
                final_text = refined or transcript

            print(f"[Daemon] Timing: transcribe {t_transcribe:.1f}s, "
                  f"refine {t_refine:.1f}s")

            self.app.copy_to_clipboard(final_text)
            time.sleep(0.05)  # let the clipboard write land before the paste keystroke

            now_hwnd, now_title = _foreground_window()
            if (self.config.get("verify_window", True)
                    and target_hwnd is not None and now_hwnd != target_hwnd):
                # The user moved on while we were working. Pasting now would
                # land in the wrong app; leave it on the clipboard instead.
                print(f"[Daemon] Focus moved {target_title!r} -> {now_title!r}; "
                      f"paste withheld, text on clipboard")
                append_entry("held (focus moved)",
                             f"{target_title or '?'} -> {now_title or '?'}")
                self._cue("held")
                self.root.after(0, lambda: self.overlay.show_held(final_text))
                return

            print(f"[Daemon] Pasting into: {now_title!r}")
            append_entry("pasted into", now_title or "(unknown window)")
            self._paste()

            self._cue("pasted")
            self.root.after(0, lambda: self.overlay.show_pasted(final_text))
        except Exception as e:
            print(f"[Daemon] Dictation failed: {e}")
            self._cue("error")
            self.root.after(0, lambda: self.overlay.show_error(str(e)))

    def _paste(self) -> None:
        self.keyboard.press(Key.ctrl)
        self.keyboard.press('v')
        self.keyboard.release('v')
        self.keyboard.release(Key.ctrl)

    def _on_audio_level(self, level: float) -> None:
        self.root.after(0, lambda: self.overlay.update_audio_level(level))

    def _on_status(self, status: str) -> None:
        print(f"[Daemon] {status}")

    # -- tray --

    def _init_tray(self) -> None:
        if not is_tray_available():
            print(f"[Daemon] System tray unavailable: {get_tray_error()}")
            return
        self.system_tray = SystemTray(
            on_show=self._open_editor,
            on_settings=self._open_editor,
            on_exit=self._exit,
            paste_mode_getter=lambda: self.config.get("paste_mode", "raw"),
            on_paste_mode_change=self._set_paste_mode,
        )
        self.system_tray.start()

    def _set_paste_mode(self, mode: str) -> None:
        self.config["paste_mode"] = mode
        try:
            AppConfig.from_dict(self.config).save()
        except Exception as e:
            print(f"[Daemon] Could not persist paste mode: {e}")
        print(f"[Daemon] Paste mode: {mode}")

    def _open_editor(self) -> None:
        run_py = Path(__file__).resolve().parents[2] / "run.py"
        subprocess.Popen([sys.executable, str(run_py), "--gui"], cwd=str(run_py.parent))

    def _exit(self) -> None:
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        if self.system_tray:
            self.system_tray.stop()
        self.app.cleanup()
        self.root.after(0, self.root.quit)

    def run(self) -> None:
        print("[Daemon] Claude Dictate running in the tray. Hold the hotkey to dictate.")
        self.root.mainloop()


def run_daemon() -> None:
    """Entry point: run Claude Dictate as a tray daemon with global hold-to-talk."""
    daemon = DictateDaemon()
    daemon.run()
