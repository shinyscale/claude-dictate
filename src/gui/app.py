"""
Main application window for Claude Dictate GUI
Coordinates all GUI components and app logic.
"""

import threading
from tkinter import messagebox
from typing import Optional

import customtkinter as ctk

from .theme import THEME, FONTS, WINDOW_WIDTH, WINDOW_HEIGHT, LEFT_PANEL_WIDTH
from .recorder import WaveformCanvas, StatusIndicator, ProgressBar
from .editor import TextEditor
from .settings import SettingsPanel

from ..main import ClaudeDictate, HotkeyListener
from ..config import DEFAULT_CONFIG


class ClaudeDictateGUI(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Configure window
        self.title("Claude Dictate")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.configure(fg_color=THEME["bg_dark"])

        # Set appearance
        ctk.set_appearance_mode("dark")

        # Initialize app
        self.config = DEFAULT_CONFIG.copy()
        self.app = ClaudeDictate(self.config)
        self._setup_callbacks()

        # State
        self.is_recording = False
        self.current_style = "clean"
        self.hotkey_listener: Optional[HotkeyListener] = None

        # Create UI
        self._create_layout()
        self._bind_hotkey()

    def _setup_callbacks(self) -> None:
        """Setup application callbacks."""
        self.app.on_recording_start = self._on_recording_start
        self.app.on_recording_stop = self._on_recording_stop
        self.app.on_transcription_complete = self._on_transcription_complete
        self.app.on_refinement_complete = self._on_refinement_complete
        self.app.on_status_update = self._on_status_update

    def _create_layout(self) -> None:
        """Create the main layout."""
        # Header
        self._create_header()

        # Main content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        # Left panel - Recording controls
        left_panel = ctk.CTkFrame(
            content,
            fg_color=THEME["bg_light"],
            corner_radius=12,
            width=LEFT_PANEL_WIDTH
        )
        left_panel.pack(side="left", fill="y", padx=(0, 16))
        left_panel.pack_propagate(False)
        self._create_control_panel(left_panel)

        # Right panel - Text editors
        right_panel = ctk.CTkFrame(content, fg_color="transparent")
        right_panel.pack(side="left", fill="both", expand=True)
        self._create_editor_panel(right_panel)

    def _create_header(self) -> None:
        """Create header with title and settings."""
        header = ctk.CTkFrame(self, fg_color="transparent", height=80)
        header.pack(fill="x", padx=24, pady=(24, 16))
        header.pack_propagate(False)

        # Logo and title
        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.pack(side="left")

        ctk.CTkLabel(
            title_frame,
            text="◉",
            font=("SF Pro Display", 32),
            text_color=THEME["accent"]
        ).pack(side="left", padx=(0, 12))

        ctk.CTkLabel(
            title_frame,
            text="Claude Dictate",
            font=FONTS["title"],
            text_color=THEME["text_primary"]
        ).pack(side="left")

        # Settings button
        ctk.CTkButton(
            header,
            text="⚙",
            font=("SF Pro Display", 20),
            width=44,
            height=44,
            fg_color="transparent",
            hover_color=THEME["bg_light"],
            command=self._open_settings
        ).pack(side="right")

        # Status indicator
        self.status = StatusIndicator(header)
        self.status.pack(side="right", padx=24)

    def _create_control_panel(self, parent) -> None:
        """Create recording control panel."""
        # Title
        ctk.CTkLabel(
            parent,
            text="Voice Input",
            font=FONTS["heading"],
            text_color=THEME["text_primary"]
        ).pack(anchor="w", padx=20, pady=(20, 8))

        ctk.CTkLabel(
            parent,
            text=f"Click button or use {self.config.get('hotkey', 'ctrl+shift')} hotkey",
            font=FONTS["small"],
            text_color=THEME["text_muted"]
        ).pack(anchor="w", padx=20, pady=(0, 16))

        # Waveform visualization
        self.waveform = WaveformCanvas(parent, height=80)
        self.waveform.pack(fill="x", padx=20, pady=(0, 12))

        # Progress bar (hidden by default)
        self.progress_bar = ProgressBar(parent)

        # Record button - click to toggle (more reliable than hold)
        self.record_btn = ctk.CTkButton(
            parent,
            text="🎤 Click to Record",
            font=FONTS["body"],
            height=56,
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            corner_radius=28,
            command=self._toggle_recording
        )
        self.record_btn.pack(fill="x", padx=20, pady=(0, 24))

        # Divider
        ctk.CTkFrame(parent, fg_color=THEME["border"], height=1).pack(fill="x", padx=20, pady=8)

        # Refinement options
        ctk.CTkLabel(
            parent,
            text="LLM Refinement",
            font=FONTS["heading"],
            text_color=THEME["text_primary"]
        ).pack(anchor="w", padx=20, pady=(16, 8))

        # Style selector
        style_frame = ctk.CTkFrame(parent, fg_color="transparent")
        style_frame.pack(fill="x", padx=20, pady=(0, 12))

        self.style_var = ctk.StringVar(value="clean")
        styles = [
            ("Clean", "clean"),
            ("Professional", "professional"),
            ("Technical", "technical"),
            ("Casual", "casual"),
            ("PRD Format", "prd"),
            ("Markdown", "bullets"),
        ]

        for label, value in styles:
            ctk.CTkRadioButton(
                style_frame,
                text=label,
                variable=self.style_var,
                value=value,
                font=FONTS["small"],
                fg_color=THEME["accent"],
                hover_color=THEME["accent_hover"]
            ).pack(anchor="w", pady=4)

        # Refine button
        self.refine_btn = ctk.CTkButton(
            parent,
            text="✨ Refine with LLM",
            font=FONTS["body"],
            height=44,
            fg_color=THEME["accent_secondary"],
            hover_color="#6EDDD4",
            command=self._refine_text
        )
        self.refine_btn.pack(fill="x", padx=20, pady=(8, 24))

        # Divider
        ctk.CTkFrame(parent, fg_color=THEME["border"], height=1).pack(fill="x", padx=20, pady=8)

        # Export options
        ctk.CTkLabel(
            parent,
            text="Export",
            font=FONTS["heading"],
            text_color=THEME["text_primary"]
        ).pack(anchor="w", padx=20, pady=(16, 12))

        export_btns = ctk.CTkFrame(parent, fg_color="transparent")
        export_btns.pack(fill="x", padx=20)

        ctk.CTkButton(
            export_btns,
            text="📋 Copy",
            font=FONTS["small"],
            width=85,
            height=36,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["bg_dark"],
            command=self._copy_to_clipboard
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            export_btns,
            text="📝 .md",
            font=FONTS["small"],
            width=85,
            height=36,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["bg_dark"],
            command=self._save_markdown
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            export_btns,
            text="📄 .prd",
            font=FONTS["small"],
            width=85,
            height=36,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["bg_dark"],
            command=self._save_prd
        ).pack(side="left")

        # Prompt button
        ctk.CTkButton(
            parent,
            text="🚀 Save as Claude Code Prompt",
            font=FONTS["small"],
            height=36,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["bg_dark"],
            command=self._save_prompt
        ).pack(fill="x", padx=20, pady=(12, 8))

        # Clear button
        ctk.CTkButton(
            parent,
            text="🗑️ Clear All",
            font=FONTS["small"],
            height=36,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["error"],
            command=self._clear_editors
        ).pack(fill="x", padx=20, pady=(0, 20))

    def _create_editor_panel(self, parent) -> None:
        """Create text editor panels."""
        # Top editor - Raw transcription
        self.raw_editor = TextEditor(parent, "Raw Transcription")
        self.raw_editor.pack(fill="both", expand=True, pady=(0, 8))

        # Bottom editor - Refined text
        self.refined_editor = TextEditor(parent, "Refined Text")
        self.refined_editor.pack(fill="both", expand=True, pady=(8, 0))

    def _bind_hotkey(self) -> None:
        """Bind keyboard hotkey for recording using pynput."""
        try:
            hotkey = self.config.get("hotkey", "ctrl+shift")

            # Stop existing listener
            if self.hotkey_listener:
                self.hotkey_listener.stop()

            self.hotkey_listener = HotkeyListener(
                hotkey_combo=hotkey,
                on_activate=lambda: self.after(0, self._start_recording),
                on_deactivate=lambda: self.after(0, self._stop_recording)
            )
            self.hotkey_listener.start()

        except Exception as e:
            print(f"Could not bind hotkey: {e}")

    def _toggle_recording(self) -> None:
        """Toggle recording on/off."""
        print(f"[DEBUG] _toggle_recording called, is_recording={self.is_recording}")
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        """Start recording."""
        print("[DEBUG] _start_recording called")
        if self.is_recording:
            print("[DEBUG] Already recording, returning")
            return

        try:
            self.is_recording = True
            self.record_btn.configure(text="🔴 Click to Stop", fg_color=THEME["error"])
            self.waveform.start_animation()
            self.status.set_status("Recording...", THEME["error"])
            print("[DEBUG] UI updated, starting recording thread")

            # Start recording in background
            def start():
                try:
                    print("[DEBUG] Background thread: calling app.start_recording()")
                    self.app.start_recording()
                    print("[DEBUG] Background thread: start_recording() returned")
                except Exception as e:
                    print(f"[DEBUG] Background thread error: {e}")
                    import traceback
                    traceback.print_exc()
                    error_msg = f"Recording error: {e}"
                    self.after(0, lambda msg=error_msg: self._on_error(msg))

            threading.Thread(target=start, daemon=True).start()
            print("[DEBUG] Recording thread started")

        except Exception as e:
            print(f"[DEBUG] Exception in _start_recording: {e}")
            import traceback
            traceback.print_exc()
            self._on_error(f"Failed to start recording: {e}")

    def _stop_recording(self) -> None:
        """Stop recording and transcribe."""
        if not self.is_recording:
            return

        self.is_recording = False
        self.record_btn.configure(text="🎤 Click to Record", fg_color=THEME["accent"])
        self.waveform.stop_animation()

        # Show progress bar
        self.progress_bar.show()
        self.progress_bar.set_progress(0.1, "Processing audio...")
        self.status.set_status("Processing...", THEME["warning"])

        # Stop recording in background
        def stop_and_transcribe():
            try:
                self.after(0, lambda: self.progress_bar.set_progress(0.3, "Transcribing..."))
                self.after(0, lambda: self.status.set_status("Transcribing...", THEME["warning"]))
                result = self.app.stop_recording()
                self.after(0, lambda: self.progress_bar.set_progress(1.0, "Done"))
                if result:
                    self.after(0, lambda: self.status.set_status("Ready", THEME["success"]))
                else:
                    self.after(0, lambda: self.status.set_status("No audio captured", THEME["warning"]))
                self.after(500, self.progress_bar.hide)
            except Exception as e:
                self.after(0, lambda: self._on_error(f"Transcription error: {e}"))
                self.after(0, self.progress_bar.hide)

        threading.Thread(target=stop_and_transcribe, daemon=True).start()

    def _on_error(self, message: str) -> None:
        """Handle and display errors."""
        self.is_recording = False
        self.record_btn.configure(text="🎤 Click to Record", fg_color=THEME["accent"])
        self.waveform.stop_animation()
        self.status.set_status(message[:50], THEME["error"])
        print(f"Error: {message}")  # Also log to console

    def _refine_text(self) -> None:
        """Refine transcribed text with LLM."""
        text = self.raw_editor.get_text()
        if not text.strip():
            return

        style = self.style_var.get()

        # Show progress
        self.progress_bar.show()
        self.progress_bar.set_progress(0.2, f"Refining with {style} style...")

        def refine():
            self.app.refine_text(text, style)
            self.after(0, lambda: self.progress_bar.set_progress(1.0, "Done"))
            self.after(500, self.progress_bar.hide)

        threading.Thread(target=refine, daemon=True).start()

    def _copy_to_clipboard(self) -> None:
        """Copy refined or raw text to clipboard."""
        text = self.refined_editor.get_text() or self.raw_editor.get_text()
        if text.strip():
            self.app.copy_to_clipboard(text)

    def _save_markdown(self) -> None:
        """Save as markdown file."""
        text = self.refined_editor.get_text() or self.raw_editor.get_text()
        if text.strip():
            path = self.app.save_as_markdown(text)
            if path:
                messagebox.showinfo("Saved", f"Saved to:\n{path}")

    def _save_prd(self) -> None:
        """Save as PRD file."""
        text = self.refined_editor.get_text() or self.raw_editor.get_text()
        if text.strip():
            path = self.app.save_as_prd(text)
            if path:
                messagebox.showinfo("Saved", f"Saved to:\n{path}")

    def _save_prompt(self) -> None:
        """Save as Claude Code prompt."""
        text = self.refined_editor.get_text() or self.raw_editor.get_text()
        if text.strip():
            path = self.app.save_as_prompt(text)
            if path:
                messagebox.showinfo("Saved", f"Saved to:\n{path}")

    def _clear_editors(self) -> None:
        """Clear both text editors."""
        self.raw_editor.clear()
        self.refined_editor.clear()
        self.status.set_status("Cleared", THEME["text_muted"])

    def _open_settings(self) -> None:
        """Open settings panel."""
        SettingsPanel(self, self.config, self._on_settings_save)

    def _on_settings_save(self, new_config: dict) -> None:
        """Handle settings save."""
        self.config.update(new_config)

        # Reinitialize app with new config
        self.app.cleanup()
        self.app = ClaudeDictate(self.config)
        self._setup_callbacks()

        # Rebind hotkey
        self._bind_hotkey()

    # Callbacks
    def _on_recording_start(self) -> None:
        """Called when recording starts."""
        pass

    def _on_recording_stop(self) -> None:
        """Called when recording stops."""
        pass

    def _on_transcription_complete(self, text: str) -> None:
        """Called when transcription is complete. Appends to existing text."""
        def append():
            current = self.raw_editor.get_text().strip()
            if current:
                self.raw_editor.set_text(current + " " + text)
            else:
                self.raw_editor.set_text(text)
        self.after(0, append)

    def _on_refinement_complete(self, text: str) -> None:
        """Called when refinement is complete."""
        self.after(0, lambda: self.refined_editor.set_text(text))

    def _on_status_update(self, status: str) -> None:
        """Called when status updates."""
        self.after(0, lambda: self.status.set_status(status))

    def on_closing(self) -> None:
        """Handle window close."""
        self.app.cleanup()
        if self.hotkey_listener:
            self.hotkey_listener.stop()
        self.destroy()


def run_gui() -> None:
    """Run the GUI application."""
    app = ClaudeDictateGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    run_gui()
