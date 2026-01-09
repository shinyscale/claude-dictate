#!/usr/bin/env python3
"""
Claude Dictate - Voice-to-Text Tool for Claude Code
Main entry point with CLI and hotkey support using pynput.
"""

import argparse
import os
import sys
import threading
from typing import Optional, Callable, Set

from pynput import keyboard

from .audio import AudioRecorder
from .transcriber import WhisperTranscriber
from .refiner import LLMRefiner
from .exporter import OutputGenerator
from .config import AppConfig, DEFAULT_CONFIG
import pyperclip


class HotkeyListener:
    """
    Cross-platform hotkey listener using pynput.
    Implements hold-to-talk functionality.
    """

    # Key name mappings for pynput
    KEY_MAP = {
        "ctrl": {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r},
        "shift": {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r},
        "alt": {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r},
        "cmd": {keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r},
        "space": {keyboard.Key.space},
        "enter": {keyboard.Key.enter},
        "tab": {keyboard.Key.tab},
    }

    def __init__(
        self,
        hotkey_combo: str,
        on_activate: Callable[[], None],
        on_deactivate: Callable[[], None]
    ):
        """
        Initialize the hotkey listener.

        Args:
            hotkey_combo: Hotkey combination string (e.g., "ctrl+shift")
            on_activate: Callback when hotkey is pressed
            on_deactivate: Callback when hotkey is released
        """
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate
        self.keys_pressed: Set = set()
        self.hotkey_keys = self._parse_hotkey(hotkey_combo)
        self.is_active = False
        self.listener: Optional[keyboard.Listener] = None

    def _parse_hotkey(self, combo: str) -> Set:
        """
        Parse hotkey string into set of pynput keys.

        Args:
            combo: Hotkey string like "ctrl+shift"

        Returns:
            Set of key identifiers
        """
        keys = set()
        parts = combo.lower().replace(" ", "").split("+")

        for part in parts:
            if part in self.KEY_MAP:
                # Add the first key from the set as the canonical key
                keys.add(part)
            else:
                # Assume it's a character key
                keys.add(part)

        return keys

    def _normalize_key(self, key) -> Optional[str]:
        """
        Normalize a pynput key to a string identifier.

        Args:
            key: pynput key object

        Returns:
            Normalized key string
        """
        # Check special keys
        for name, key_set in self.KEY_MAP.items():
            if key in key_set:
                return name

        # Check character keys
        try:
            if hasattr(key, 'char') and key.char:
                return key.char.lower()
        except AttributeError:
            pass

        return None

    def _handle_press(self, key) -> None:
        """Handle key press event."""
        normalized = self._normalize_key(key)
        if normalized:
            self.keys_pressed.add(normalized)

            # Check if all hotkey keys are pressed
            if self.hotkey_keys.issubset(self.keys_pressed) and not self.is_active:
                self.is_active = True
                self.on_activate()

    def _handle_release(self, key) -> None:
        """Handle key release event."""
        normalized = self._normalize_key(key)
        if normalized:
            # If hotkey was active and a required key is released, deactivate
            if self.is_active and normalized in self.hotkey_keys:
                self.is_active = False
                self.on_deactivate()

            self.keys_pressed.discard(normalized)

    def start(self) -> None:
        """Start listening for hotkeys."""
        self.listener = keyboard.Listener(
            on_press=self._handle_press,
            on_release=self._handle_release
        )
        self.listener.start()

    def stop(self) -> None:
        """Stop listening for hotkeys."""
        if self.listener:
            self.listener.stop()
            self.listener = None
        self.is_active = False
        self.keys_pressed.clear()

    def join(self) -> None:
        """Wait for listener to finish."""
        if self.listener:
            self.listener.join()


class ClaudeDictate:
    """Main application class coordinating all components."""

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize Claude Dictate.

        Args:
            config: Configuration dictionary (uses defaults if None)
        """
        self.config = config or DEFAULT_CONFIG.copy()

        # Initialize components
        self.recorder = AudioRecorder(
            sample_rate=self.config.get("sample_rate", 16000),
            channels=self.config.get("channels", 1),
            chunk_size=self.config.get("chunk_size", 1024),
            device_index=self.config.get("audio_device_index", None)
        )
        self.transcriber = WhisperTranscriber(
            whisper_path=self.config.get("whisper_cpp_path", ""),
            model=self.config.get("whisper_model", "base.en")
        )
        llm_backend = self.config.get("default_llm", "ollama")
        self.refiner = LLMRefiner(
            backend=llm_backend,
            model=self.config.get("default_model", "llama3.2"),
            base_url=self.config.get("ollama_url" if llm_backend == "ollama" else "lm_studio_url", ""),
            system_prompt=self.config.get("system_prompt", "")
        )
        self.output_gen = OutputGenerator(
            output_dir=self.config.get("output_dir", "./outputs")
        )

        # State
        self.current_transcription = ""
        self.current_refined = ""
        self.is_running = False
        self.hotkey_listener: Optional[HotkeyListener] = None

        # Callbacks for UI updates
        self.on_recording_start: Optional[Callable] = None
        self.on_recording_stop: Optional[Callable] = None
        self.on_transcription_complete: Optional[Callable[[str], None]] = None
        self.on_refinement_complete: Optional[Callable[[str], None]] = None
        self.on_status_update: Optional[Callable[[str], None]] = None

    def start_recording(self) -> None:
        """Start audio recording."""
        if self.on_status_update:
            self.on_status_update("Recording...")
        if self.on_recording_start:
            self.on_recording_start()
        self.recorder.start_recording()

    def stop_recording(self) -> str:
        """Stop recording and transcribe."""
        if self.on_status_update:
            self.on_status_update("Processing...")
        if self.on_recording_stop:
            self.on_recording_stop()

        audio_path = self.recorder.stop_recording()

        if not audio_path:
            if self.on_status_update:
                self.on_status_update("No audio recorded")
            return ""

        # Transcribe
        if self.on_status_update:
            self.on_status_update("Transcribing...")

        self.current_transcription = self.transcriber.transcribe(audio_path)

        # Clean up temp file
        try:
            os.unlink(audio_path)
        except:
            pass

        if self.on_transcription_complete:
            self.on_transcription_complete(self.current_transcription)

        if self.on_status_update:
            self.on_status_update("Ready")

        return self.current_transcription

    def refine_text(self, text: Optional[str] = None, style: str = "clean") -> str:
        """
        Refine text using LLM.

        Args:
            text: Text to refine (uses current transcription if None)
            style: Refinement style

        Returns:
            Refined text
        """
        text = text or self.current_transcription
        print(f"[main.py] refine_text called: style='{style}', text_len={len(text) if text else 0}")

        if not text:
            print("[main.py] refine_text: No text provided, returning empty")
            return ""

        if self.on_status_update:
            self.on_status_update("Refining with LLM...")

        print(f"[main.py] Calling refiner.refine() with {len(text)} chars...")
        self.current_refined = self.refiner.refine(text, style)
        print(f"[main.py] refiner.refine() returned: {len(self.current_refined) if self.current_refined else 0} chars")

        if self.on_refinement_complete:
            print(f"[main.py] Triggering on_refinement_complete callback")
            self.on_refinement_complete(self.current_refined)
        else:
            print(f"[main.py] WARNING: on_refinement_complete callback is None!")

        if self.on_status_update:
            self.on_status_update("Ready")

        return self.current_refined

    def copy_to_clipboard(self, text: Optional[str] = None) -> None:
        """Copy text to clipboard."""
        text = text or self.current_refined or self.current_transcription
        if text:
            pyperclip.copy(text)
            if self.on_status_update:
                self.on_status_update("Copied to clipboard!")

    def save_as_markdown(self, text: Optional[str] = None, title: str = "") -> str:
        """Save as markdown file."""
        text = text or self.current_refined or self.current_transcription
        if text:
            path = self.output_gen.save_markdown(text, title)
            if self.on_status_update:
                self.on_status_update(f"Saved: {path}")
            return path
        return ""

    def save_as_prd(self, text: Optional[str] = None, title: str = "") -> str:
        """Save as PRD file."""
        text = text or self.current_refined or self.current_transcription
        if text:
            path = self.output_gen.save_prd(text, title)
            if self.on_status_update:
                self.on_status_update(f"Saved: {path}")
            return path
        return ""

    def save_as_prompt(self, text: Optional[str] = None, title: str = "") -> str:
        """Save as prompt file for Claude Code."""
        text = text or self.current_refined or self.current_transcription
        if text:
            path = self.output_gen.save_prompt(text, title)
            if self.on_status_update:
                self.on_status_update(f"Saved: {path}")
            return path
        return ""

    def setup_hotkey(self, hotkey: Optional[str] = None) -> None:
        """
        Setup the push-to-talk hotkey using pynput.

        Args:
            hotkey: Hotkey combination (e.g., "ctrl+shift")
        """
        hotkey = hotkey or self.config.get("hotkey", "ctrl+shift")

        # Stop existing listener
        if self.hotkey_listener:
            self.hotkey_listener.stop()

        self.hotkey_listener = HotkeyListener(
            hotkey_combo=hotkey,
            on_activate=self.start_recording,
            on_deactivate=self.stop_recording
        )
        self.hotkey_listener.start()

    def cleanup(self) -> None:
        """Clean up resources."""
        self.recorder.cleanup()
        if self.hotkey_listener:
            self.hotkey_listener.stop()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Claude Dictate - Voice-to-Text for Claude Code"
    )
    parser.add_argument("--gui", action="store_true", help="Launch GUI mode")
    parser.add_argument("--record", action="store_true", help="Record and transcribe once")
    parser.add_argument("--refine", type=str, help="Refine text from file or stdin")
    parser.add_argument(
        "--style",
        type=str,
        default="clean",
        choices=["clean", "professional", "technical", "casual", "minimal",
                 "expand", "summarize", "bullets", "prd", "prompt"],
        help="Refinement style"
    )
    parser.add_argument(
        "--output",
        type=str,
        choices=["md", "prd", "prompt", "ralph", "clipboard"],
        default="clipboard",
        help="Output format"
    )
    parser.add_argument(
        "--llm",
        type=str,
        choices=["ollama", "lm_studio"],
        default="ollama",
        help="LLM backend"
    )
    parser.add_argument("--model", type=str, default="llama3.2", help="LLM model name")

    args = parser.parse_args()

    if args.gui:
        # Import and run GUI
        from .gui import run_gui
        run_gui()
    elif args.record:
        # Single recording mode
        app = ClaudeDictate()
        print("Press Enter to start recording, Enter again to stop...")
        input()
        app.start_recording()
        print("Recording... Press Enter to stop")
        input()
        text = app.stop_recording()
        print(f"\nTranscription:\n{text}")

        if text and args.style != "clean":
            print(f"\nRefining with style '{args.style}'...")
            refined = app.refine_text(text, args.style)
            print(f"\nRefined:\n{refined}")
            text = refined or text

        if args.output == "clipboard":
            app.copy_to_clipboard(text)
            print("\nCopied to clipboard!")
        elif args.output == "md":
            path = app.save_as_markdown(text)
            print(f"\nSaved to: {path}")
        elif args.output == "prd":
            path = app.save_as_prd(text)
            print(f"\nSaved to: {path}")
        elif args.output == "prompt":
            path = app.save_as_prompt(text)
            print(f"\nSaved to: {path}")
        elif args.output == "ralph":
            path = app.output_gen.save_ralph_prompt(text)
            print(f"\nSaved to: {path}")

        app.cleanup()
    elif args.refine:
        # Refine text from file
        app = ClaudeDictate()

        if args.refine == "-":
            text = sys.stdin.read()
        else:
            with open(args.refine, 'r', encoding='utf-8') as f:
                text = f.read()

        print(f"Refining with style '{args.style}'...")
        refined = app.refine_text(text, args.style)
        print(refined)

        app.cleanup()
    else:
        # Default: launch GUI
        try:
            from .gui import run_gui
            run_gui()
        except ImportError as e:
            print(f"GUI dependencies not found: {e}")
            print("Run with --record for CLI mode.")
            print("Install GUI dependencies: pip install customtkinter")


if __name__ == "__main__":
    main()
