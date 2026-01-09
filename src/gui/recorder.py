"""
Recording controls for Claude Dictate GUI
Waveform visualization and status indicator widgets.
"""

import random
import tkinter as tk
from typing import Optional

import customtkinter as ctk

from .theme import THEME, FONTS


class WaveformCanvas(ctk.CTkFrame):
    """Animated waveform visualization for recording."""

    def __init__(self, master, bar_count: int = 32, **kwargs):
        """
        Initialize waveform canvas.

        Args:
            master: Parent widget
            bar_count: Number of bars in the waveform
            **kwargs: Additional frame arguments
        """
        # Extract height for the canvas, default to 80
        canvas_height = kwargs.pop('height', 80)

        super().__init__(master, fg_color=THEME["bg_medium"], corner_radius=8, **kwargs)

        self.is_active = False
        self.receiving_audio = False  # True when audio level callbacks are being received
        self.bars = []
        self.bar_count = bar_count
        self.animation_id: Optional[str] = None
        self._bars_created = False
        self._canvas_height = canvas_height

        # Create a standard tkinter canvas inside the frame
        self.canvas = tk.Canvas(
            self,
            bg=THEME["bg_medium"],
            highlightthickness=0,
            height=canvas_height
        )
        self.canvas.pack(fill="both", expand=True, padx=4, pady=4)

        # Bind to configure event for resize handling
        self.canvas.bind("<Configure>", self._on_configure)

    def _on_configure(self, event=None) -> None:
        """Handle canvas resize."""
        # Recreate bars when canvas size changes
        self.after(50, self._create_bars)

    def _create_bars(self) -> None:
        """Create waveform bars."""
        # Clear existing bars
        self.canvas.delete("all")
        self.bars = []

        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()

        # Use minimum dimensions if not ready
        if width < 20:
            width = 280
        if height < 20:
            height = self._canvas_height

        bar_width = max(4, width / self.bar_count)
        gap = 2

        for i in range(self.bar_count):
            x = i * bar_width + gap
            # Create thin bar in center (idle state)
            bar = self.canvas.create_rectangle(
                x, height / 2 - 2,
                x + bar_width - gap * 2, height / 2 + 2,
                fill=THEME["text_muted"],
                outline=""
            )
            self.bars.append(bar)

        self._bars_created = True

    def start_animation(self) -> None:
        """Start waveform - waits for real audio, no random animation."""
        print("[Waveform] Ready for audio input")
        self.is_active = True
        self.receiving_audio = False  # Will be set True when audio callback fires
        # Ensure bars exist
        if not self._bars_created or not self.bars:
            self._create_bars()
        # Show "waiting" state - slightly elevated bars in accent color to indicate active
        self._show_waiting_state()

    def stop_animation(self) -> None:
        """Stop waveform animation."""
        print("[Waveform] Stopping animation")
        self.is_active = False
        self.receiving_audio = False
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None
        self._reset_bars()

    def _show_waiting_state(self) -> None:
        """Show visual indication that waveform is ready and waiting for audio."""
        if not self.bars or not self._bars_created:
            return

        try:
            height = self.canvas.winfo_height()
            if height < 20:
                height = self._canvas_height

            # Show small elevated bars in accent color to indicate "active/waiting"
            for bar in self.bars:
                coords = self.canvas.coords(bar)
                if not coords or len(coords) < 4:
                    continue
                x1, _, x2, _ = coords
                y_center = height / 2
                bar_height = 8  # Small but visible

                self.canvas.coords(bar, x1, y_center - bar_height / 2, x2, y_center + bar_height / 2)
                self.canvas.itemconfig(bar, fill=THEME["accent_secondary"])  # Teal to indicate waiting
        except Exception as e:
            print(f"[Waveform] Waiting state error: {e}")

    def _reset_bars(self) -> None:
        """Reset bars to idle state."""
        if not self.bars or not self._bars_created:
            return

        try:
            height = self.canvas.winfo_height()
            if height < 20:
                height = self._canvas_height

            for bar in self.bars:
                coords = self.canvas.coords(bar)
                if not coords or len(coords) < 4:
                    continue
                x1, _, x2, _ = coords
                y_center = height / 2
                self.canvas.coords(bar, x1, y_center - 2, x2, y_center + 2)
                self.canvas.itemconfig(bar, fill=THEME["text_muted"])
        except Exception as e:
            print(f"[Waveform] Reset error: {e}")

    def update_level(self, level: float) -> None:
        """
        Update waveform based on audio level from microphone.

        Args:
            level: Audio level (0.0-1.0)
        """
        if not self.is_active:
            return

        # First audio callback - switch from random to audio-driven animation
        if not self.receiving_audio:
            self.receiving_audio = True
            # Cancel any pending random animation
            if self.animation_id:
                self.after_cancel(self.animation_id)
                self.animation_id = None
            print("[Waveform] Switched to audio-driven mode")

        # Schedule update on main thread (callback may come from audio thread)
        self.after(0, lambda: self._do_update_level(level))

    def _do_update_level(self, level: float) -> None:
        """Actually update the waveform bars based on audio level."""
        if not self.is_active:
            return

        if not self.bars or not self._bars_created:
            return

        try:
            height = self.canvas.winfo_height()
            if height < 20:
                height = self._canvas_height

            for i, bar in enumerate(self.bars):
                # Add slight variation per bar for visual interest, but based on actual audio level
                variation = random.uniform(0.8, 1.2)
                # Boost amplitude for more visible response (square root for better low-level visibility)
                boosted_level = (level ** 0.6) * 1.5  # Non-linear boost for sensitivity
                amplitude = max(0.08, boosted_level * variation)
                bar_height = max(4, int(amplitude * (height * 0.95)))

                coords = self.canvas.coords(bar)
                if not coords or len(coords) < 4:
                    continue
                x1, _, x2, _ = coords
                y_center = height / 2

                self.canvas.coords(
                    bar,
                    x1, y_center - bar_height / 2,
                    x2, y_center + bar_height / 2
                )
                # Color based on intensity - brighter orange for louder audio
                if level > 0.3:
                    self.canvas.itemconfig(bar, fill=THEME["accent"])
                elif level > 0.1:
                    self.canvas.itemconfig(bar, fill=THEME["accent_secondary"])
                else:
                    self.canvas.itemconfig(bar, fill=THEME["text_secondary"])
        except Exception as e:
            print(f"[Waveform] Level update error: {e}")


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


class LoadingSpinner(ctk.CTkFrame):
    """Animated loading spinner with status text."""

    def __init__(self, master, **kwargs):
        """
        Initialize loading spinner.

        Args:
            master: Parent widget
            **kwargs: Additional frame arguments
        """
        super().__init__(master, fg_color="transparent", **kwargs)

        self.is_spinning = False
        self.animation_id = None
        self.spinner_chars = ["◐", "◓", "◑", "◒"]
        self.current_frame = 0

        # Spinner label
        self.spinner_label = ctk.CTkLabel(
            self,
            text="◐",
            font=("SF Pro Display", 24),
            text_color=THEME["accent"]
        )
        self.spinner_label.pack(side="left", padx=(0, 8))

        # Status text
        self.status_label = ctk.CTkLabel(
            self,
            text="Loading...",
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        )
        self.status_label.pack(side="left")

        # Character/token count
        self.count_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["small"],
            text_color=THEME["text_muted"]
        )
        self.count_label.pack(side="right")

    def start(self, text: str = "Loading...") -> None:
        """Start spinner animation."""
        self.status_label.configure(text=text)
        self.count_label.configure(text="")
        self.is_spinning = True
        self._animate()

    def stop(self) -> None:
        """Stop spinner animation."""
        self.is_spinning = False
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None

    def set_text(self, text: str) -> None:
        """Update the status text."""
        self.status_label.configure(text=text)

    def set_count(self, count_text: str) -> None:
        """Update the character/token count display."""
        self.count_label.configure(text=count_text)

    def _animate(self) -> None:
        """Animate the spinner."""
        if not self.is_spinning:
            return

        self.current_frame = (self.current_frame + 1) % len(self.spinner_chars)
        self.spinner_label.configure(text=self.spinner_chars[self.current_frame])

        self.animation_id = self.after(100, self._animate)


class PulsingIndicator(ctk.CTkFrame):
    """Pulsing animation indicator for inference progress."""

    def __init__(self, master, bar_count: int = 5, **kwargs):
        """
        Initialize pulsing indicator.

        Args:
            master: Parent widget
            bar_count: Number of pulsing bars
            **kwargs: Additional frame arguments
        """
        super().__init__(master, fg_color="transparent", **kwargs)

        self.is_pulsing = False
        self.animation_id = None
        self.bars = []
        self.bar_count = bar_count
        self.current_phase = 0

        # Create bars
        for i in range(bar_count):
            bar = ctk.CTkLabel(
                self,
                text="▮",
                font=("SF Pro Display", 16),
                text_color=THEME["text_muted"]
            )
            bar.pack(side="left", padx=2)
            self.bars.append(bar)

        # Status text
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["small"],
            text_color=THEME["text_secondary"]
        )
        self.status_label.pack(side="left", padx=(12, 0))

    def start(self, text: str = "Processing...") -> None:
        """Start pulsing animation."""
        self.status_label.configure(text=text)
        self.is_pulsing = True
        self._animate()

    def stop(self) -> None:
        """Stop pulsing animation."""
        self.is_pulsing = False
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None
        # Reset all bars to muted
        for bar in self.bars:
            bar.configure(text_color=THEME["text_muted"])

    def set_text(self, text: str) -> None:
        """Update the status text."""
        self.status_label.configure(text=text)

    def _animate(self) -> None:
        """Animate the pulsing bars."""
        if not self.is_pulsing:
            return

        # Create wave effect
        for i, bar in enumerate(self.bars):
            # Calculate distance from current phase
            dist = abs((self.current_phase % self.bar_count) - i)
            if dist > self.bar_count // 2:
                dist = self.bar_count - dist

            if dist == 0:
                bar.configure(text_color=THEME["accent"])
            elif dist == 1:
                bar.configure(text_color=THEME["accent_secondary"])
            else:
                bar.configure(text_color=THEME["text_muted"])

        self.current_phase = (self.current_phase + 1) % self.bar_count

        self.animation_id = self.after(150, self._animate)


class GearSpinner(ctk.CTkFrame):
    """Animated spinner for refinement with rotating indicator."""

    def __init__(self, master, **kwargs):
        """
        Initialize gear spinner.

        Args:
            master: Parent widget
            **kwargs: Additional frame arguments
        """
        super().__init__(master, fg_color="transparent", **kwargs)

        self.is_spinning = False
        self.animation_id = None
        # Use rotating characters for visible animation
        self.spinner_chars = ["◐", "◓", "◑", "◒"]
        self.current_frame = 0

        # Spinner label with larger, more visible font
        self.spinner_label = ctk.CTkLabel(
            self,
            text="⚙",
            font=("SF Pro Display", 20),
            text_color=THEME["accent"]
        )
        self.spinner_label.pack(side="left", padx=(0, 8))

        # Status text
        self.status_label = ctk.CTkLabel(
            self,
            text="",
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        )
        self.status_label.pack(side="left")

    def start(self, text: str = "Refining...") -> None:
        """Start spinner animation."""
        print(f"[GearSpinner] Starting animation: {text}")
        self.status_label.configure(text=text)
        self.is_spinning = True
        self.current_frame = 0
        self._animate()

    def stop(self) -> None:
        """Stop spinner animation."""
        print("[GearSpinner] Stopping animation")
        self.is_spinning = False
        if self.animation_id:
            self.after_cancel(self.animation_id)
            self.animation_id = None
        self.spinner_label.configure(text="⚙", text_color=THEME["text_muted"])

    def set_text(self, text: str) -> None:
        """Update the status text."""
        self.status_label.configure(text=text)

    def _animate(self) -> None:
        """Animate the spinner with rotating characters."""
        if not self.is_spinning:
            return

        # Update spinner character
        self.spinner_label.configure(
            text=self.spinner_chars[self.current_frame],
            text_color=THEME["accent"]
        )
        self.current_frame = (self.current_frame + 1) % len(self.spinner_chars)

        # Schedule next frame (8fps for visible rotation)
        self.animation_id = self.after(125, self._animate)


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
