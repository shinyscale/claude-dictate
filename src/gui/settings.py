"""
Settings dialog for Claude Dictate GUI
Configuration panel for all app settings.
"""

import threading
from tkinter import filedialog
from typing import Callable, Optional, List

import customtkinter as ctk
import requests

from .theme import THEME, FONTS
from ..audio import AudioRecorder


class SettingsPanel(ctk.CTkToplevel):
    """Settings window with Ollama integration."""

    def __init__(
        self,
        master,
        config: dict,
        on_save: Optional[Callable[[dict], None]] = None
    ):
        super().__init__(master)

        self.config = config.copy()
        self.on_save = on_save
        self.ollama_models: List[str] = []
        self.audio_devices: List[dict] = []

        self.title("Settings")
        self.geometry("600x920")
        self.configure(fg_color=THEME["bg_dark"])

        # Make modal
        self.transient(master)
        self.grab_set()

        # Center on parent
        self.update_idletasks()
        x = master.winfo_x() + (master.winfo_width() - 600) // 2
        y = master.winfo_y() + (master.winfo_height() - 920) // 2
        self.geometry(f"+{x}+{y}")

        self._create_widgets()

        # Fetch Ollama models on open
        self._fetch_ollama_models()

    def _fetch_ollama_models(self) -> None:
        """Fetch available models from Ollama API."""
        def fetch():
            try:
                url = self.ollama_url_var.get() or "http://localhost:11434"
                print(f"[Settings] Connecting to Ollama at {url}...")
                response = requests.get(f"{url}/api/tags", timeout=5)
                if response.status_code == 200:
                    data = response.json()
                    models = [m["name"] for m in data.get("models", [])]
                    self.ollama_models = sorted(models)
                    print(f"[Settings] Found {len(models)} models: {', '.join(models[:5])}{'...' if len(models) > 5 else ''}")
                    # Update dropdown on main thread
                    self.after(0, self._update_model_dropdown)
                    self.after(0, lambda: self.connection_status.configure(
                        text=f"✓ Connected ({len(models)} models)",
                        text_color=THEME["success"]
                    ))
                else:
                    print(f"[Settings] Ollama connection failed: HTTP {response.status_code}")
                    self.after(0, self._enable_manual_model_input)
                    self.after(0, lambda: self.connection_status.configure(
                        text="✗ Connection failed - type model name manually",
                        text_color=THEME["error"]
                    ))
            except Exception as e:
                print(f"[Settings] Ollama error: {e}")
                self.after(0, self._enable_manual_model_input)
                self.after(0, lambda: self.connection_status.configure(
                    text=f"✗ {str(e)[:25]} - type manually",
                    text_color=THEME["error"]
                ))

        threading.Thread(target=fetch, daemon=True).start()

    def _enable_manual_model_input(self) -> None:
        """Enable manual model input when Ollama fails."""
        self.llm_model_dropdown.configure(state="normal")
        if self._saved_model:
            self.llm_model_var.set(self._saved_model)
        else:
            self.llm_model_var.set("")

    def _update_model_dropdown(self) -> None:
        """Update the model dropdown with fetched models."""
        if self.ollama_models:
            self.llm_model_dropdown.configure(
                values=self.ollama_models,
                state="normal"  # Enable dropdown after loading
            )
            # Restore saved model if it exists in the list
            if self._saved_model and self._saved_model in self.ollama_models:
                self.llm_model_var.set(self._saved_model)
            elif self.ollama_models:
                # Otherwise select first available model
                self.llm_model_var.set(self.ollama_models[0])

    def _create_widgets(self) -> None:
        """Create settings widgets."""
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=24, pady=(24, 16))

        ctk.CTkLabel(
            header,
            text="Settings",
            font=FONTS["title"],
            text_color=THEME["text_primary"]
        ).pack(anchor="w")

        # Scrollable content
        content = ctk.CTkScrollableFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=24)

        # === LLM Settings (moved to top - most important) ===
        self._add_section(content, "LLM Configuration")

        # Ollama URL with test button
        url_frame = ctk.CTkFrame(content, fg_color="transparent")
        url_frame.pack(fill="x", pady=6)

        ctk.CTkLabel(
            url_frame,
            text="Ollama URL:",
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        ).pack(anchor="w")

        url_row = ctk.CTkFrame(url_frame, fg_color="transparent")
        url_row.pack(fill="x", pady=(4, 0))

        self.ollama_url_var = ctk.StringVar(
            value=self.config.get("ollama_url", "http://localhost:11434")
        )
        ctk.CTkEntry(
            url_row,
            textvariable=self.ollama_url_var,
            font=FONTS["body"],
            fg_color=THEME["bg_light"],
            border_color=THEME["border"],
            height=36,
            width=350
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            url_row,
            text="Test",
            font=FONTS["small"],
            width=70,
            height=36,
            fg_color=THEME["accent_secondary"],
            hover_color="#6EDDD4",
            command=self._fetch_ollama_models
        ).pack(side="right")

        # Connection status
        self.connection_status = ctk.CTkLabel(
            content,
            text="Checking connection...",
            font=FONTS["small"],
            text_color=THEME["text_muted"]
        )
        self.connection_status.pack(anchor="w", pady=(4, 8))

        # Model dropdown (populated from Ollama)
        model_frame = ctk.CTkFrame(content, fg_color="transparent")
        model_frame.pack(fill="x", pady=6)

        ctk.CTkLabel(
            model_frame,
            text="Model:",
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        ).pack(anchor="w")

        # Store the saved model to restore after loading
        self._saved_model = self.config.get("default_model", "")
        self.llm_model_var = ctk.StringVar(value="Loading models...")
        self.llm_model_dropdown = ctk.CTkComboBox(
            model_frame,
            variable=self.llm_model_var,
            values=["Loading models..."],
            font=FONTS["body"],
            fg_color=THEME["bg_light"],
            border_color=THEME["border"],
            button_color=THEME["accent"],
            button_hover_color=THEME["accent_hover"],
            dropdown_fg_color=THEME["bg_medium"],
            height=36,
            state="disabled"  # Disabled until models loaded
        )
        self.llm_model_dropdown.pack(fill="x", pady=(4, 0))

        # System Prompt
        prompt_frame = ctk.CTkFrame(content, fg_color="transparent")
        prompt_frame.pack(fill="x", pady=(16, 6))

        ctk.CTkLabel(
            prompt_frame,
            text="System Prompt:",
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        ).pack(anchor="w")

        default_prompt = self.config.get("system_prompt",
            "You are a text editor assistant. Your job is to clean up and refine transcribed speech. "
            "Output ONLY the refined text with no preamble, explanation, or commentary."
        )

        self.system_prompt_text = ctk.CTkTextbox(
            prompt_frame,
            font=FONTS["mono"],
            fg_color=THEME["bg_light"],
            text_color=THEME["text_primary"],
            border_width=1,
            border_color=THEME["border"],
            corner_radius=8,
            height=120,
            wrap="word"
        )
        self.system_prompt_text.pack(fill="x", pady=(4, 0))
        self.system_prompt_text.insert("1.0", default_prompt)

        # LM Studio URL (collapsed/secondary)
        self._add_section(content, "Alternative Backend (LM Studio)")

        self.lm_studio_url_var = ctk.StringVar(
            value=self.config.get("lm_studio_url", "http://localhost:1234/v1")
        )
        self._add_entry(content, "LM Studio URL:", self.lm_studio_url_var)

        self.llm_backend_var = ctk.StringVar(
            value=self.config.get("default_llm", "ollama")
        )
        self._add_dropdown(
            content,
            "Active Backend:",
            self.llm_backend_var,
            ["ollama", "lm_studio"]
        )

        # === Whisper Settings ===
        self._add_section(content, "Whisper Configuration")

        self.whisper_path_var = ctk.StringVar(
            value=self.config.get("whisper_cpp_path", "")
        )
        self._add_entry(
            content,
            "Whisper Path (leave empty for Python fallback):",
            self.whisper_path_var,
            placeholder="Auto-detect"
        )

        self.whisper_model_var = ctk.StringVar(
            value=self.config.get("whisper_model", "base.en")
        )
        self._add_dropdown(
            content,
            "Whisper Model:",
            self.whisper_model_var,
            ["tiny.en", "base.en", "small.en", "medium.en", "large"]
        )

        # === Controls ===
        self._add_section(content, "Recording Controls")

        # Microphone selection
        mic_frame = ctk.CTkFrame(content, fg_color="transparent")
        mic_frame.pack(fill="x", pady=6)

        ctk.CTkLabel(
            mic_frame,
            text="Microphone:",
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        ).pack(anchor="w")

        mic_row = ctk.CTkFrame(mic_frame, fg_color="transparent")
        mic_row.pack(fill="x", pady=(4, 0))

        # Get available audio devices
        self.audio_devices = AudioRecorder.get_input_devices()
        device_names = ["Default"] + [d["name"] for d in self.audio_devices]

        # Find current device
        current_device_idx = self.config.get("audio_device_index", None)
        current_name = "Default"
        if current_device_idx is not None:
            for d in self.audio_devices:
                if d["index"] == current_device_idx:
                    current_name = d["name"]
                    break

        self.mic_var = ctk.StringVar(value=current_name)
        self.mic_dropdown = ctk.CTkComboBox(
            mic_row,
            variable=self.mic_var,
            values=device_names,
            font=FONTS["body"],
            fg_color=THEME["bg_light"],
            border_color=THEME["border"],
            button_color=THEME["accent"],
            button_hover_color=THEME["accent_hover"],
            dropdown_fg_color=THEME["bg_medium"],
            height=36,
            state="readonly"
        )
        self.mic_dropdown.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            mic_row,
            text="Refresh",
            font=FONTS["small"],
            width=70,
            height=36,
            fg_color=THEME["accent_secondary"],
            hover_color="#6EDDD4",
            command=self._refresh_audio_devices
        ).pack(side="right")

        # Device count label
        self.mic_status = ctk.CTkLabel(
            content,
            text=f"Found {len(self.audio_devices)} input device(s)",
            font=FONTS["small"],
            text_color=THEME["text_muted"]
        )
        self.mic_status.pack(anchor="w", pady=(4, 8))

        self.hotkey_var = ctk.StringVar(
            value=self.config.get("hotkey", "ctrl+shift")
        )
        self._add_entry(
            content,
            "Hold-to-Talk Hotkey:",
            self.hotkey_var,
            placeholder="e.g., ctrl+shift"
        )

        ctk.CTkLabel(
            content,
            text="Tip: Use 'ctrl+shift', 'alt+space', etc. Or just use the record button.",
            font=FONTS["small"],
            text_color=THEME["text_muted"]
        ).pack(anchor="w", pady=(0, 8))

        # === Output ===
        self._add_section(content, "Output")

        # Output directory with Browse button
        output_frame = ctk.CTkFrame(content, fg_color="transparent")
        output_frame.pack(fill="x", pady=6)

        ctk.CTkLabel(
            output_frame,
            text="Output Directory:",
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        ).pack(anchor="w")

        output_row = ctk.CTkFrame(output_frame, fg_color="transparent")
        output_row.pack(fill="x", pady=(4, 0))

        self.output_dir_var = ctk.StringVar(
            value=self.config.get("output_dir", "./outputs")
        )
        ctk.CTkEntry(
            output_row,
            textvariable=self.output_dir_var,
            font=FONTS["body"],
            fg_color=THEME["bg_light"],
            border_color=THEME["border"],
            height=36
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            output_row,
            text="Browse",
            font=FONTS["small"],
            width=70,
            height=36,
            fg_color=THEME["accent_secondary"],
            hover_color="#6EDDD4",
            command=self._browse_output_dir
        ).pack(side="right")

        # === Buttons ===
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=24)

        ctk.CTkButton(
            buttons,
            text="Cancel",
            font=FONTS["body"],
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            hover_color=THEME["bg_light"],
            command=self.destroy
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            buttons,
            text="Save",
            font=FONTS["body"],
            fg_color=THEME["accent"],
            hover_color=THEME["accent_hover"],
            command=self._save
        ).pack(side="right")

        ctk.CTkButton(
            buttons,
            text="Reset Defaults",
            font=FONTS["body"],
            fg_color="transparent",
            border_width=1,
            border_color=THEME["border"],
            hover_color=THEME["bg_light"],
            command=self._reset_defaults
        ).pack(side="left")

    def _refresh_audio_devices(self) -> None:
        """Refresh the list of audio devices."""
        self.audio_devices = AudioRecorder.get_input_devices()
        device_names = ["Default"] + [d["name"] for d in self.audio_devices]
        self.mic_dropdown.configure(values=device_names)
        self.mic_status.configure(text=f"Found {len(self.audio_devices)} input device(s)")

    def _browse_output_dir(self) -> None:
        """Open directory browser for output directory selection."""
        current = self.output_dir_var.get() or "./outputs"
        path = filedialog.askdirectory(
            initialdir=current,
            title="Select Output Directory"
        )
        if path:
            self.output_dir_var.set(path)

    def _add_section(self, parent, title: str) -> None:
        """Add section header."""
        ctk.CTkLabel(
            parent,
            text=title,
            font=FONTS["heading"],
            text_color=THEME["text_primary"]
        ).pack(anchor="w", pady=(24, 12))

    def _add_entry(
        self,
        parent,
        label: str,
        variable: ctk.StringVar,
        placeholder: str = ""
    ) -> None:
        """Add labeled entry field."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=6)

        ctk.CTkLabel(
            frame,
            text=label,
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        ).pack(anchor="w")

        ctk.CTkEntry(
            frame,
            textvariable=variable,
            font=FONTS["body"],
            fg_color=THEME["bg_light"],
            border_color=THEME["border"],
            placeholder_text=placeholder,
            height=36
        ).pack(fill="x", pady=(4, 0))

    def _add_dropdown(
        self,
        parent,
        label: str,
        variable: ctk.StringVar,
        values: list
    ) -> None:
        """Add labeled dropdown."""
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.pack(fill="x", pady=6)

        ctk.CTkLabel(
            frame,
            text=label,
            font=FONTS["body"],
            text_color=THEME["text_secondary"]
        ).pack(anchor="w")

        ctk.CTkComboBox(
            frame,
            variable=variable,
            values=values,
            font=FONTS["body"],
            fg_color=THEME["bg_light"],
            border_color=THEME["border"],
            button_color=THEME["accent"],
            button_hover_color=THEME["accent_hover"],
            dropdown_fg_color=THEME["bg_medium"],
            height=36
        ).pack(fill="x", pady=(4, 0))

    def _save(self) -> None:
        """Save settings."""
        self.config["whisper_cpp_path"] = self.whisper_path_var.get()
        self.config["whisper_model"] = self.whisper_model_var.get()
        self.config["default_llm"] = self.llm_backend_var.get()
        self.config["default_model"] = self.llm_model_var.get()
        self.config["ollama_url"] = self.ollama_url_var.get()
        self.config["lm_studio_url"] = self.lm_studio_url_var.get()
        self.config["hotkey"] = self.hotkey_var.get()
        self.config["output_dir"] = self.output_dir_var.get()
        self.config["system_prompt"] = self.system_prompt_text.get("1.0", "end-1c")

        # Save audio device
        mic_name = self.mic_var.get()
        if mic_name == "Default":
            self.config["audio_device_index"] = None
        else:
            for d in self.audio_devices:
                if d["name"] == mic_name:
                    self.config["audio_device_index"] = d["index"]
                    break

        if self.on_save:
            self.on_save(self.config)

        self.destroy()

    def _reset_defaults(self) -> None:
        """Reset all settings to defaults."""
        self.whisper_path_var.set("")
        self.whisper_model_var.set("base.en")
        self.llm_backend_var.set("ollama")
        self.llm_model_var.set("llama3.1:8b")
        self.ollama_url_var.set("http://localhost:11434")
        self.lm_studio_url_var.set("http://localhost:1234/v1")
        self.hotkey_var.set("ctrl+shift")
        self.output_dir_var.set("./outputs")
        self.mic_var.set("Default")
        self.system_prompt_text.delete("1.0", "end")
        self.system_prompt_text.insert("1.0",
            "You are a text editor assistant. Your job is to clean up and refine transcribed speech. "
            "Output ONLY the refined text with no preamble, explanation, or commentary."
        )
