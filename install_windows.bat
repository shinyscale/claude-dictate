@echo off
setlocal

:: Claude Dictate - one-step Windows setup.
:: Makes a private Python environment in this folder, installs everything,
:: downloads the speech model, and runs the check-up. Safe to run again.

cd /d "%~dp0"

:: Python 3.12 is the newest version every dependency ships a Windows build for.
set "PY="
py -3.12 -c "import sys" >nul 2>&1 && set "PY=py -3.12"
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info[:2] in ((3,10),(3,11),(3,12)) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo ERROR: Python 3.10, 3.11 or 3.12 was not found.
    echo Install Python 3.12 from https://python.org and run this again.
    exit /b 1
)

if not exist "venv\Scripts\python.exe" (
    echo [1/4] Creating the Python environment...
    %PY% -m venv venv || exit /b 1
) else (
    echo [1/4] Python environment already there.
)

echo [2/4] Installing packages (a few minutes the first time)...
venv\Scripts\python.exe -m pip install --quiet --upgrade pip || exit /b 1
venv\Scripts\python.exe -m pip install --quiet -r requirements.txt || exit /b 1

echo [3/4] Check-up (downloads the speech model the first time, about 1.6 GB)...
venv\Scripts\python.exe doctor.py --shortcut
if errorlevel 1 (
    echo.
    echo Something above says FAIL. Fix that, then run this again.
    exit /b 1
)

echo [4/4] Done.
echo.
echo Start it with:   run_windows.bat   (or search Start for Claude Dictate)
echo Then hold Ctrl+Shift anywhere, talk, and let go.
echo To start it every time you sign in: right-click the tray icon,
echo "Start when I sign in".
exit /b 0
