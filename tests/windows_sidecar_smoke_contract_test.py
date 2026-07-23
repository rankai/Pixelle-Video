from pathlib import Path

WORKFLOW = Path(".github/workflows/windows-desktop-build.yml")
SMOKE = Path("scripts/windows_sidecar_smoke.ps1")


def test_windows_ci_runs_a_bounded_direct_sidecar_diagnostic_before_installer_smoke():
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/windows_sidecar_smoke.ps1" in source
    assert "Diagnose packaged Windows sidecar" in source
    assert "Upload Windows sidecar smoke evidence" in source
    assert "continue-on-error: true" in source
    assert "windows-sidecar-smoke.json" in source


def test_windows_sidecar_smoke_is_bounded_and_never_publishes():
    source = SMOKE.read_text(encoding="utf-8")

    assert "#requires -Version 7.0" in source
    assert "Start-Process" in source
    assert "TimeoutSeconds = 90" in source
    assert "/health" in source
    assert "taskkill.exe" in source
    assert "external_actions = 0" in source
    assert "final_publish_clicks = 0" in source
    assert "stderr_present" in source
    assert "stderr_tail" in source
    assert "GITHUB_STEP_SUMMARY" in source
    assert "sidecar_exit_" in source
