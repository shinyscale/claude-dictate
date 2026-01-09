"""
Claude Dictate - Voice-to-Text Tool for Claude Code
A local dictation tool using whisper.cpp with optional LLM refinement.
"""

from .audio import AudioRecorder
from .transcriber import WhisperTranscriber
from .refiner import LLMRefiner
from .exporter import OutputGenerator
from .config import AppConfig

__version__ = "1.0.0"
__all__ = [
    "AudioRecorder",
    "WhisperTranscriber",
    "LLMRefiner",
    "OutputGenerator",
    "AppConfig",
]
