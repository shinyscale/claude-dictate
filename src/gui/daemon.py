"""
Background tray daemon for Claude Dictate.

No main window. Hold the hotkey anywhere, release, and the refined
transcript is pasted directly into whatever window has focus.
"""

import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import customtkinter as ctk
from pynput.keyboard import Controller, Key

from .tray import SystemTray, is_tray_available, get_tray_error
from .overlay import FloatingOverlay
from ..main import ClaudeDictate, HotkeyListener
from ..config import AppConfig


class DictateDaemon:
    """Tray-resident daemon: hold hotkey -> record -> transcribe -> refine -> paste."""

    def __init__(self):
        self.config = AppConfig.load().to_flat_dict()

        self.app = ClaudeDictate(self.config)
        self.app.recorder.on_level_update = self._on_audio_level
        self.app.on_status_update = self._on_status

        self.keyboard = Controller()

        # Hidden root hosts the Tk mainloop and the overlay Toplevel; it is
        # never shown. CTk only supports one root per process, so the full
        # editor/settings window is launched as a separate process instead
        # of a second root (see _open_editor).
        self.root = ctk.CTk()
        self.root.withdraw()

        self.overlay = FloatingOverlay(self.root)
        self.hotkey_listener: Optional[HotkeyListener] = None
        self.system_tray: Optional[SystemTray] = None

        self._bind_hotkey()
        self._init_tray()

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
        transcript = self.app.stop_recording()
        if not transcript:
            self.root.after(0, lambda: self.overlay.show_result(""))
            return

        refined = self.app.refine_text(transcript, style="clean")
        # Refine is best-effort: if f235 is unreachable, still paste the raw
        # transcript rather than losing the dictation.
        final_text = refined or transcript

        self.app.copy_to_clipboard(final_text)
        time.sleep(0.05)  # let the clipboard write land before the paste keystroke
        self._paste()

        self.root.after(0, lambda: self.overlay.show_result(final_text))

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
