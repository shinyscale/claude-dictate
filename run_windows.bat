@echo off
setlocal

:: Claude Dictate - start the tray app (no console window stays open).
:: Run install_windows.bat once first.
::   run_windows.bat            start in the tray
::   run_windows.bat --gui      open the editor window
::   run_windows.bat --console  start with a console, to watch messages live

cd /d "%~dp0"

if not exist "venv\Scripts\pythonw.exe" (
    echo Claude Dictate is not installed yet. Run install_windows.bat first.
    pause
    exit /b 1
)

if /i "%~1"=="--console" (
    venv\Scripts\python.exe run.py
    exit /b %errorlevel%
)

start "" venv\Scripts\pythonw.exe run.py %*
exit /b 0
