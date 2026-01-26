"""
Whisper transcription module for Claude Dictate
Handles speech-to-text using whisper.cpp or Python whisper fallback.
"""

import os
import subprocess
import shutil
from pathlib import Path
from typing import Optional, Callable


class WhisperTranscriber:
    """Handles transcription using whisper.cpp."""

    def __init__(
        self,
        whisper_path: str = "",
        model: str = "base.en",
        language: str = "en",
        on_progress: Optional[Callable[[float, str], None]] = None
    ):
        """
        Initialize the Whisper transcriber.

        Args:
            whisper_path: Path to whisper.cpp executable (auto-detected if empty)
            model: Whisper model name (tiny.en, base.en, small.en, medium.en, large)
            language: Language code for transcription
            on_progress: Callback for progress updates (progress 0-1, status message)
        """
        self.whisper_path = whisper_path or self._find_whisper()
        self.model = model
        self.language = language
        self.model_path = self._get_model_path()
        self.on_progress = on_progress

    def _find_whisper(self) -> str:
        """Try to find whisper.cpp executable."""
        # Common executable names
        names = ["whisper", "main", "whisper-cpp"]

        # Check PATH first
        for name in names:
            found = shutil.which(name)
            if found:
                return found

        # Common installation paths
        possible_paths = [
            Path.home() / "whisper.cpp" / "main",
            Path.home() / "whisper.cpp" / "build" / "bin" / "main",
            Path.home() / ".local" / "bin" / "whisper",
            Path("/usr/local/bin/whisper"),
            Path("/usr/bin/whisper"),
            Path("./whisper"),
        ]

        for path in possible_paths:
            if path.exists() and os.access(path, os.X_OK):
                return str(path)

        return ""

    def _get_model_path(self) -> str:
        """Get the path to the whisper model."""
        model_dirs = [
            Path.home() / ".cache" / "whisper",
            Path.home() / "whisper.cpp" / "models",
            Path("./models"),
            Path("/usr/share/whisper/models"),
        ]

        model_filename = f"ggml-{self.model}.bin"

        for dir_path in model_dirs:
            model_path = dir_path / model_filename
            if model_path.exists():
                return str(model_path)

        # Return filename - will need to be downloaded
        return model_filename

    def transcribe(self, audio_path: str) -> str:
        """
        Transcribe audio file using whisper.cpp.

        Args:
            audio_path: Path to the audio file (WAV format)

        Returns:
            Transcribed text
        """
        if self.on_progress:
            self.on_progress(0.0, "Starting transcription...")

        if not self.whisper_path:
            if self.on_progress:
                self.on_progress(0.1, "Using Python whisper fallback...")
            return self._transcribe_fallback(audio_path)

        try:
            if self.on_progress:
                self.on_progress(0.2, "Running whisper.cpp...")

            cmd = [
                self.whisper_path,
                "-m", self.model_path,
                "-f", audio_path,
                "-otxt",
                "--no-timestamps",
                "-l", self.language,
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if self.on_progress:
                self.on_progress(0.8, "Processing output...")

            if result.returncode == 0:
                # Read the output text file
                txt_path = audio_path + ".txt"
                if os.path.isfile(txt_path):
                    with open(txt_path, 'r', encoding='utf-8') as f:
                        text = f.read().strip()
                    os.unlink(txt_path)

                    if self.on_progress:
                        self.on_progress(1.0, "Transcription complete")
                    return text

                if self.on_progress:
                    self.on_progress(1.0, "Transcription complete")
                return result.stdout.strip()
            else:
                print(f"Whisper error: {result.stderr}")
                return self._transcribe_fallback(audio_path)

        except subprocess.TimeoutExpired:
            print("Transcription timed out")
            if self.on_progress:
                self.on_progress(1.0, "Transcription timed out")
            return ""
        except Exception as e:
            print(f"Transcription error: {e}")
            return self._transcribe_fallback(audio_path)

    def _transcribe_fallback(self, audio_path: str) -> str:
        """Fallback transcription using openai-whisper Python package."""
        try:
            import whisper

            if self.on_progress:
                self.on_progress(0.3, "Loading whisper model...")

            model_name = self.model.replace(".en", "")
            # Force CPU - Blackwell GPUs (sm_120) not yet supported by PyTorch
            model = whisper.load_model(model_name, device="cpu")

            if self.on_progress:
                self.on_progress(0.5, "Transcribing with Python whisper...")

            result = model.transcribe(audio_path, language=self.language)

            if self.on_progress:
                self.on_progress(1.0, "Transcription complete")

            return result["text"].strip()

        except ImportError:
            print("Neither whisper.cpp nor openai-whisper found.")
            print("Install whisper.cpp or run: pip install openai-whisper")
            if self.on_progress:
                self.on_progress(1.0, "No whisper backend available")
            return ""
        except Exception as e:
            print(f"Fallback transcription error: {e}")
            if self.on_progress:
                self.on_progress(1.0, f"Transcription error: {e}")
            return ""

    def is_available(self) -> bool:
        """Check if whisper transcription is available."""
        if self.whisper_path and os.path.isfile(self.model_path):
            return True

        # Check for Python whisper fallback
        try:
            import whisper
            return True
        except ImportError:
            return False

    def get_available_models(self) -> list:
        """Get list of available models."""
        return ["tiny.en", "base.en", "small.en", "medium.en", "large"]
