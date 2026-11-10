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
from pynput import mouse
from pynput.keyboard import Controller, Key

from .theme import resolve_fonts
from .tray import SystemTray, is_tray_available, get_tray_error
from .overlay import FloatingOverlay
from ..main import ClaudeDictate, HotkeyListener
from ..config import AppConfig
from ..history import append_entry, mark_session_start
from ..lockfile import write_daemon_lock, clear_daemon_lock
from ..refiner import get_model_status, resolve_llm
from ..seams import strip_refine_command, join_continuation
from ..logfile import start_logging, open_log
from .. import autostart


def _foreground_window() -> tuple:
    """(hwnd, title, class_name) of the window that owns keyboard focus."""
    if os.name != "nt":
        return (None, "", "")
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        return (hwnd, buf.value, cls.value)
    except Exception:
        return (None, "", "")


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
        # PID lock tells a concurrently-open GUI editor not to bind the
        # record hotkey too (double-binding recorded every dictation twice).
        write_daemon_lock()

        # Both models pay their load cost at startup, off the main thread, so
        # the first hotkey press doesn't stall behind a whisper VRAM load or
        # an LM Studio JIT model load.
        threading.Thread(target=self._warm_backends, daemon=True).start()

        self.keyboard = Controller()

        # Continuation tracking: what we last pasted and into which window.
        # Any real keystroke or mouse click clears it -- after either, the
        # caret may have moved and a seam repair would corrupt text.
        self._last_paste: Optional[dict] = None
        self._injecting = False  # our own synthetic keystrokes don't count
        self._mouse_listener = mouse.Listener(on_click=self._on_click)
        self._mouse_listener.start()

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
            if r.backend == "auto" or r.model == "auto":
                # Auto mode rides whatever is already resident, so warming
                # must not load (or evict) anything -- just report.
                resolved = r._resolve()
                if resolved:
                    b, _, m = resolved
                    print(f"[Daemon] LLM auto mode: '{m}' already loaded ({b})")
                else:
                    print("[Daemon] LLM auto mode: nothing loaded yet; refine "
                          "will use whatever model is resident at dictation time")
                return
            status = get_model_status(r.backend, r.base_url, r.model)
            if status["state"] == "loaded":
                print(f"[Daemon] LLM '{r.model}' already resident")
            elif status["state"] == "not-loaded" and self._lms_pin_model(r.model):
                print(f"[Daemon] LLM '{r.model}' pinned resident "
                      f"({time.time() - t0:.1f}s)")
            else:
                # Fallback: a 1-token request JIT-loads the model. Less good
                # than pinning (JIT loads auto-evict on an idle TTL), but it
                # works for Ollama and remote backends.
                if r.backend == "ollama":
                    requests.post(
                        f"{r.base_url}/api/generate",
                        json={"model": r.model, "prompt": "hi",
                              "options": {"num_predict": 1}},
                        timeout=300,
                    )
                else:
                    requests.post(
                        f"{r.base_url}/chat/completions",
                        json={"model": r.model,
                              "messages": [{"role": "user", "content": "hi"}],
                              "max_tokens": 1},
                        timeout=300,
                    )
                print(f"[Daemon] LLM '{r.model}' warm ({time.time() - t0:.1f}s)")
        except Exception as e:
            print(f"[Daemon] LLM warmup skipped: {e}")

    def _lms_pin_model(self, model: str) -> bool:
        """Explicitly load the model via the lms CLI. Unlike a JIT load this
        has no idle TTL, so the model can't be evicted between dictations --
        JIT re-loads have failed mid-dictation ('Operation canceled') where
        explicit loads succeed."""
        lms = Path.home() / ".lmstudio" / "bin" / (
            "lms.exe" if os.name == "nt" else "lms")
        if not lms.exists():
            return False
        try:
            res = subprocess.run(
                [str(lms), "load", model, "-c", "8192", "--gpu", "max", "-y"],
                capture_output=True, text=True, timeout=300,
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            return res.returncode == 0
        except Exception as e:
            print(f"[Daemon] lms load failed: {e}")
            return False

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
            on_other_key=self._invalidate_continuation,
        )
        self.hotkey_listener.start()
        print(f"[Daemon] Hold-to-talk hotkey bound: {hotkey}")

    def _invalidate_continuation(self) -> None:
        if not self._injecting:
            self._last_paste = None

    def _on_click(self, x, y, button, pressed) -> None:
        if pressed and not self._injecting:
            self._last_paste = None

    def _start_recording(self) -> None:
        if self._injecting:
            return  # a synthetic paste combo must never start a recording
        self.app.start_recording()
        self._cue("start")
        if self.system_tray and self.system_tray.is_running:
            self.system_tray.update_icon(recording=True)
        self.root.after(0, self.overlay.show_recording)

    def _stop_recording(self) -> None:
        if self._injecting:
            return
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
        target_hwnd, target_title, _target_cls = target
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
            refine_requested, transcript = strip_refine_command(transcript)
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
                if not refined:
                    # One retry: LM Studio JIT loads occasionally fail with a
                    # transient error and succeed immediately after.
                    print("[Daemon] Refine returned nothing; retrying once...")
                    refined = self.app.refine_text(transcript, style="clean")
                t_refine = time.time() - t0
                # Refine is best-effort: if the backend is unreachable, still
                # paste the raw transcript rather than losing the dictation.
                final_text = refined or transcript
                if not refined:
                    append_entry("refine failed",
                                 "LLM returned no output; raw transcript pasted")

            print(f"[Daemon] Timing: transcribe {t_transcribe:.1f}s, "
                  f"refine {t_refine:.1f}s")

            now_hwnd, now_title, now_cls = _foreground_window()
            if (self.config.get("verify_window", True)
                    and target_hwnd is not None and now_hwnd != target_hwnd):
                # The user moved on while we were working. Pasting now would
                # land in the wrong app; leave it on the clipboard instead.
                self.app.copy_to_clipboard(final_text)
                print(f"[Daemon] Focus moved {target_title!r} -> {now_title!r}; "
                      f"paste withheld, text on clipboard")
                append_entry("held (focus moved)",
                             f"{target_title or '?'} -> {now_title or '?'}")
                self._cue("held")
                self.root.after(0, lambda: self.overlay.show_held(final_text))
                return

            # Same window, nothing typed or clicked since the last paste:
            # this dictation continues the previous one, so repair the seam.
            backspaces, paste_text = 0, final_text
            lp = self._last_paste
            if (self.config.get("continuation_join", True)
                    and lp and target_hwnd is not None
                    and lp["hwnd"] == target_hwnd):
                backspaces, paste_text = join_continuation(
                    lp["text"], final_text,
                    self.config.get("vocabulary_terms", []))
                if backspaces or paste_text != final_text:
                    print(f"[Daemon] Continuation join: {backspaces} backspace(s), "
                          f"seam {lp['text'][-20:]!r} + {paste_text[:20]!r}")

            self.app.copy_to_clipboard(paste_text)
            time.sleep(0.05)  # let the clipboard write land before the paste keystroke

            combo = self._paste_combo_for(now_title, now_cls)
            print(f"[Daemon] Pasting into: {now_title!r} ({combo})")
            append_entry("pasted into", now_title or "(unknown window)")
            self._paste(backspaces, combo)
            # Only the tail matters for the next seam, so remembering just
            # this chunk is enough.
            self._last_paste = {"hwnd": now_hwnd, "text": paste_text}

            self._cue("pasted")
            self.root.after(0, lambda: self.overlay.show_pasted(paste_text))
        except Exception as e:
            print(f"[Daemon] Dictation failed: {e}")
            self._cue("error")
            self.root.after(0, lambda: self.overlay.show_error(str(e)))

    # Names accepted in paste-combo config strings ("ctrl+shift+v",
    # "shift+insert", ...); anything else is sent as a literal character.
    _COMBO_KEYS = {
        "ctrl": Key.ctrl, "shift": Key.shift, "alt": Key.alt,
        "cmd": Key.cmd, "insert": Key.insert,
    }

    def _paste_combo_for(self, title: str, cls: str) -> str:
        """Terminal emulators paste with Ctrl+Shift+V -- to a terminal,
        Ctrl+V is a literal control byte, not paste -- so pick the combo by
        the focused window's class/title."""
        needles = self.config.get("terminal_windows") or []
        haystack = f"{cls} {title}".lower()
        if any(n.lower() in haystack for n in needles):
            return self.config.get("terminal_paste_key", "ctrl+shift+v")
        return self.config.get("paste_key", "ctrl+v")

    def _paste(self, backspaces: int = 0, combo: str = "ctrl+v") -> None:
        # Injected keystrokes echo back through our own pynput listeners;
        # the flag keeps them from clearing the continuation state (and from
        # triggering the record hotkey when the combo overlaps it).
        self._injecting = True
        try:
            for _ in range(backspaces):
                self.keyboard.press(Key.backspace)
                self.keyboard.release(Key.backspace)
            parts = [p for p in combo.lower().replace(" ", "").split("+") if p]
            keys = [self._COMBO_KEYS.get(p, p) for p in parts]
            for k in keys:
                self.keyboard.press(k)
            for k in reversed(keys):
                self.keyboard.release(k)
            time.sleep(0.15)  # let the echoed events drain before re-arming
        finally:
            self._injecting = False

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
            autostart_getter=autostart.is_enabled if autostart.supported() else None,
            on_autostart_toggle=self._toggle_autostart,
            on_open_log=open_log,
        )
        self.system_tray.start()

    def _set_paste_mode(self, mode: str) -> None:
        self.config["paste_mode"] = mode
        try:
            AppConfig.from_dict(self.config).save()
        except Exception as e:
            print(f"[Daemon] Could not persist paste mode: {e}")
        print(f"[Daemon] Paste mode: {mode}")

    def _toggle_autostart(self) -> None:
        now = autostart.set_enabled(not autostart.is_enabled())
        print(f"[Daemon] Start at sign-in: {'on' if now else 'off'}")

    def _open_editor(self) -> None:
        run_py = Path(__file__).resolve().parents[2] / "run.py"
        subprocess.Popen([sys.executable, str(run_py), "--gui"], cwd=str(run_py.parent))

    def _exit(self) -> None:
        clear_daemon_lock()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        if self._mouse_listener:
            self._mouse_listener.stop()
        if self.system_tray:
            self.system_tray.stop()
        self.app.cleanup()
        self.root.after(0, self.root.quit)

    def run(self) -> None:
        print("[Daemon] Claude Dictate running in the tray. Hold the hotkey to dictate.")
        self.root.mainloop()


def run_daemon() -> None:
    """Entry point: run Claude Dictate as a tray daemon with global hold-to-talk."""
    # First, so everything after it -- including a crash while starting --
    # lands in the log instead of a console that may not exist.
    path = start_logging()
    try:
        daemon = DictateDaemon()
        daemon.run()
    except Exception:
        import traceback
        traceback.print_exc()
        print(f"[Daemon] Stopped on an error; see {path}")
        raise
