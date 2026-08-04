"""
Whisper transcription module for Claude Dictate.

Backend priority:
  1. faster-whisper on CUDA  -- CTranslate2 kernels, ~30x realtime on the RTX PRO 6000
  2. whisper.cpp executable   -- if one is configured/on PATH
  3. openai-whisper (Python)  -- last-resort CPU fallback

The faster-whisper model is cached at module level so a long-lived process
(tray daemon) pays the load cost once and every subsequent hotkey press hits a
model that is already resident in VRAM.
"""

import os
import subprocess
import shutil
import threading
from pathlib import Path
from typing import Optional, Callable

# faster-whisper accepts its own model ids; translate the legacy names the
# config/UI still hand us so old settings files keep working.
_MODEL_ALIASES = {
    "large": "large-v3",
    "large.en": "large-v3",
    "turbo": "large-v3-turbo",
}

DEFAULT_FW_MODEL = "large-v3-turbo"

# (model, device, compute_type) -> WhisperModel. Guarded because the tray
# daemon may transcribe from a worker thread while the UI thread preloads.
_model_cache = {}
_model_lock = threading.Lock()


def _load_faster_whisper(model: str, device: str, compute_type: str):
    """Get (or build) a cached faster-whisper model. Raises if unavailable."""
    key = (model, device, compute_type)
    with _model_lock:
        if key not in _model_cache:
            from faster_whisper import WhisperModel
            _model_cache[key] = WhisperModel(
                model, device=device, compute_type=compute_type
            )
        return _model_cache[key]


def cuda_available() -> bool:
    """True if CTranslate2 can see a usable CUDA device."""
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class WhisperTranscriber:
    """Handles transcription, preferring GPU faster-whisper."""

    def __init__(
        self,
        whisper_path: str = "",
        model: str = "base.en",
        language: str = "en",
        on_progress: Optional[Callable[[float, str], None]] = None,
        device: str = "auto",
        compute_type: str = "float16",
    ):
        """
        Args:
            whisper_path: Path to a whisper.cpp executable (auto-detected if empty)
            model: Whisper model id (base.en, small.en, large-v3, large-v3-turbo, ...)
            language: Language code for transcription
            on_progress: Callback (progress 0-1, status message)
            device: "auto" | "cuda" | "cpu" for the faster-whisper backend
            compute_type: CTranslate2 compute type (float16 on CUDA, int8 on CPU)
        """
        self.whisper_path = whisper_path or self._find_whisper()
        self.model = model
        self.language = language
        self.model_path = self._get_model_path()
        self.on_progress = on_progress

        if device == "auto":
            device = "cuda" if cuda_available() else "cpu"
        self.device = device
        self.compute_type = compute_type if device == "cuda" else "int8"

    # -- backend selection -------------------------------------------------

    @property
    def fw_model_name(self) -> str:
        """The model id to hand faster-whisper."""
        return _MODEL_ALIASES.get(self.model, self.model)

    def preload(self) -> bool:
        """
        Warm the GPU model so the first dictation isn't stuck behind a load.

        Safe to call from a background thread at startup. Returns True if a
        faster-whisper model is resident afterwards.
        """
        try:
            _load_faster_whisper(self.fw_model_name, self.device, self.compute_type)
            return True
        except Exception as e:
            print(f"faster-whisper preload failed: {e}")
            return False

    # -- transcription -----------------------------------------------------

    def transcribe(self, audio_path: str) -> str:
        """Transcribe an audio file, returning the text."""
        if self.on_progress:
            self.on_progress(0.0, "Starting transcription...")

        text = self._transcribe_faster_whisper(audio_path)
        if text is not None:
            return text

        if not self.whisper_path:
            if self.on_progress:
                self.on_progress(0.1, "Using Python whisper fallback...")
            return self._transcribe_fallback(audio_path)

        return self._transcribe_whisper_cpp(audio_path)

    def _transcribe_faster_whisper(self, audio_path: str) -> Optional[str]:
        """
        Primary path: CTranslate2. Returns None (not "") on backend failure so
        the caller can tell "backend unavailable" from "you said nothing".
        """
        try:
            if self.on_progress:
                self.on_progress(0.2, f"Transcribing on {self.device.upper()}...")

            model = _load_faster_whisper(
                self.fw_model_name, self.device, self.compute_type
            )
            segments, _info = model.transcribe(
                audio_path,
                language=self.language,
                beam_size=1,
                # Hold-to-talk clips are bookended by dead air from the key
                # press/release; VAD trims it and stops Whisper hallucinating
                # filler into the silence.
                vad_filter=True,
            )
            text = " ".join(s.text for s in segments).strip()

            if self.on_progress:
                self.on_progress(1.0, "Transcription complete")
            return text

        except Exception as e:
            print(f"faster-whisper unavailable ({e}); falling back")
            return None

    def _transcribe_whisper_cpp(self, audio_path: str) -> str:
        """Shell out to a whisper.cpp binary."""
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

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

            if self.on_progress:
                self.on_progress(0.8, "Processing output...")

            if result.returncode == 0:
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
        """Last resort: openai-whisper. CPU only -- torch here is a cu124 build
        with no sm_120 kernels, so CUDA would fault on the RTX PRO 6000."""
        try:
            import whisper

            if self.on_progress:
                self.on_progress(0.3, "Loading whisper model...")

            model_name = self.model.replace(".en", "")
            model = whisper.load_model(model_name, device="cpu")

            if self.on_progress:
                self.on_progress(0.5, "Transcribing with Python whisper...")

            result = model.transcribe(audio_path, language=self.language)

            if self.on_progress:
                self.on_progress(1.0, "Transcription complete")

            return result["text"].strip()

        except ImportError:
            print("No whisper backend found. Run: pip install faster-whisper")
            if self.on_progress:
                self.on_progress(1.0, "No whisper backend available")
            return ""
        except Exception as e:
            print(f"Fallback transcription error: {e}")
            if self.on_progress:
                self.on_progress(1.0, f"Transcription error: {e}")
            return ""

    # -- discovery ---------------------------------------------------------

    def _find_whisper(self) -> str:
        """Try to find a whisper.cpp executable."""
        for name in ["whisper", "whisper-cli", "main", "whisper-cpp"]:
            found = shutil.which(name)
            if found:
                return found

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
        """Path to a ggml model for the whisper.cpp backend."""
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

        return model_filename

    def is_available(self) -> bool:
        """Check if any transcription backend is available."""
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            pass

        if self.whisper_path and os.path.isfile(self.model_path):
            return True

        try:
            import whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def get_available_models(self) -> list:
        """Models offered in the UI, fastest to most accurate."""
        return [
            "tiny.en", "base.en", "small.en", "medium.en",
            "distil-large-v3", "large-v3-turbo", "large-v3",
        ]
