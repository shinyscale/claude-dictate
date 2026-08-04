"""
Floating status pill for Claude Dictate.

A small always-on-top capsule that narrates the whole dictation round trip:
Listening -> Transcribing -> Refining -> Pasted. It has no buttons. In daemon
mode the text is already on the clipboard and already pasted by the time any
button could be clicked, so the pill's only job is to tell the user which of
those four things is happening right now.
"""

import ctypes
import math
import random
import sys
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from .theme import THEME, FONTS

# Win32 constants for keeping the overlay from ever taking keyboard focus.
# The daemon pastes with a synthetic Ctrl+V into whatever window the user was
# already typing in; if this overlay steals foreground on show, that paste
# lands here instead of in their editor.
_GWL_EXSTYLE = -20
_WS_EX_NOACTIVATE = 0x08000000
_WS_EX_TOOLWINDOW = 0x00000080  # also keeps the overlay out of Alt-Tab
_HWND_TOPMOST = -1
_SWP_NOSIZE = 0x0001
_SWP_NOMOVE = 0x0002
_SWP_NOACTIVATE = 0x0010
_SWP_SHOWWINDOW = 0x0040

_IS_WINDOWS = sys.platform == "win32"

# Pill geometry
PILL_WIDTH = 300
PILL_HEIGHT = 44
PILL_RADIUS = PILL_HEIGHT // 2
PILL_BG = THEME["bg_medium"]

# A colour no part of the UI uses. Windows renders every pixel of exactly this
# colour as fully transparent, which is what turns the square Toplevel into an
# actual capsule instead of a rounded rect on a black card.
_CHROMA_KEY = "#010203"

# state key -> (label, colour, waveform mode, auto-hide ms or None)
STATES = {
    "listening":    ("Listening",    THEME["error"],      "live", None),
    "transcribing": ("Transcribing", THEME["warning"],    "scan", None),
    "refining":     ("Refining",     THEME["accent"],     "scan", None),
    "pasted":       ("Pasted",       THEME["success"],    "flat", 1800),
    # Paste withheld because the focused window changed mid-dictation; the
    # text is on the clipboard instead of in the wrong app.
    "held":         ("On clipboard", THEME["warning"],    "flat", 3000),
    "empty":        ("No audio",     THEME["text_muted"], "flat", 2200),
    "error":        ("Failed",       THEME["error"],      "flat", 3000),
}


class MiniWaveform(ctk.CTkFrame):
    """
    Bar strip with three modes.

    live  - heights driven by real microphone level (recording)
    scan  - a travelling bump, for work whose duration we can't measure
            (transcribe, refine). Deliberately distinct from `live` so the
            strip never pretends to be hearing audio when it isn't.
    flat  - a resting hairline
    """

    BAR_MIN = 3
    TICK_MS = 33
    SCAN_SPEED = 0.018   # phase per tick; ~1.8s per sweep
    SCAN_WIDTH = 0.13    # bump half-width as a fraction of the strip

    def __init__(self, master, bar_count: int = 28, height: int = 22, **kwargs):
        super().__init__(master, fg_color="transparent", corner_radius=0, **kwargs)

        self.bar_count = bar_count
        self._height = height
        self._mode = "flat"
        self._color = THEME["text_muted"]
        self._phase = 0.0
        self._anim_id: Optional[str] = None
        self.bars = []

        self.canvas = tk.Canvas(
            self,
            bg=PILL_BG,
            highlightthickness=0,
            bd=0,
            height=height,
            width=170,
        )
        self.canvas.pack(fill="both", expand=True)

        self.after(50, self._create_bars)

    # -- geometry ----------------------------------------------------------

    def _dims(self):
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width < 20:
            width = 170
        if height < 8:
            height = self._height
        return width, height

    def _create_bars(self) -> None:
        self.canvas.delete("all")
        self.bars = []

        width, height = self._dims()
        slot = width / self.bar_count
        bar_w = max(2, slot - 2)
        y = height / 2

        for i in range(self.bar_count):
            x = i * slot + (slot - bar_w) / 2
            self.bars.append(self.canvas.create_rectangle(
                x, y - self.BAR_MIN / 2,
                x + bar_w, y + self.BAR_MIN / 2,
                fill=self._color,
                outline="",
            ))

    def _set_heights(self, heights) -> None:
        """Apply a list of pixel heights, one per bar."""
        if not self.bars:
            return
        _, height = self._dims()
        y = height / 2
        for bar, h in zip(self.bars, heights):
            coords = self.canvas.coords(bar)
            if not coords or len(coords) < 4:
                continue
            x1, _, x2, _ = coords
            half = max(self.BAR_MIN, h) / 2
            self.canvas.coords(bar, x1, y - half, x2, y + half)

    # -- modes -------------------------------------------------------------

    def set_color(self, color: str) -> None:
        self._color = color
        for bar in self.bars:
            self.canvas.itemconfig(bar, fill=color)

    def set_mode(self, mode: str, color: Optional[str] = None) -> None:
        """Switch between 'live', 'scan' and 'flat'."""
        if color:
            self.set_color(color)
        if not self.bars:
            self._create_bars()

        self._mode = mode
        self._stop_anim()

        if mode == "scan":
            self._phase = 0.0
            self._tick_scan()
        elif mode == "flat":
            self._set_heights([self.BAR_MIN] * len(self.bars))
        # 'live' waits for update_level() calls

    def stop(self) -> None:
        self.set_mode("flat", THEME["text_muted"])

    def _stop_anim(self) -> None:
        if self._anim_id:
            try:
                self.after_cancel(self._anim_id)
            except Exception:
                pass
            self._anim_id = None

    def _tick_scan(self) -> None:
        if self._mode != "scan":
            return

        _, height = self._dims()
        peak = height - 4
        n = max(1, len(self.bars) - 1)

        heights = []
        for i in range(len(self.bars)):
            p = i / n
            # wrap the distance so the bump re-enters from the left cleanly
            d = abs(p - self._phase)
            d = min(d, 1.0 - d)
            amp = math.exp(-((d / self.SCAN_WIDTH) ** 2))
            heights.append(self.BAR_MIN + amp * (peak - self.BAR_MIN))

        self._set_heights(heights)

        self._phase = (self._phase + self.SCAN_SPEED) % 1.0
        self._anim_id = self.after(self.TICK_MS, self._tick_scan)

    # -- live level --------------------------------------------------------

    def update_level(self, level: float) -> None:
        if self._mode != "live" or not self.bars:
            return
        self.after(0, lambda: self._do_update(level))

    def _do_update(self, level: float) -> None:
        if self._mode != "live" or not self.bars:
            return

        _, height = self._dims()
        peak = height - 4
        center = len(self.bars) / 2

        heights = []
        for i in range(len(self.bars)):
            # taller toward the middle, plus a little jitter so it breathes
            distance = abs(i - center) / center
            wave = 1.0 - (distance * 0.5)
            heights.append(level * peak * wave * random.uniform(0.8, 1.2))

        self._set_heights(heights)


class FloatingOverlay(ctk.CTkToplevel):
    """
    Capsule that reports where the dictation currently is.

    Drive it with show_recording() / show_transcribing() / show_refining() and
    finish with show_pasted(), show_empty() or show_error(). show_result() is
    kept for the windowed app, which has no separate refine step.
    """

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        self._auto_hide_id: Optional[str] = None
        self._transcript: str = ""
        self._state: str = "flat"

        self.title("")
        self.geometry(f"{PILL_WIDTH}x{PILL_HEIGHT}")
        self._position_default()

        self.overrideredirect(True)
        self.attributes("-topmost", True)

        # Punch the corners out so this reads as a capsule, not a card.
        self.configure(fg_color=_CHROMA_KEY)
        try:
            self.attributes("-transparentcolor", _CHROMA_KEY)
        except tk.TclError:
            # Not supported off Windows; fall back to a dark surround.
            self.configure(fg_color=THEME["bg_dark"])

        self.container = ctk.CTkFrame(
            self,
            fg_color=PILL_BG,
            corner_radius=PILL_RADIUS,
            border_width=1,
            border_color=THEME["border"],
        )
        self.container.pack(fill="both", expand=True)

        self.row = ctk.CTkFrame(self.container, fg_color="transparent")
        self.row.pack(fill="both", expand=True, padx=14, pady=6)

        # State dot
        self.status_dot = ctk.CTkLabel(
            self.row,
            text="●",
            font=("Arial", 13),
            text_color=THEME["text_muted"],
            width=12,
        )
        self.status_dot.pack(side="left", padx=(0, 8))

        # State word. Fixed width so the waveform doesn't shift when the label
        # changes from "Listening" to "Transcribing".
        self.status_label = ctk.CTkLabel(
            self.row,
            text="Ready",
            font=FONTS["pill"],
            text_color=THEME["text_secondary"],
            width=84,
            anchor="w",
        )
        self.status_label.pack(side="left")

        self.waveform = MiniWaveform(self.row, bar_count=28, height=22)
        self.waveform.pack(side="left", fill="both", expand=True, padx=(6, 0))

        self.withdraw()

        # Never let the overlay become the foreground window (see module notes)
        self._apply_no_activate()

        # Draggable by its body -- there are no controls to conflict with.
        self._drag_data = {"x": 0, "y": 0}
        for widget in (self.container, self.row, self.status_label,
                       self.status_dot, self.waveform, self.waveform.canvas):
            widget.bind("<Button-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._do_drag)

    # -- focus containment (Windows) ---------------------------------------

    def _hwnd(self) -> int:
        """Native handle for this Toplevel, or 0 if it isn't realized yet."""
        try:
            wid = self.winfo_id()
        except tk.TclError:
            return 0
        # An overrideredirect Toplevel is its own top-level HWND, but a
        # decorated one is a child of a Tk-owned frame; prefer the parent
        # when there is one so the style lands on the real window.
        parent = ctypes.windll.user32.GetParent(wid)
        return parent or wid

    def _apply_no_activate(self) -> None:
        """
        Mark the overlay WS_EX_NOACTIVATE so Windows refuses to give it
        keyboard focus, no matter how it is shown or clicked.

        Without this, deiconify()/lift() can pull foreground away from the
        user's editor, and the daemon's Ctrl+V (sent ~50ms later) pastes the
        transcript into the overlay instead of where they were typing.
        """
        if not _IS_WINDOWS:
            return
        try:
            self.update_idletasks()  # ensure the HWND exists
            hwnd = self._hwnd()
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            user32.GetWindowLongW.restype = ctypes.c_long
            style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            user32.SetWindowLongW(
                hwnd, _GWL_EXSTYLE,
                style | _WS_EX_NOACTIVATE | _WS_EX_TOOLWINDOW,
            )
        except Exception as e:  # pragma: no cover - platform specific
            print(f"[Overlay] Could not apply no-activate style: {e}")

    def _raise_without_focus(self) -> None:
        """Bring the overlay to the front without activating it."""
        if _IS_WINDOWS:
            hwnd = self._hwnd()
            if hwnd:
                try:
                    ctypes.windll.user32.SetWindowPos(
                        hwnd, _HWND_TOPMOST, 0, 0, 0, 0,
                        _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE | _SWP_SHOWWINDOW,
                    )
                    return
                except Exception as e:  # pragma: no cover - platform specific
                    print(f"[Overlay] SetWindowPos failed, falling back to lift(): {e}")
        # Non-Windows (or Win32 call failed): lift() may briefly take focus,
        # which is the behaviour we are trying to avoid, but a visible overlay
        # beats an invisible one.
        self.lift()
        self.attributes("-topmost", True)

    def _position_default(self) -> None:
        """Park the pill at top-centre until the user drags it elsewhere."""
        self.update_idletasks()
        x = (self.winfo_screenwidth() - PILL_WIDTH) // 2
        self.geometry(f"+{x}+50")

    def _start_drag(self, event) -> None:
        self._drag_data["x"] = event.x_root - self.winfo_x()
        self._drag_data["y"] = event.y_root - self.winfo_y()

    def _do_drag(self, event) -> None:
        self.geometry(
            f"+{event.x_root - self._drag_data['x']}"
            f"+{event.y_root - self._drag_data['y']}"
        )

    # -- state machine -----------------------------------------------------

    def set_state(self, state: str, label: Optional[str] = None) -> None:
        """
        Move the pill to one of STATES and show it. Terminal states carry
        their own auto-hide delay; working states stay up until the next
        transition, so the pill can never go quiet mid-round-trip.
        """
        text, color, mode, hide_after = STATES.get(state, STATES["error"])
        self._state = state

        self._cancel_auto_hide()

        self.status_dot.configure(text_color=color)
        self.status_label.configure(text=label or text, text_color=THEME["text_primary"])
        self.waveform.set_mode(mode, color)

        # deiconify() alone can hand foreground to the overlay on Windows;
        # _apply_no_activate is re-asserted because a withdraw/deiconify cycle
        # can drop the extended style on some Tk builds.
        self.deiconify()
        self._apply_no_activate()
        self._raise_without_focus()

        if hide_after:
            self._auto_hide_id = self.after(hide_after, self.hide_overlay)

        print(f"[Overlay] {state}")

    def show_recording(self) -> None:
        self.set_state("listening")

    def show_transcribing(self) -> None:
        self.set_state("transcribing")

    def show_refining(self) -> None:
        self.set_state("refining")

    def show_pasted(self, transcript: str = "") -> None:
        self._transcript = transcript
        self.set_state("pasted")

    def show_held(self, transcript: str = "") -> None:
        self._transcript = transcript
        self.set_state("held")

    def show_empty(self) -> None:
        self._transcript = ""
        self.set_state("empty")

    def show_error(self, message: str = "") -> None:
        self.set_state("error", label=(message[:14] if message else None))

    def show_result(self, transcript: str) -> None:
        """
        Back-compat entry point for the windowed app, which transcribes and
        refines as separate user actions and so has no in-between states.
        """
        if transcript:
            self.show_pasted(transcript)
        else:
            self.show_empty()

    def hide_overlay(self) -> None:
        self._cancel_auto_hide()
        self.waveform.stop()
        self.withdraw()

    def _cancel_auto_hide(self) -> None:
        if self._auto_hide_id:
            try:
                self.after_cancel(self._auto_hide_id)
            except Exception:
                pass
            self._auto_hide_id = None

    def update_audio_level(self, level: float) -> None:
        self.waveform.update_level(level)
