"""
Background tray daemon for Claude Dictate.

No main window. Hold the hotkey anywhere, release, and the refined
transcript is pasted directly into whatever window has focus.
"""

import ctypes
import os
import subprocess
import sys
import threading
import time
from datetime import datetime
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


def _history_path() -> Path:
    """Dictation history lives next to the config, not the clipboard."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", str(Path.home()))) / "ClaudeDictate"
    else:
        base = Path.home() / ".config" / "claude-dictate"
    base.mkdir(parents=True, exist_ok=True)
    return base / "history.md"


def _foreground_window_title() -> str:
    """Title of the window that will receive the synthetic Ctrl+V."""
    if os.name != "nt":
        return ""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception:
        return ""


class DictateDaemon:
    """Tray-resident daemon: hold hotkey -> record -> transcribe -> refine -> paste."""

    def __init__(self):
        self.config = AppConfig.load().to_flat_dict()

        self.app = ClaudeDictate(self.config)
        self.app.recorder.on_level_update = self._on_audio_level
        self.app.on_status_update = self._on_status

        self.history_path = _history_path()

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

    # -- history --

    def _log_history(self, heading: str, text: str) -> None:
        """Append to the dictation history file. Never raises: history is a
        safety net, not a reason to fail the paste."""
        try:
            stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self.history_path, "a", encoding="utf-8") as f:
                f.write(f"\n## {stamp} — {heading}\n\n{text}\n")
        except Exception as e:
            print(f"[Daemon] History write failed: {e}")

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
        if self.system_tray and self.system_tray.is_running:
            self.system_tray.update_icon(recording=True)
        self.root.after(0, self.overlay.show_recording)

    def _stop_recording(self) -> None:
        if self.system_tray and self.system_tray.is_running:
            self.system_tray.update_icon(recording=False)
        # Transcription/refinement/paste happen off the hotkey-listener thread
        # so a slow LLM response can't block the next hotkey press.
        threading.Thread(target=self._process_recording, daemon=True).start()

    def _process_recording(self) -> None:
        # Each leg of the round trip is announced before it starts. The refine
        # leg in particular is a network call to f235 with a 300s ceiling; the
        # overlay used to sit on "Recording..." for the whole of it, so the
        # app's slowest moment was also its least communicative.
        try:
            self.root.after(0, self.overlay.show_transcribing)
            t0 = time.time()
            transcript = self.app.stop_recording()
            t_transcribe = time.time() - t0
            if not transcript:
                self.root.after(0, self.overlay.show_empty)
                return

            # Raw transcript hits disk before the refine leg, so even a crash
            # or dead LLM backend can't lose the dictation.
            self._log_history("raw", transcript)

            self.root.after(0, self.overlay.show_refining)
            t0 = time.time()
            refined = self.app.refine_text(transcript, style="clean")
            t_refine = time.time() - t0
            # Refine is best-effort: if the backend is unreachable, still paste
            # the raw transcript rather than losing the dictation.
            final_text = refined or transcript
            if refined:
                self._log_history("refined", refined)

            print(f"[Daemon] Timing: transcribe {t_transcribe:.1f}s, "
                  f"refine {t_refine:.1f}s")

            self.app.copy_to_clipboard(final_text)
            time.sleep(0.05)  # let the clipboard write land before the paste keystroke
            target = _foreground_window_title()
            print(f"[Daemon] Pasting into: {target!r}")
            self._log_history("pasted into", target or "(unknown window)")
            self._paste()

            self.root.after(0, lambda: self.overlay.show_pasted(final_text))
        except Exception as e:
            print(f"[Daemon] Dictation failed: {e}")
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
        )
        self.system_tray.start()

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
