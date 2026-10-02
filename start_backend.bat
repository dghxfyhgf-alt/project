@echo off
setlocal
REM Start the Macau backend and Windows Flutter desktop client.
REM Run from project root or double-click this file.

cd /d "%~dp0"

if not exist "frontend\windows\CMakeLists.txt" (
    echo ERROR: Flutter Windows desktop support is not configured for frontend.
    echo Run: flutter create --platforms=windows --project-name macau_navigation frontend
    pause
    exit /b 1
)

if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python was not found on PATH.
    pause
    exit /b 1
)

start "Macau Navigation Backend" cmd /k "cd /d ""%~dp0"" && if exist venv\Scripts\activate.bat call venv\Scripts\activate.bat && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload"

set "DESKTOP_EXE=%~dp0frontend\build\windows\x64\runner\Release\macau_navigation.exe"
if not exist "%DESKTOP_EXE%" (
    echo Release executable not found. Attempting a Windows desktop build...
    where flutter >nul 2>&1
    if errorlevel 1 (
        echo ERROR: Flutter was not found on PATH and no built desktop executable exists.
        echo Install Flutter and add its bin directory to PATH:
        echo https://docs.flutter.dev/get-started/install/windows/desktop
        pause
        exit /b 1
    )
    cd /d "%~dp0frontend"
    flutter devices 2>nul | findstr /I /C:"windows" >nul
    if errorlevel 1 (
        echo ERROR: No Flutter Windows desktop device is available.
        echo Install Visual Studio with the "Desktop development with C++" workload
        echo and a Windows 10/11 SDK, then verify with: flutter doctor -v
        pause
        exit /b 1
    )
    flutter build windows
    if errorlevel 1 (
        echo ERROR: Windows desktop build failed.
        echo Run "flutter doctor -v" and confirm Visual Studio C++ desktop tooling is installed.
        pause
        exit /b 1
    )
)

if exist "%DESKTOP_EXE%" (
    echo Starting %DESKTOP_EXE%
    start "Macau Navigation" "%DESKTOP_EXE%"
) else (
    echo.
    echo ERROR: Windows desktop executable is still missing after the build.
    pause
    exit /b 1
)