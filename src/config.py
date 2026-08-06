"""
Configuration management for Claude Dictate
Handles loading, saving, and validating configuration.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
import shutil


# Terms Whisper has no reason to know but that show up constantly in this
# user's dictation. Fed to the decoder as an initial_prompt, which biases the
# language model toward these spellings instead of phonetic guesses.
# Keep it short -- Whisper only conditions on the last 224 prompt tokens.
DEFAULT_VOCABULARY = [
    "strixhalo", "sandpipe", "bodypipe", "facepipe", "sandpipe-body",
    "GVHMR", "SMPL-X", "mocap", "Spark f235", "spark-987a", "powerhouse",
    "Deck Nine", "ACX", "Scripty", "DeepSeek", "Qwen", "LM Studio",
    "vLLM", "Tailscale", "Home Assistant", "Claude", "Anthropic",
    "faster-whisper", "CTranslate2", "Cloudflare Pages",
]

# Deterministic fix-ups applied after decoding, for words Whisper reliably
# mangles even with the prompt bias. Keys are matched case-insensitively on
# word boundaries; values are pasted verbatim.
DEFAULT_CORRECTIONS = {
    "sticks halo": "strixhalo",
    "strix halo": "strixhalo",
    "sand pipe": "sandpipe",
    "body pipe": "bodypipe",
    "face pipe": "facepipe",
    "deck 9": "Deck Nine",
    "scripty": "Scripty",
    "f 235": "f235",
    "deep seek": "DeepSeek",
    "lm studio": "LM Studio",
    "tail scale": "Tailscale",
}


# Default configuration dict (for backwards compatibility)
DEFAULT_CONFIG = {
    "whisper_cpp_path": "",
    "whisper_model": "large-v3-turbo",
    # copies: DEFAULT_CONFIG.copy() is shallow, so callers must not be handed
    # aliases of the module-level defaults
    "vocabulary_terms": list(DEFAULT_VOCABULARY),
    "vocabulary_corrections": dict(DEFAULT_CORRECTIONS),
    "sample_rate": 16000,
    "channels": 1,
    "chunk_size": 1024,
    "audio_device_index": None,
    "hotkey": "ctrl+shift",
    "clear_hotkey": "ctrl+alt+x",
    "ollama_url": "http://localhost:11434",
    "lm_studio_url": "http://localhost:1234/v1",
    "f235_url": "http://spark-f235:8000/v1",
    "default_llm": "f235",
    "default_model": "deepseek-ai/DeepSeek-V4-Flash-0731",
    "system_prompt": "",
    "output_dir": "./outputs",
    "paste_mode": "raw",
    "verify_window": True,
    "continuation_join": True,
    "minimize_to_tray": False,
    "audio_cues": False,
    # Window geometry (None means use defaults)
    "window_width": None,
    "window_height": None,
    "window_x": None,
    "window_y": None,
}


@dataclass
class WhisperConfig:
    """Whisper transcription configuration."""
    executable_path: str = ""
    model: str = "large-v3-turbo"
    language: str = "en"


@dataclass
class VocabularyConfig:
    """Personal vocabulary: decoder bias plus post-decode corrections."""
    terms: List[str] = field(default_factory=lambda: list(DEFAULT_VOCABULARY))
    corrections: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CORRECTIONS))


@dataclass
class AudioConfig:
    """Audio recording configuration."""
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    device_index: Optional[int] = None


@dataclass
class LLMConfig:
    """LLM refinement configuration."""
    backend: str = "f235"  # ollama, lm_studio, f235, or auto (probe engines)
    model: str = "deepseek-ai/DeepSeek-V4-Flash-0731"  # or "auto" = whatever is loaded
    ollama_url: str = "http://localhost:11434"
    lm_studio_url: str = "http://localhost:1234/v1"
    f235_url: str = "http://spark-f235:8000/v1"
    temperature: float = 0.3
    max_tokens: int = 2048
    system_prompt: str = ""


@dataclass
class HotkeyConfig:
    """Hotkey configuration."""
    record_hotkey: str = "ctrl+shift"
    clear_hotkey: str = "ctrl+alt+x"


@dataclass
class OutputConfig:
    """Output configuration."""
    output_dir: str = "./outputs"
    default_format: str = "clipboard"  # clipboard, md, prd, prompt
    # Daemon paste behavior. "raw" pastes the transcription as-is (whisper
    # output is already punctuated and clean); "refined" runs the LLM pass
    # first. Raw is the default: it's instant and can't hallucinate.
    paste_mode: str = "raw"  # raw | refined
    # Only auto-paste if the window focused when the hotkey was released is
    # still focused when processing finishes; otherwise leave on clipboard.
    verify_window: bool = True
    # When the next dictation lands in the same window with no typing or
    # clicking in between, repair the seam between the two pastes: exactly
    # one space, drop a stray Whisper period after a dangling function word,
    # lowercase the next chunk's leading capital when resuming mid-sentence.
    continuation_join: bool = True


@dataclass
class WindowConfig:
    """Window geometry configuration."""
    width: Optional[int] = None
    height: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None


@dataclass
class SystemConfig:
    """System behavior configuration."""
    minimize_to_tray: bool = False
    # Short tones from the tray daemon (recording started, pasted, held,
    # error). Off by default -- Zach found the beeps intrusive; the code
    # stays for anyone who wants outcome sounds in full-screen apps.
    audio_cues: bool = False


@dataclass
class AppConfig:
    """Main application configuration."""
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    vocabulary: VocabularyConfig = field(default_factory=VocabularyConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    hotkey: HotkeyConfig = field(default_factory=HotkeyConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    system: SystemConfig = field(default_factory=SystemConfig)

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the configuration file path."""
        # Check for local config first
        local_config = Path("config.json")
        if local_config.exists():
            return local_config

        # Then check user config directory
        if os.name == "nt":  # Windows
            config_dir = Path(os.environ.get("APPDATA", "")) / "ClaudeDictate"
        else:  # macOS/Linux
            config_dir = Path.home() / ".config" / "claude-dictate"

        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "config.json"

    @classmethod
    def load(cls) -> "AppConfig":
        """Load configuration from file."""
        config_path = cls.get_config_path()

        if config_path.exists():
            try:
                # utf-8-sig: tolerate a BOM from Notepad/PowerShell edits, which
                # plain utf-8 rejects — and a parse failure here silently
                # reverts every setting to defaults.
                with open(config_path, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                return cls.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not load config: {e}")

        return cls()

    def save(self) -> None:
        """Save configuration to file."""
        config_path = self.get_config_path()

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "whisper": asdict(self.whisper),
            "vocabulary": asdict(self.vocabulary),
            "audio": asdict(self.audio),
            "llm": asdict(self.llm),
            "hotkey": asdict(self.hotkey),
            "output": asdict(self.output),
            "window": asdict(self.window),
            "system": asdict(self.system),
        }

    def to_flat_dict(self) -> dict:
        """Convert to flat dictionary for backwards compatibility."""
        return {
            "whisper_cpp_path": self.whisper.executable_path,
            "whisper_model": self.whisper.model,
            "vocabulary_terms": self.vocabulary.terms,
            "vocabulary_corrections": self.vocabulary.corrections,
            "sample_rate": self.audio.sample_rate,
            "channels": self.audio.channels,
            "chunk_size": self.audio.chunk_size,
            "audio_device_index": self.audio.device_index,
            "hotkey": self.hotkey.record_hotkey,
            "clear_hotkey": self.hotkey.clear_hotkey,
            "ollama_url": self.llm.ollama_url,
            "lm_studio_url": self.llm.lm_studio_url,
            "f235_url": self.llm.f235_url,
            "default_llm": self.llm.backend,
            "default_model": self.llm.model,
            "system_prompt": self.llm.system_prompt,
            "output_dir": self.output.output_dir,
            "paste_mode": self.output.paste_mode,
            "verify_window": self.output.verify_window,
            "continuation_join": self.output.continuation_join,
            "minimize_to_tray": self.system.minimize_to_tray,
            "audio_cues": self.system.audio_cues,
            "window_width": self.window.width,
            "window_height": self.window.height,
            "window_x": self.window.x,
            "window_y": self.window.y,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """Create from dictionary."""
        # Handle both nested and flat config formats
        if "whisper" in data:
            # Nested format
            window_data = data.get("window", {})
            system_data = data.get("system", {})
            return cls(
                whisper=WhisperConfig(**data.get("whisper", {})),
                vocabulary=VocabularyConfig(**data.get("vocabulary", {})),
                audio=AudioConfig(**data.get("audio", {})),
                llm=LLMConfig(**data.get("llm", {})),
                hotkey=HotkeyConfig(**data.get("hotkey", {})),
                output=OutputConfig(**data.get("output", {})),
                window=WindowConfig(**window_data) if window_data else WindowConfig(),
                system=SystemConfig(**system_data) if system_data else SystemConfig(),
            )
        else:
            # Flat format (backwards compatibility)
            return cls(
                whisper=WhisperConfig(
                    executable_path=data.get("whisper_cpp_path", ""),
                    model=data.get("whisper_model", "base.en"),
                ),
                vocabulary=VocabularyConfig(
                    terms=data.get("vocabulary_terms", list(DEFAULT_VOCABULARY)),
                    corrections=data.get(
                        "vocabulary_corrections", dict(DEFAULT_CORRECTIONS)
                    ),
                ),
                audio=AudioConfig(
                    sample_rate=data.get("sample_rate", 16000),
                    channels=data.get("channels", 1),
                    chunk_size=data.get("chunk_size", 1024),
                    device_index=data.get("audio_device_index"),
                ),
                llm=LLMConfig(
                    backend=data.get("default_llm", "f235"),
                    model=data.get("default_model", "deepseek-ai/DeepSeek-V4-Flash-0731"),
                    ollama_url=data.get("ollama_url", "http://localhost:11434"),
                    lm_studio_url=data.get("lm_studio_url", "http://localhost:1234/v1"),
                    f235_url=data.get("f235_url", "http://spark-f235:8000/v1"),
                    system_prompt=data.get("system_prompt", ""),
                ),
                hotkey=HotkeyConfig(
                    record_hotkey=data.get("hotkey", "ctrl+shift"),
                    clear_hotkey=data.get("clear_hotkey", "ctrl+alt+x"),
                ),
                output=OutputConfig(
                    output_dir=data.get("output_dir", "./outputs"),
                    paste_mode=data.get("paste_mode", "raw"),
                    verify_window=data.get("verify_window", True),
                    continuation_join=data.get("continuation_join", True),
                ),
                window=WindowConfig(
                    width=data.get("window_width"),
                    height=data.get("window_height"),
                    x=data.get("window_x"),
                    y=data.get("window_y"),
                ),
                system=SystemConfig(
                    minimize_to_tray=data.get("minimize_to_tray", False),
                    audio_cues=data.get("audio_cues", False),
                ),
            )


def find_whisper_executable() -> str:
    """Try to find the whisper.cpp executable."""
    # Common executable names
    names = ["whisper", "main", "whisper-cpp"]

    # Check PATH first
    for name in names:
        found = shutil.which(name)
        if found:
            return found

    # Common installation paths
    paths = [
        Path.home() / "whisper.cpp" / "main",
        Path.home() / "whisper.cpp" / "build" / "bin" / "main",
        Path.home() / ".local" / "bin" / "whisper",
        Path("/usr/local/bin/whisper"),
        Path("/usr/bin/whisper"),
    ]

    # Check known paths
    for path in paths:
        if path.exists() and os.access(path, os.X_OK):
            return str(path)

    return ""


def find_whisper_model(model_name: str = "base.en") -> str:
    """Try to find a whisper model file."""
    model_filename = f"ggml-{model_name}.bin"

    search_dirs = [
        Path.home() / ".cache" / "whisper",
        Path.home() / "whisper.cpp" / "models",
        Path("./models"),
        Path("/usr/share/whisper/models"),
    ]

    for dir_path in search_dirs:
        model_path = dir_path / model_filename
        if model_path.exists():
            return str(model_path)

    return ""
