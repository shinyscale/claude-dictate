@echo off
setlocal enabledelayedexpansion

:: Claude Dictate Windows Launcher
:: Run this script natively on Windows (not through WSL) for full system tray support

echo Starting Claude Dictate...

:: Check if Python is available
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found in PATH
    echo Please install Python from https://python.org and add it to your PATH
    pause
    exit /b 1
)

:: Change to script directory
cd /d "%~dp0"

:: Check for virtual environment
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
) else if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
)

:: Check if core dependencies are installed
python -c "import customtkinter" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing dependencies...
    pip install -r requirements.txt
    if %errorlevel% neq 0 (
        echo ERROR: Failed to install dependencies
        pause
        exit /b 1
    )
)

:: Check and install system tray dependencies
python -c "import pystray" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing pystray...
    pip install pystray
)
python -c "from PIL import Image" >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing Pillow...
    pip install Pillow
)

:: Verify system tray is available
python -c "import pystray; from PIL import Image; print('System tray dependencies OK')" 2>nul || (
    echo WARNING: System tray dependencies not fully installed
)

:: Run the application
python run.py %*
