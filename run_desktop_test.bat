@echo off
setlocal EnableExtensions

REM Double-click this file from the repository root to run the desktop test app.
cd /d "%~dp0"

if exist "%USERPROFILE%\Downloads\macau-260904.osm.pbf" (
  set "OSM_PBF_PATH=%USERPROFILE%\Downloads\macau-260904.osm.pbf"
  echo Using local OSM PBF: %OSM_PBF_PATH%
)

where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found on PATH.
  pause
  exit /b 1
)

where flutter >nul 2>nul
if errorlevel 1 (
  echo Flutter was not found on PATH.
  pause
  exit /b 1
)

if not exist "frontend\windows\CMakeLists.txt" (
  echo Flutter Windows support is missing. Generating it now...
  flutter create --platforms=windows frontend
  if errorlevel 1 (
    echo Could not generate the Flutter Windows runner.
    pause
    exit /b 1
  )
)

echo Checking the backend...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$h = try { (Invoke-RestMethod -Uri http://127.0.0.1:8000/health -TimeoutSec 1) } catch { $null }; if ($null -ne $h -and -not $h.fallback_graph -and $h.node_count -gt 1000) { exit 0 } else { exit 1 }"
if not errorlevel 1 goto backend_ready

powershell -NoProfile -ExecutionPolicy Bypass -Command "$h = try { (Invoke-RestMethod -Uri http://127.0.0.1:8000/health -TimeoutSec 1) } catch { $null }; if ($null -ne $h -and $h.status -eq 'healthy') { $connections = @(Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue); foreach ($connection in $connections) { $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue; if ($null -ne $process -and ($process.ProcessName -in @('python','python3','uvicorn'))) { Write-Host ('Stopping old Macau backend (PID ' + $process.Id + ').') -ForegroundColor Yellow; Stop-Process -Id $process.Id -Force } }; Start-Sleep -Milliseconds 500 }"

echo Starting the backend...
start "Macau Navigation Backend" /min cmd /c "python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"

echo Waiting for the backend health endpoint...
for /l %%N in (1,1,30) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health -TimeoutSec 1 | Out-Null; exit 0 } catch { exit 1 }"
  if not errorlevel 1 goto backend_ready
  timeout /t 1 /nobreak >nul
)

echo Backend did not become ready at http://127.0.0.1:8000/health
pause
exit /b 1

:backend_ready
echo Backend is ready. Checking the Flutter Windows app...
pushd frontend
if not exist "build\windows\x64\runner\Release\macau_navigation.exe" (
  echo Release app not found. Installing dependencies and building it once...
  flutter pub get
  if errorlevel 1 (
    popd
    echo Flutter dependencies could not be installed.
    pause
    exit /b 1
  )
  flutter build windows --release
  if errorlevel 1 (
    popd
    echo Flutter Windows build failed.
    pause
    exit /b 1
  )
)
echo Opening the Flutter Windows app...
start "" "build\windows\x64\runner\Release\macau_navigation.exe"
set APP_EXIT=0
popd

echo The Flutter app was started.
echo The backend window remains open while the app is running.
pause
exit /b %APP_EXIT%
