"""
A real Start Menu shortcut for Claude Dictate (Windows).

Without one, the editor is just "pythonw.exe" to Windows: right-clicking
its taskbar button offers to pin Python, not Claude Dictate, and the pin
does not reopen the app. A Start Menu shortcut that carries the same
AppUserModelID as the running window is what makes "Pin to taskbar" pin
this app, with its own icon, and makes the pin launch it.
"""

import os
import sys
from pathlib import Path

# Must match the id the editor window gives itself (gui/app.py).
APP_ID = "ClaudeDictate.VoiceToText.1.0"
NAME = "Claude Dictate"


def shortcut_path() -> Path:
    return (Path(os.environ.get("APPDATA", str(Path.home())))
            / "Microsoft" / "Windows" / "Start Menu" / "Programs" / f"{NAME}.lnk")


def create() -> Path:
    """Create or refresh the Start Menu shortcut. Raises on failure."""
    if os.name != "nt":
        raise RuntimeError("shortcuts are a Windows feature")
    import pythoncom
    from win32com.shell import shell
    from win32com.propsys import propsys, pscon

    repo = Path(__file__).resolve().parents[1]
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw

    link = pythoncom.CoCreateInstance(
        shell.CLSID_ShellLink, None,
        pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IShellLink)
    link.SetPath(str(exe))
    # Opens the editor window, which starts the tray app if it isn't running.
    link.SetArguments(f'"{repo / "run.py"}" --gui')
    link.SetWorkingDirectory(str(repo))
    link.SetDescription("Hold a hotkey, talk, and the text is typed where your cursor is")
    icon = repo / "claude_dictate.ico"
    if icon.exists():
        link.SetIconLocation(str(icon), 0)

    store = link.QueryInterface(propsys.IID_IPropertyStore)
    store.SetValue(pscon.PKEY_AppUserModel_ID,
                   propsys.PROPVARIANTType(APP_ID, pythoncom.VT_LPWSTR))
    store.Commit()

    path = shortcut_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    link.QueryInterface(pythoncom.IID_IPersistFile).Save(str(path), True)
    return path
