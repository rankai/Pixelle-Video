from pathlib import Path

WORKFLOW = Path(".github/workflows/windows-desktop-build.yml")
SMOKE = Path("scripts/windows_installer_smoke.ps1")


def test_windows_ci_runs_install_health_restart_smoke_and_uploads_evidence():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "Install and smoke-test Windows package" in source
    assert "scripts/windows_installer_smoke.ps1" in source
    assert "windows-installer-smoke.json" in source
    assert "if: ${{ always() }}" in source
    assert "Upload Windows installer smoke evidence" in source
    assert "actions/upload-artifact@v4" in source


def test_windows_smoke_script_has_bounded_install_health_and_port_release_contract():
    source = SMOKE.read_text(encoding="utf-8")
    required_fragments = (
        'ArgumentList @("/S", "/D=$installRootFull")',
        "Wait-Health",
        'http://127.0.0.1:$TargetPort/health',
        "Wait-PortReleased",
        "Stop-OwnSidecars",
        "foreach ($cycle in 1..2)",
        'status = "passed_with_boundary"',
        'external_actions = 0',
        'final_publish_clicks = 0',
        "taskkill.exe /PID $Process.Id /T /F",
        '"installer_timeout"',
        '"port_query_failed"',
        '"process_query_failed"',
        '"pixelle-video-desktop.exe"',
        "process_exit_code",
        '"app_exit_before_health_',
        '"smoke_failed"',
    )
    for fragment in required_fragments:
        assert fragment in source


def test_windows_smoke_evidence_redacts_machine_paths_and_secrets():
    source = SMOKE.read_text(encoding="utf-8")
    assert "desktop_token" not in source
    assert "authorization" not in source.lower()
    assert "Exception.Message" in source
    assert "Get-SafeErrorCode" in source
    assert "app_executable = [IO.Path]::GetFileName($appPath)" in source
    assert "#requires -Version 7.0" in source
    assert "foreach ($pid in" not in source
