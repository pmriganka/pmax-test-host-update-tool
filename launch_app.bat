@echo off
title PMAX Test Steps Update Tool - Launcher
echo ============================================
echo   PMAX Test Steps Update Tool - Setup
echo ============================================
echo.

:: Save the real project directory (where this batch file lives)
set "PROJECT_DIR=%~dp0"
set "SUBST_DRIVE="

:: ---- Long-path workaround ------------------------------------------------
:: Map the project folder to a short drive letter so that deeply-nested
:: pip / setuptools paths stay under the Windows 260-char limit.
:: Clean up any stale mapping first.
for %%d in (Z Y X W V U T S R Q P O N M L K J I H G) do (
    if not exist %%d:\ (
        set "SUBST_DRIVE=%%d:"
        goto :found_drive
    )
)
:: No free drive letter – fall back to original (long) path
echo [WARN] No free drive letter for long-path workaround. Continuing...
set "APP_DIR=%PROJECT_DIR%"
goto :start

:found_drive
subst %SUBST_DRIVE% "%PROJECT_DIR:~0,-1%"
set "APP_DIR=%SUBST_DRIVE%\"
echo       Mapped %SUBST_DRIVE% to project directory (long-path workaround).
echo.

:start
:: All operations use APP_DIR so venv + packages land in the batch file's folder
cd /d "%APP_DIR%"

:: Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.10+ and add it to your PATH.
    goto :cleanup
)

echo [1/4] Checking virtual environment...

set "NEED_INSTALL=1"

:: Create virtual environment in the same folder as this batch file
if not exist "%APP_DIR%myvenv\Scripts\activate.bat" (
    echo       Creating virtual environment in %APP_DIR%myvenv ...
    python -m venv "%APP_DIR%myvenv"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        goto :cleanup
    )
    echo       Virtual environment created successfully.
) else (
    echo       Virtual environment already exists at %APP_DIR%myvenv
    :: Skip install only if the previously installed requirements match the current ones
    if exist "%APP_DIR%myvenv\.installed_requirements.txt" (
        fc /b "%APP_DIR%requirements.txt" "%APP_DIR%myvenv\.installed_requirements.txt" >nul 2>&1
        if not errorlevel 1 set "NEED_INSTALL=0"
    )
)

echo.
echo [2/4] Activating virtual environment...
call "%APP_DIR%myvenv\Scripts\activate.bat"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    goto :cleanup
)
echo       Virtual environment activated.

echo.
if "%NEED_INSTALL%"=="0" (
    echo [3/4] Required packages already installed - skipping installation.
) else (
    echo [3/4] Installing packages from requirements.txt...
    python -m pip install --upgrade pip --quiet
    python -m pip install -r "%APP_DIR%requirements.txt" --quiet
    if errorlevel 1 (
        echo [ERROR] Failed to install packages. Check requirements.txt.
        goto :cleanup
    )
    copy /Y "%APP_DIR%requirements.txt" "%APP_DIR%myvenv\.installed_requirements.txt" >nul
    echo       Packages installed successfully.
)

echo.
echo [4/4] Launching Streamlit app...
echo ============================================
echo   App is starting... 
echo   It will open in your default browser.
echo   Press Ctrl+C in this window to stop.
echo ============================================
echo.

python -m streamlit run "%APP_DIR%streamlitapp.py"

:cleanup
:: Remove the subst drive mapping if it was created
if defined SUBST_DRIVE (
    cd /d "%PROJECT_DIR%"
    subst %SUBST_DRIVE% /d 2>nul
)
pause
