@echo off
title PMAX Test Steps Update Tool - Launcher
echo ============================================
echo   PMAX Test Steps Update Tool - Setup
echo ============================================
echo.

:: Set the project directory to where this batch file is located
cd /d "%~dp0"

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ and add it to your PATH.
    pause
    exit /b 1
)

echo [1/3] Checking virtual environment...

:: Create virtual environment if it doesn't exist
if not exist "myvenv" (
    echo       Creating virtual environment...
    python -m venv myvenv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo       Virtual environment created successfully.
) else (
    echo       Virtual environment already exists.
)

echo.
echo [2/3] Installing packages...

:: Activate virtual environment and install requirements
call myvenv\Scripts\activate.bat

pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install packages. Check requirements.txt.
    pause
    exit /b 1
)
echo       Packages installed successfully.

echo.
echo [3/3] Launching Streamlit app...
echo ============================================
echo   App is starting... 
echo   It will open in your default browser.
echo   Press Ctrl+C in this window to stop.
echo ============================================
echo.

streamlit run streamlitapp.py

:: Deactivate when done
call myvenv\Scripts\deactivate.bat 2>nul
pause
