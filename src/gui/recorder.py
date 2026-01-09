"""
Recording controls for Claude Dictate GUI
Waveform visualization and status indicator widgets.
"""

import random
from typing import Optional

import customtkinter as ctk

from .theme import THEME, FONTS


class WaveformCanvas(ctk.CTkCanvas):
    """Animated waveform visualization for recording."""

    def __init__(self, master, bar_count: int = 40, **kwargs):
        """
        Initialize waveform canvas.

        Args:
            master: Parent widget
            bar_count: Number of bars in the waveform
            **kwargs: Additional canvas arguments
        """
        super().__init__(
            master,
            bg=THEME["bg_medium"],
            highlightthickness=0,
            **kwargs
        )
        self.is_active = False
        self.bars = []
        self.bar_count = bar_count
        self.animation_id: Optional[str] = None
        self._bars_created = False
        # Delay bar creation until widget is mapped
        self.bind("<Map>", self._on_map)

    def _on_map(self, event=None) -> None:
        """Called when widget is mapped/visible."""
        if not self._bars_created:
            self.after(100, self._create_bars)

    def _create_bars(self) -> None:
        """Create waveform bars."""
        # Clear existing bars
        for bar in self.bars:
            self.delete(bar)
        self.bars = []

        width = self.winfo_width()
        height = self.winfo_height()

        if width < 10 or height < 10:
            # Widget not ready yet, try again later
            self.after(100, self._create_bars)
            return

        bar_width = width / self.bar_count

        for i in range(self.bar_count):
            x = i * bar_width + bar_width / 4
            bar = self.create_rectangle(
                x, height / 2 - 2,
                x + bar_width / 2, height / 2 + 2,
                fill=THEME["text_muted"],
                outline=""
            )
            self.bars.append(bar)

        self._bars_created = True

    def start_animation(self) -> None:
        """Start waveform animation."""
        self.is_active = True
        # Force bar creation if not done yet
        if not self._bars_created:
            self._force_create_bars()
        self._animate()

    def _force_create_bars(self) -> None:
        """Force synchronous bar creation with fallback dimensions."""
        # Clear existing bars
        for bar in self.bars:
            self.delete(bar)
        self.bars = []

        # Force geometry calculation
        self.update_idletasks()

        width = self.winfo_width()
        height = self.winfo_height()

        # Use fallback dimensions if widget not ready
        if width < 10:
            width = 280
        if height < 10:
            height = 80

        bar_width = width / self.bar_count

        for i in range(self.bar_count):
            x = i * bar_width + bar_width / 4
            bar = self.create_rectangle(
                x, height / 2 - 2,
                x + bar_width / 2, height / 2 + 2,
                fill=THEME["text_muted"],
                outline=""
            )
            self.bars.append(bar)

        self._bars_created = True

    def stop_animation(self) -> None:
        """Stop waveform animation."""
        self.is_active = False
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None
        self._reset_bars()

    def _animate(self) -> None:
        """Animate waveform bars."""
        if not self.is_active:
            return

        # Skip if bars not yet created
        if not self.bars or not self._bars_created:
            self.animation_id = self.after(50, self._animate)
            return

        height = self.winfo_height() or 60

        for i, bar in enumerate(self.bars):
            # Generate pseudo-random height based on position
            amplitude = random.uniform(0.1, 1.0)
            bar_height = int(amplitude * (height * 0.8))

            coords = self.coords(bar)
            if not coords or len(coords) < 4:
                continue  # Skip invalid bar
            x1, _, x2, _ = coords
            y_center = height / 2

            self.coords(bar, x1, y_center - bar_height / 2, x2, y_center + bar_height / 2)
            self.itemconfig(bar, fill=THEME["accent"])

        # Force canvas refresh
        self.update_idletasks()

        self.animation_id = self.after(50, self._animate)

    def _reset_bars(self) -> None:
        """Reset bars to idle state."""
        # Skip if bars not yet created
        if not self.bars or not self._bars_created:
            return

        height = self.winfo_height() or 60

        for bar in self.bars:
            coords = self.coords(bar)
            if not coords or len(coords) < 4:
                continue  # Skip invalid bar
            x1, _, x2, _ = coords
            y_center = height / 2
            self.coords(bar, x1, y_center - 2, x2, y_center + 2)
            self.itemconfig(bar, fill=THEME["text_muted"])

    def update_level(self, level: float) -> None:
        """
        Update waveform based on audio level.

        Args:
            level: Audio level (0.0-1.0)
        """
        if not self.is_active:
            return

        # Schedule update on main thread (callback may come from audio thread)
        self.after(0, lambda: self._do_update_level(level))

    def _do_update_level(self, level: float) -> None:
        """Actually update the waveform bars (runs on main thread)."""
        if not self.is_active:
            return

        # Skip if bars not yet created
        if not self.bars or not self._bars_created:
            return

        height = self.winfo_height() or 60

        for i, bar in enumerate(self.bars):
            # Add some variation based on position
            variation = random.uniform(0.7, 1.3)
            amplitude = level * variation
            bar_height = int(amplitude * (height * 0.8))
            bar_height = max(4, min(bar_height, height * 0.9))

            coords = self.coords(bar)
            if not coords or len(coords) < 4:
                continue  # Skip invalid bar
            x1, _, x2, _ = coords
            y_center = height / 2

            self.coords(bar, x1, y_center - bar_height / 2, x2, y_center + bar_height / 2)
            self.itemconfig(bar, fill=THEME["accent"])  # Make bars visible with accent color

        # Force canvas refresh
        self.update_idletasks()


class StatusIndicator(ctk.CTkFrame):
    """Status indicator with colored dot."""

    def __init__(self, master, **kwargs):
        """
        Initialize status indicator.

        Args:
            master: Parent widget
            **kwargs: Additional frame arguments
        """
        super().__init__(master, fg_color="transparent", **kwargs)

        self.dot = ctk.CTkLabel(
            self,
            text="●",
            font=("SF Pro Display", 12),
            text_color=THEME["text_muted"]
        )
        self.dot.pack(side="left", padx=(0, 8))

        self.label = ctk.CTkLabel(
            self,
            text="Ready",
            font=FONTS["small"],
            text_color=THEME["text_secondary"]
        )
        self.label.pack(side="left")

    def set_status(self, status: str, color: Optional[str] = None) -> None:
        """
        Update status display.

        Args:
            status: Status text
            color: Optional custom color for the dot
        """
        self.label.configure(text=status)

        if color:
            self.dot.configure(text_color=color)
        elif "recording" in status.lower():
            self.dot.configure(text_color=THEME["error"])
        elif "processing" in status.lower() or "transcribing" in status.lower():
            self.dot.configure(text_color=THEME["warning"])
        elif "refining" in status.lower():
            self.dot.configure(text_color=THEME["accent_secondary"])
        elif "ready" in status.lower():
            self.dot.configure(text_color=THEME["success"])
        elif "error" in status.lower():
            self.dot.configure(text_color=THEME["error"])
        else:
            self.dot.configure(text_color=THEME["text_muted"])


class ProgressBar(ctk.CTkFrame):
    """Progress bar with label."""

    def __init__(self, master, **kwargs):
        """
        Initialize progress bar.

        Args:
            master: Parent widget
            **kwargs: Additional frame arguments
        """
        super().__init__(master, fg_color="transparent", **kwargs)

        self.label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["small"],
            text_color=THEME["text_secondary"]
        )
        self.label.pack(anchor="w")

        self.progress = ctk.CTkProgressBar(
            self,
            fg_color=THEME["bg_dark"],
            progress_color=THEME["accent"],
            height=8
        )
        self.progress.pack(fill="x", pady=(4, 0))
        self.progress.set(0)

    def set_progress(self, value: float, text: str = "") -> None:
        """
        Update progress.

        Args:
            value: Progress value (0.0-1.0)
            text: Optional status text
        """
        self.progress.set(value)
        if text:
            self.label.configure(text=text)

    def reset(self) -> None:
        """Reset progress bar."""
        self.progress.set(0)
        self.label.configure(text="")

    def show(self) -> None:
        """Show the progress bar."""
        self.pack(fill="x", padx=20, pady=(0, 12))

    def hide(self) -> None:
        """Hide the progress bar."""
        self.pack_forget()
