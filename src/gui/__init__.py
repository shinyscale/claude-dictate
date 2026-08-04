"""
Claude Dictate GUI - Modern interface for voice-to-text
"""

from .app import ClaudeDictateGUI, run_gui
from .daemon import DictateDaemon, run_daemon
from .theme import THEME, FONTS
from .recorder import WaveformCanvas, StatusIndicator, ProgressBar
from .editor import TextEditor
from .settings import SettingsPanel

__all__ = [
    "ClaudeDictateGUI",
    "run_gui",
    "DictateDaemon",
    "run_daemon",
    "THEME",
    "FONTS",
    "WaveformCanvas",
    "StatusIndicator",
    "ProgressBar",
    "TextEditor",
    "SettingsPanel",
]
