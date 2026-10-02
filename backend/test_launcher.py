from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = (ROOT / "start_backend.ps1").read_text(encoding="utf-8")


def test_windows_launcher_reuses_healthy_backend() -> None:
    assert "Invoke-WebRequest" in LAUNCHER
    assert "127.0.0.1:$Port/health" in LAUNCHER
    assert "Reusing healthy backend" in LAUNCHER


def test_windows_launcher_reports_unhealthy_port_owner() -> None:
    assert "Get-NetTCPConnection -LocalPort $Port -State Listen" in LAUNCHER
    assert "OwningProcess" in LAUNCHER
    assert "Show-PortDiagnostics" in LAUNCHER


def test_windows_launcher_starts_backend_only_after_port_check() -> None:
    port_check = LAUNCHER.index("$connections = Get-ListeningConnection")
    start_backend = LAUNCHER.index("Start-Process -FilePath \"cmd.exe\"")
    assert port_check < start_backend
    assert "macau_navigation.exe" in LAUNCHER
