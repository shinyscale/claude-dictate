"""
Floating recording overlay for Claude Dictate
Shows a small always-on-top window during recording with waveform and controls.
"""

import ctypes
import sys
import tkinter as tk
from typing import Callable, Optional

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


class MiniWaveform(ctk.CTkFrame):
    """Compact waveform visualization for the floating overlay."""

    def __init__(self, master, bar_count: int = 20, **kwargs):
        super().__init__(master, fg_color=THEME["bg_medium"], corner_radius=4, **kwargs)

        self.is_active = False
        self.bars = []
        self.bar_count = bar_count

        # Create canvas
        self.canvas = tk.Canvas(
            self,
            bg=THEME["bg_medium"],
            highlightthickness=0,
            height=40,
            width=200
        )
        self.canvas.pack(fill="both", expand=True, padx=2, pady=2)

        # Create bars after widget is mapped
        self.after(50, self._create_bars)

    def _create_bars(self) -> None:
        """Create waveform bars."""
        self.canvas.delete("all")
        self.bars = []

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        if width < 20:
            width = 200
        if height < 20:
            height = 40

        bar_width = max(3, width / self.bar_count)
        gap = 1

        for i in range(self.bar_count):
            x = i * bar_width + gap
            bar = self.canvas.create_rectangle(
                x, height / 2 - 2,
                x + bar_width - gap * 2, height / 2 + 2,
                fill=THEME["text_muted"],
                outline=""
            )
            self.bars.append(bar)

    def start(self) -> None:
        """Start waveform - show waiting state."""
        self.is_active = True
        if not self.bars:
            self._create_bars()
        self._show_waiting()

    def stop(self) -> None:
        """Stop waveform."""
        self.is_active = False
        self._reset()

    def _show_waiting(self) -> None:
        """Show waiting state."""
        height = self.canvas.winfo_height()
        if height < 20:
            height = 40

        for bar in self.bars:
            coords = self.canvas.coords(bar)
            if not coords or len(coords) < 4:
                continue
            x1, _, x2, _ = coords
            y_center = height / 2
            self.canvas.coords(bar, x1, y_center - 4, x2, y_center + 4)
            self.canvas.itemconfig(bar, fill=THEME["accent_secondary"])

    def _reset(self) -> None:
        """Reset to idle state."""
        height = self.canvas.winfo_height()
        if height < 20:
            height = 40

        for bar in self.bars:
            coords = self.canvas.coords(bar)
            if not coords or len(coords) < 4:
                continue
            x1, _, x2, _ = coords
            y_center = height / 2
            self.canvas.coords(bar, x1, y_center - 2, x2, y_center + 2)
            self.canvas.itemconfig(bar, fill=THEME["text_muted"])

    def update_level(self, level: float) -> None:
        """Update waveform based on audio level."""
        if not self.is_active or not self.bars:
            return

        self.after(0, lambda: self._do_update(level))

    def _do_update(self, level: float) -> None:
        """Update bars based on level."""
        if not self.is_active:
            return

        height = self.canvas.winfo_height()
        if height < 20:
            height = 40

        max_bar_height = height - 8

        for i, bar in enumerate(self.bars):
            coords = self.canvas.coords(bar)
            if not coords or len(coords) < 4:
                continue

            x1, _, x2, _ = coords

            # Create wave effect - bars near center are taller
            center = len(self.bars) / 2
            distance = abs(i - center) / center
            wave_factor = 1.0 - (distance * 0.5)

            # Add some randomness for natural look
            import random
            variance = random.uniform(0.8, 1.2)

            bar_height = max(4, level * max_bar_height * wave_factor * variance)
            y_center = height / 2

            self.canvas.coords(bar, x1, y_center - bar_height / 2, x2, y_center + bar_height / 2)

            # Color based on level
            if level > 0.7:
                color = THEME["error"]
            elif level > 0.3:
                color = THEME["accent"]
            else:
                color = THEME["accent_secondary"]

            self.canvas.itemconfig(bar, fill=color)


class FloatingOverlay(ctk.CTkToplevel):
    """
    Small floating window that appears during recording.
    Shows waveform and provides Copy/Clear buttons after recording.
    """

    def __init__(
        self,
        master,
        on_copy: Optional[Callable] = None,
        on_clear: Optional[Callable] = None,
        **kwargs
    ):
        super().__init__(master, **kwargs)

        self.on_copy = on_copy
        self.on_clear = on_clear
        self._auto_hide_id: Optional[str] = None
        self._transcript: str = ""

        # Configure window
        self.title("")
        self.configure(fg_color=THEME["bg_dark"])

        # Set size and position
        self.geometry("320x90")
        self._center_on_screen()

        # Window properties - always on top, no decorations
        self.overrideredirect(True)  # Remove window decorations
        self.attributes("-topmost", True)  # Always on top
        self.attributes("-alpha", 0.95)  # Slight transparency

        # Create rounded border effect
        self.configure(corner_radius=12)

        # Main container with border
        self.container = ctk.CTkFrame(
            self,
            fg_color=THEME["bg_medium"],
            corner_radius=10,
            border_width=1,
            border_color=THEME["border"]
        )
        self.container.pack(fill="both", expand=True, padx=2, pady=2)

        # Top row: Status and waveform
        self.top_row = ctk.CTkFrame(self.container, fg_color="transparent")
        self.top_row.pack(fill="x", padx=8, pady=(8, 4))

        # Status indicator (red dot when recording)
        self.status_dot = ctk.CTkLabel(
            self.top_row,
            text="●",
            font=("Arial", 16),
            text_color=THEME["text_muted"],
            width=20
        )
        self.status_dot.pack(side="left", padx=(0, 4))

        # Status text
        self.status_label = ctk.CTkLabel(
            self.top_row,
            text="Ready",
            font=FONTS["small"],
            text_color=THEME["text_secondary"]
        )
        self.status_label.pack(side="left")

        # Close button
        self.close_btn = ctk.CTkButton(
            self.top_row,
            text="×",
            width=24,
            height=24,
            font=("Arial", 14),
            fg_color="transparent",
            hover_color=THEME["bg_light"],
            text_color=THEME["text_muted"],
            command=self.hide_overlay
        )
        self.close_btn.pack(side="right")

        # Waveform
        self.waveform = MiniWaveform(self.container, bar_count=24)
        self.waveform.pack(fill="x", padx=8, pady=4)

        # Bottom row: Buttons (hidden initially)
        self.button_row = ctk.CTkFrame(self.container, fg_color="transparent")
        # Don't pack yet - will show after recording

        # Copy button
        self.copy_btn = ctk.CTkButton(
            self.button_row,
            # Plain text, not emoji: U+1F4CB/U+1F5D1 are outside the BMP and
            # Tk on Windows renders them as tofu (or raises on Tcl < 8.6.10).
            text="Copy",
            font=FONTS["small"],
            width=80,
            height=28,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._handle_copy
        )
        self.copy_btn.pack(side="left", padx=(0, 4))

        # Clear button
        self.clear_btn = ctk.CTkButton(
            self.button_row,
            text="Clear",
            font=FONTS["small"],
            width=80,
            height=28,
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            hover_color=THEME["bg_light"],
            text_color=THEME["text_secondary"],
            command=self._handle_clear
        )
        self.clear_btn.pack(side="left")

        # Start hidden
        self.withdraw()

        # Never let the overlay become the foreground window (see module notes)
        self._apply_no_activate()

        # Make window draggable
        self._drag_data = {"x": 0, "y": 0}
        self.container.bind("<Button-1>", self._start_drag)
        self.container.bind("<B1-Motion>", self._do_drag)

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

    def _center_on_screen(self) -> None:
        """Position window at top-center of screen."""
        self.update_idletasks()
        screen_width = self.winfo_screenwidth()
        window_width = 320
        x = (screen_width - window_width) // 2
        y = 50  # Near top of screen
        self.geometry(f"+{x}+{y}")

    def _start_drag(self, event) -> None:
        """Start window drag."""
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y

    def _do_drag(self, event) -> None:
        """Handle window drag."""
        x = self.winfo_x() + (event.x - self._drag_data["x"])
        y = self.winfo_y() + (event.y - self._drag_data["y"])
        self.geometry(f"+{x}+{y}")

    def show_recording(self) -> None:
        """Show overlay in recording state."""
        # Cancel any pending auto-hide
        if self._auto_hide_id:
            self.after_cancel(self._auto_hide_id)
            self._auto_hide_id = None

        # Update UI for recording
        self.status_dot.configure(text_color=THEME["error"])
        self.status_label.configure(text="Recording...")

        # Hide buttons during recording
        self.button_row.pack_forget()

        # Start waveform
        self.waveform.start()

        # Show window. deiconify() alone can hand foreground to the overlay on
        # Windows; _apply_no_activate is re-asserted because a withdraw/
        # deiconify cycle can drop the extended style on some Tk builds.
        self.deiconify()
        self._apply_no_activate()
        self._raise_without_focus()

        print("[Overlay] Showing recording state")

    def show_result(self, transcript: str) -> None:
        """Show overlay with result and buttons."""
        self._transcript = transcript

        # Update UI for result state
        self.status_dot.configure(text_color=THEME["success"])

        if transcript:
            # Show "Copied!" to indicate auto-copy happened
            self.status_label.configure(text="✓ Copied to clipboard!")
        else:
            self.status_label.configure(text="No audio captured")

        # Stop waveform
        self.waveform.stop()

        # Show buttons
        self.button_row.pack(fill="x", padx=8, pady=(0, 8))

        # Auto-hide after 5 seconds (shorter since it's already copied)
        self._auto_hide_id = self.after(5000, self.hide_overlay)

        print(f"[Overlay] Showing result: {transcript[:50] if transcript else 'empty'}...")

    def hide_overlay(self) -> None:
        """Hide the overlay."""
        if self._auto_hide_id:
            self.after_cancel(self._auto_hide_id)
            self._auto_hide_id = None

        self.waveform.stop()
        self.withdraw()
        print("[Overlay] Hidden")

    def update_audio_level(self, level: float) -> None:
        """Update waveform with audio level."""
        self.waveform.update_level(level)

    def _handle_copy(self) -> None:
        """Handle copy button click."""
        if self.on_copy:
            self.on_copy()
        # Flash success
        self.status_label.configure(text="✓ Copied!")
        self.after(1500, self.hide_overlay)

    def _handle_clear(self) -> None:
        """Handle clear button click."""
        if self.on_clear:
            self.on_clear()
        self.hide_overlay()
