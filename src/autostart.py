"""
Start Claude Dictate when you sign in to Windows.

Uses the per-user Run key (HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run):
no admin rights, no extra dependency, visible and removable in
Task Manager > Startup apps. Off by default; the tray menu toggles it.
"""

import os
import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "ClaudeDictate"


def supported() -> bool:
    return os.name == "nt"


def launch_command() -> str:
    """The command the Run key should hold: this install's own Python,
    windowless (pythonw.exe), running this checkout's run.py."""
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    run_py = Path(__file__).resolve().parents[1] / "run.py"
    return f'"{exe}" "{run_py}"'


def is_enabled() -> bool:
    if not supported():
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    """Turn start-at-sign-in on or off. Returns the state afterwards."""
    if not supported():
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ,
                                  launch_command())
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                except FileNotFoundError:
                    pass
    except OSError as e:
        print(f"[Autostart] Could not change the startup setting: {e}")
    return is_enabled()
