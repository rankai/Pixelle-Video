import json
from pathlib import Path

WORKFLOW = Path(".github/workflows/windows-desktop-build.yml")
ARTIFACT_CHECK = Path("scripts/windows_desktop_artifact_check.py")
PACKAGE_LOCK = Path("desktop/package-lock.json")
WINDOWS_ICON = Path("desktop/src-tauri/icons/icon.ico")


def test_windows_ci_uses_a_windows_runner_and_builds_both_targets():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: windows-latest" in source
    assert "uv run python desktop/scripts/build_sidecar.py" in source
    assert "pixelle-api-x86_64-pc-windows-msvc.exe" in source
    assert "npm run tauri build -- --target x86_64-pc-windows-msvc" in source
    assert "actions/upload-artifact@v4" in source
    assert "macos-latest" not in source


def test_windows_ci_is_manual_or_scoped_to_desktop_changes():
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in source
    assert '"desktop/**"' in source
    assert '"pyproject.toml"' in source
    assert '"uv.lock"' in source


def test_cross_platform_rolldown_bindings_are_optional_in_lockfile():
    lock = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    package = lock["packages"]["node_modules/@rolldown/binding-darwin-arm64"]
    assert package["os"] == ["darwin"]
    assert package["cpu"] == ["arm64"]
    assert package["optional"] is True


def test_windows_bundle_has_a_native_ico_resource():
    assert WINDOWS_ICON.exists()
    assert WINDOWS_ICON.stat().st_size > 0


def test_artifact_manifest_requires_windows_executables_and_marks_install_pending():
    source = ARTIFACT_CHECK.read_text(encoding="utf-8")
    assert 'expected_suffix=".exe"' in source
    assert "x86_64-pc-windows-msvc" in source
    assert '"install_test": "pending_windows_manual_install"' in source
