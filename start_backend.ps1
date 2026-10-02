[CmdletBinding()]
param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$repoRoot = $PSScriptRoot
$frontendRoot = Join-Path $repoRoot "frontend"
$desktopExe = Join-Path $frontendRoot "build\windows\x64\runner\Release\macau_navigation.exe"
$healthUri = "http://127.0.0.1:$Port/health"

function Test-BackendHealth {
    try {
        $response = Invoke-WebRequest -Uri $healthUri -UseBasicParsing -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Get-ListeningConnection {
    try {
        return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop)
    } catch {
        return @()
    }
}

function Show-PortDiagnostics {
    param([object[]]$Connections)

    Write-Host "ERROR: TCP port $Port is occupied, but $healthUri did not return a healthy response." -ForegroundColor Red
    foreach ($connection in $Connections) {
        $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        $processName = if ($process) { $process.ProcessName } else { "unknown" }
        Write-Host ("PID {0} ({1}) is listening on {2}:{3}." -f `
            $connection.OwningProcess, $processName, $connection.LocalAddress, $connection.LocalPort)
    }
    Write-Host "Stop the conflicting process or configure the backend/client to use another port, then retry." -ForegroundColor Yellow
}

if (-not (Test-Path (Join-Path $frontendRoot "windows\CMakeLists.txt"))) {
    throw "Flutter Windows project is missing: $frontendRoot\windows. Run flutter create --platforms=windows frontend."
}

$backendAlreadyRunning = Test-BackendHealth
if ($backendAlreadyRunning) {
    Write-Host "Reusing healthy backend at $healthUri." -ForegroundColor Green
} else {
    $connections = Get-ListeningConnection
    if ($connections.Count -gt 0) {
        Show-PortDiagnostics -Connections $connections
        exit 1
    }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if (-not $python) {
        throw "Python was not found on PATH. Install Python or activate the project's venv before launching."
    }

    $activate = Join-Path $repoRoot "venv\Scripts\activate.bat"
    $backendCommand = "cd /d `"$repoRoot`""
    if (Test-Path $activate) {
        $backendCommand += " && call `"$activate`""
    }
    $backendCommand += " && python -m uvicorn backend.main:app --host 0.0.0.0 --port $Port --reload"
    Start-Process -FilePath "cmd.exe" -ArgumentList "/k", $backendCommand | Out-Null

    $healthy = $false
    for ($attempt = 1; $attempt -le 30; $attempt++) {
        Start-Sleep -Seconds 1
        if (Test-BackendHealth) {
            $healthy = $true
            break
        }
    }
    if (-not $healthy) {
        $connections = Get-ListeningConnection
        if ($connections.Count -gt 0) {
            Show-PortDiagnostics -Connections $connections
        }
        throw "Backend did not become healthy at $healthUri within 30 seconds. Inspect the backend console for startup errors."
    }
    Write-Host "Started backend at $healthUri." -ForegroundColor Green
}

if (-not (Test-Path $desktopExe)) {
    $flutter = Get-Command flutter -ErrorAction SilentlyContinue
    if (-not $flutter) {
        throw "Desktop executable is missing and Flutter was not found on PATH. Run: flutter build windows"
    }
    Push-Location $frontendRoot
    try {
        flutter build windows
        if ($LASTEXITCODE -ne 0) {
            throw "flutter build windows failed. Verify Visual Studio Desktop development with C++ and a Windows SDK with: flutter doctor -v"
        }
    } finally {
        Pop-Location
    }
}

if (-not (Test-Path $desktopExe)) {
    throw "Windows desktop executable is still missing: $desktopExe"
}

Start-Process -FilePath $desktopExe
Write-Host "Started Macau Navigation desktop app." -ForegroundColor Green
