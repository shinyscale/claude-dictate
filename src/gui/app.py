"""
Main application window for Claude Dictate GUI
Coordinates all GUI components and app logic.
"""

import threading
from tkinter import messagebox, filedialog
from typing import Optional

import customtkinter as ctk

from .theme import THEME, FONTS, WINDOW_WIDTH, WINDOW_HEIGHT, WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT, LEFT_PANEL_WIDTH
from .recorder import WaveformCanvas, StatusIndicator, ProgressBar, LoadingSpinner, GearSpinner, PulsingIndicator
from .editor import TextEditor
from .settings import SettingsPanel
from .tray import SystemTray, is_tray_available

from ..main import ClaudeDictate, HotkeyListener
from ..config import DEFAULT_CONFIG, AppConfig


class ClaudeDictateGUI(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Configure window
        self.title("Claude Dictate")
        self.configure(fg_color=THEME["bg_dark"])

        # Set appearance
        ctk.set_appearance_mode("dark")

        # Load saved configuration or use defaults
        self.config = self._load_config()

        # Apply window geometry (saved or defaults)
        self._apply_window_geometry()

        # Set minimum window size
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        # Initialize app
        self.app = ClaudeDictate(self.config)
        self._setup_callbacks()

        # State
        self.is_recording = False
        self.is_refining = False
        self.current_style = "clean"
        self.hotkey_listener: Optional[HotkeyListener] = None
        self.system_tray: Optional[SystemTray] = None
        self._is_hidden_to_tray = False

        # Create UI
        self._create_layout()
        self._bind_hotkey()

        # Connect waveform to audio level updates
        self.app.recorder.on_level_update = self.waveform.update_level

        # Initialize system tray if enabled
        self._init_system_tray()

    def _apply_window_geometry(self) -> None:
        """Apply saved window geometry or use defaults."""
        width = self.config.get("window_width") or WINDOW_WIDTH
        height = self.config.get("window_height") or WINDOW_HEIGHT
        x = self.config.get("window_x")
        y = self.config.get("window_y")

        # Validate dimensions
        width = max(WINDOW_MIN_WIDTH, min(width, self.winfo_screenwidth()))
        height = max(WINDOW_MIN_HEIGHT, min(height, self.winfo_screenheight()))

        if x is not None and y is not None:
            # Validate position is on screen
            screen_width = self.winfo_screenwidth()
            screen_height = self.winfo_screenheight()
            x = max(0, min(x, screen_width - 100))
            y = max(0, min(y, screen_height - 100))
            self.geometry(f"{width}x{height}+{x}+{y}")
        else:
            self.geometry(f"{width}x{height}")

    def _save_window_geometry(self) -> None:
        """Save current window geometry to config."""
        try:
            self.config["window_width"] = self.winfo_width()
            self.config["window_height"] = self.winfo_height()
            self.config["window_x"] = self.winfo_x()
            self.config["window_y"] = self.winfo_y()

            # Persist to disk
            app_config = AppConfig.from_dict(self.config)
            app_config.save()
            print(f"[GUI] Window geometry saved: {self.winfo_width()}x{self.winfo_height()} at ({self.winfo_x()}, {self.winfo_y()})")
        except Exception as e:
            print(f"[GUI] Failed to save window geometry: {e}")

    def _load_config(self) -> dict:
        """Load configuration from disk or use defaults."""
        try:
            saved_config = AppConfig.load()
            config = saved_config.to_flat_dict()
            print(f"[GUI] Loaded saved configuration from {AppConfig.get_config_path()}")
            return config
        except Exception as e:
            print(f"[GUI] Could not load saved config: {e}, using defaults")
            return DEFAULT_CONFIG.copy()

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

        # Export toolbar (always visible)
        self._create_toolbar()

        # Main content
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24, pady=(0, 24))

        # Left panel container - fixed width
        left_container = ctk.CTkFrame(
            content,
            fg_color=THEME["bg_light"],
            corner_radius=12,
            width=LEFT_PANEL_WIDTH
        )
        left_container.pack(side="left", fill="y", padx=(0, 16))
        left_container.pack_propagate(False)

        # Scrollable frame inside the left container
        self.left_scroll = ctk.CTkScrollableFrame(
            left_container,
            fg_color="transparent",
            scrollbar_button_color=THEME["bg_medium"],
            scrollbar_button_hover_color=THEME["accent"]
        )
        self.left_scroll.pack(fill="both", expand=True)

        self._create_control_panel(self.left_scroll)

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

    def _create_toolbar(self) -> None:
        """Create export toolbar below header."""
        toolbar = ctk.CTkFrame(self, fg_color=THEME["bg_light"], height=50, corner_radius=8)
        toolbar.pack(fill="x", padx=24, pady=(0, 16))
        toolbar.pack_propagate(False)

        # Left side - Export buttons
        export_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        export_frame.pack(side="left", fill="y", padx=12)

        ctk.CTkLabel(
            export_frame,
            text="Export:",
            font=FONTS["small"],
            text_color=THEME["text_secondary"]
        ).pack(side="left", padx=(0, 8))

        # Copy button
        ctk.CTkButton(
            export_frame,
            text="📋 Copy",
            font=FONTS["small"],
            width=75,
            height=34,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["bg_dark"],
            command=self._copy_to_clipboard
        ).pack(side="left", padx=4)

        # Save as .md
        ctk.CTkButton(
            export_frame,
            text="📝 .md",
            font=FONTS["small"],
            width=70,
            height=34,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["bg_dark"],
            command=self._save_markdown
        ).pack(side="left", padx=4)

        # Save as .prd
        ctk.CTkButton(
            export_frame,
            text="📄 .prd",
            font=FONTS["small"],
            width=70,
            height=34,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["bg_dark"],
            command=self._save_prd
        ).pack(side="left", padx=4)

        # Save as Prompt
        ctk.CTkButton(
            export_frame,
            text="🚀 Prompt",
            font=FONTS["small"],
            width=90,
            height=34,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["bg_dark"],
            command=self._save_prompt
        ).pack(side="left", padx=4)

        # Right side - Output directory and Clear
        right_frame = ctk.CTkFrame(toolbar, fg_color="transparent")
        right_frame.pack(side="right", fill="y", padx=12)

        # Clear button
        ctk.CTkButton(
            right_frame,
            text="🗑️",
            font=FONTS["small"],
            width=40,
            height=34,
            fg_color=THEME["bg_medium"],
            hover_color=THEME["error"],
            command=self._clear_editors
        ).pack(side="right", padx=(8, 0))

        # Output directory browse button
        ctk.CTkButton(
            right_frame,
            text="📁",
            font=FONTS["small"],
            width=40,
            height=34,
            fg_color=THEME["action_green"],
            hover_color=THEME["action_green_hover"],
            command=self._browse_output_dir
        ).pack(side="right")

        # Output directory entry
        self.output_dir_var = ctk.StringVar(value=self.config.get("output_dir", "./outputs"))
        self.output_dir_entry = ctk.CTkEntry(
            right_frame,
            textvariable=self.output_dir_var,
            font=FONTS["small"],
            fg_color=THEME["bg_medium"],
            border_color=THEME["border"],
            width=180,
            height=34,
            placeholder_text="Output directory..."
        )
        self.output_dir_entry.pack(side="right", padx=(0, 4))

        # Output label
        ctk.CTkLabel(
            right_frame,
            text="Save to:",
            font=FONTS["small"],
            text_color=THEME["text_secondary"]
        ).pack(side="right", padx=(0, 4))

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

        # Style selector dropdown
        style_frame = ctk.CTkFrame(parent, fg_color="transparent")
        style_frame.pack(fill="x", padx=20, pady=(0, 12))

        # Map display names to style codes
        self.style_map = {
            "Clean": "clean",
            "Professional": "professional",
            "Technical": "technical",
            "Casual": "casual",
            "PRD Format": "prd",
            "Markdown": "bullets",
        }
        style_names = list(self.style_map.keys())

        ctk.CTkLabel(
            style_frame,
            text="Style:",
            font=FONTS["small"],
            text_color=THEME["text_secondary"]
        ).pack(anchor="w", pady=(0, 4))

        self.style_var = ctk.StringVar(value="Clean")
        self.style_dropdown = ctk.CTkComboBox(
            style_frame,
            variable=self.style_var,
            values=style_names,
            font=FONTS["body"],
            fg_color=THEME["bg_medium"],
            border_color=THEME["border"],
            button_color=THEME["accent"],
            button_hover_color=THEME["accent_hover"],
            dropdown_fg_color=THEME["bg_medium"],
            height=36,
            state="readonly"
        )
        self.style_dropdown.pack(fill="x")

        # Refine button
        self.refine_btn = ctk.CTkButton(
            parent,
            text="✨ Refine with LLM",
            font=FONTS["body"],
            height=44,
            fg_color=THEME["action_green"],
            hover_color=THEME["action_green_hover"],
            command=self._refine_text
        )
        self.refine_btn.pack(fill="x", padx=20, pady=(8, 4))

        # Model info display
        model_backend = self.config.get("default_llm", "ollama")
        model_name = self.config.get("default_model", "llama3.2")
        self.model_label = ctk.CTkLabel(
            parent,
            text=f"Model: {model_backend}/{model_name}",
            font=FONTS["small"],
            text_color=THEME["text_muted"]
        )
        self.model_label.pack(anchor="w", padx=20, pady=(2, 4))

        # Spinner container frame - always in layout, content shown/hidden
        self.spinner_container = ctk.CTkFrame(parent, fg_color="transparent", height=30)
        self.spinner_container.pack(fill="x", padx=20, pady=(0, 12))

        # Gear spinner for refinement (inside container, hidden by default)
        self.refine_spinner = GearSpinner(self.spinner_container)
        # Don't pack initially - will be shown when refining

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
        if self.is_refining:
            return

        text = self.raw_editor.get_text()
        if not text.strip():
            print("[DEBUG] _refine_text: No text to refine")
            return

        self.is_refining = True

        # Convert display name to style code
        style_display = self.style_var.get()
        style = self.style_map.get(style_display, "clean")
        print(f"[DEBUG] _refine_text: Starting refinement with style='{style}' (display: '{style_display}'), text_len={len(text)}")

        # Show gear spinner animation inside container
        self.refine_spinner.pack(fill="x", expand=True)
        self.refine_spinner.start(f"Refining... ({len(text)} chars)")
        self.refine_btn.configure(state="disabled", text="⏳ Refining...")

        # Show progress bar too
        self.progress_bar.show()
        self.progress_bar.set_progress(0.2, f"Refining with {style} style...")

        def refine():
            print(f"[DEBUG] refine thread: Calling app.refine_text()")
            result = self.app.refine_text(text, style)
            print(f"[DEBUG] refine thread: app.refine_text returned: {type(result)}, len={len(result) if result else 0}")
            self.after(0, self._on_refine_complete)

        threading.Thread(target=refine, daemon=True).start()

    def _on_refine_complete(self) -> None:
        """Called when refinement is complete - hide animations."""
        self.is_refining = False
        self.refine_spinner.stop()
        self.refine_spinner.pack_forget()
        self.refine_btn.configure(state="normal", text="✨ Refine with LLM")
        self.progress_bar.set_progress(1.0, "Done")
        self.after(500, self.progress_bar.hide)

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

    def _browse_output_dir(self) -> None:
        """Open directory browser for output directory selection."""
        current = self.output_dir_var.get() or "./outputs"
        path = filedialog.askdirectory(
            initialdir=current,
            title="Select Output Directory"
        )
        if path:
            self.output_dir_var.set(path)
            self.config["output_dir"] = path
            # Update the app's exporter with new output directory
            if hasattr(self.app, 'exporter'):
                self.app.exporter.output_dir = path

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

        # Reconnect waveform callback
        self.app.recorder.on_level_update = self.waveform.update_level

        # Rebind hotkey
        self._bind_hotkey()

        # Sync output directory to main UI
        if hasattr(self, 'output_dir_var'):
            self.output_dir_var.set(self.config.get("output_dir", "./outputs"))

        # Update model label
        if hasattr(self, 'model_label'):
            model_backend = self.config.get("default_llm", "ollama")
            model_name = self.config.get("default_model", "llama3.2")
            self.model_label.configure(text=f"Model: {model_backend}/{model_name}")

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
        print(f"[DEBUG] _on_refinement_complete callback fired, text_len={len(text) if text else 0}")
        self.after(0, lambda: self.refined_editor.set_text(text))

    def _on_status_update(self, status: str) -> None:
        """Called when status updates."""
        self.after(0, lambda: self.status.set_status(status))

    def _init_system_tray(self) -> None:
        """Initialize system tray if available and enabled."""
        if not is_tray_available():
            print("[GUI] System tray not available")
            return

        # Always create tray but only start if minimize_to_tray is enabled
        self.system_tray = SystemTray(
            on_show=self._show_from_tray,
            on_settings=self._open_settings,
            on_exit=self._exit_app
        )

        # Start tray icon if minimize to tray is enabled
        if self.config.get("minimize_to_tray", False):
            self.system_tray.start()
            print("[GUI] System tray started (minimize_to_tray enabled)")

    def _show_from_tray(self) -> None:
        """Show window from system tray."""
        self._is_hidden_to_tray = False
        self.deiconify()
        self.lift()
        self.focus_force()
        print("[GUI] Window restored from tray")

    def _hide_to_tray(self) -> None:
        """Hide window to system tray."""
        if not self.system_tray or not is_tray_available():
            return

        # Ensure tray is running
        if not self.system_tray.is_running:
            self.system_tray.start()

        self._is_hidden_to_tray = True
        self._save_window_geometry()
        self.withdraw()
        print("[GUI] Window hidden to tray")

    def _exit_app(self) -> None:
        """Exit the application completely."""
        self._is_hidden_to_tray = False
        self._save_window_geometry()

        # Stop system tray
        if self.system_tray:
            self.system_tray.stop()

        # Cleanup
        self.app.cleanup()
        if self.hotkey_listener:
            self.hotkey_listener.stop()

        self.destroy()

    def on_closing(self) -> None:
        """Handle window close."""
        # If minimize to tray is enabled, hide instead of exit
        if self.config.get("minimize_to_tray", False) and is_tray_available():
            self._hide_to_tray()
            return

        # Otherwise exit normally
        self._exit_app()


def run_gui() -> None:
    """Run the GUI application."""
    app = ClaudeDictateGUI()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    run_gui()
