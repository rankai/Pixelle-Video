import json
from pathlib import Path

WORKFLOW = Path(".github/workflows/windows-desktop-build.yml")
ARTIFACT_CHECK = Path("scripts/windows_desktop_artifact_check.py")
PACKAGE_LOCK = Path("desktop/package-lock.json")
WINDOWS_ICON = Path("desktop/src-tauri/icons/icon.ico")
TAURI_MAIN = Path("desktop/src-tauri/src/main.rs")


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
    assert "pull_request:" in source
    assert "branches: [main]" in source
    assert 'branches: [dev, main, "codex/**"]' in source
    assert '"scripts/**"' in source
    assert '"tests/windows_*_test.py"' in source
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


def test_windows_tauri_webview_uses_the_http_localhost_origin_for_sidecar_cors():
    source = TAURI_MAIN.read_text(encoding="utf-8")
    assert 'cfg!(target_os = "windows")' in source
    assert '"http://tauri.localhost"' in source
    assert '"tauri://localhost"' in source
    assert '.env("PIXELLE_DESKTOP_ORIGIN", desktop_origin())' in source


def test_windows_sidecar_runs_from_user_writable_app_data():
    source = TAURI_MAIN.read_text(encoding="utf-8")
    assert "fn sidecar_resource_root" in source
    assert "let command = command.current_dir(&resource_root);" in source
    assert '.env("PIXELLE_RESOURCE_ROOT", &resource_root)' in source
    assert "resources are" in source and "unavailable" in source


def test_windows_sidecar_enables_application_registry_rollout_by_default():
    source = TAURI_MAIN.read_text(encoding="utf-8")
    assert 'std::env::var("PIXELLE_APP_CENTER_CONTENT_APPS")' in source
    assert 'std::env::var("PIXELLE_APP_CENTER_DOUYIN_CAROUSEL")' in source
    assert 'std::env::var("PIXELLE_APP_CENTER_DIGITAL_HUMAN")' in source
    assert '.env("PIXELLE_APP_CENTER_CONTENT_APPS", app_center_content_apps)' in source
    assert '"PIXELLE_APP_CENTER_DOUYIN_CAROUSEL"' in source
    assert "app_center_douyin_carousel" in source
    assert '.env("PIXELLE_APP_CENTER_DIGITAL_HUMAN", app_center_digital_human)' in source


def test_windows_sidecar_keeps_publish_v2_backend_gate_in_sync_with_desktop_shell():
    source = TAURI_MAIN.read_text(encoding="utf-8")
    assert 'std::env::var("PIXELLE_PUBLISH_V2_ENABLED")' in source
    assert 'unwrap_or_else(|_| "1".to_string())' in source
    assert '.env("PIXELLE_PUBLISH_V2_ENABLED", publish_v2_enabled)' in source
    assert "explicit" in source and "rollback switch" in source


def test_windows_sidecar_keeps_brand_project_gate_in_sync_with_desktop_shell():
    source = TAURI_MAIN.read_text(encoding="utf-8")
    main_source = Path("desktop/src/main.tsx").read_text(encoding="utf-8")
    feature_source = Path("desktop/src/featureFlags.ts").read_text(encoding="utf-8")
    assert 'std::env::var("PIXELLE_BRAND_PROJECT_BOUNDARY_V1")' in source
    assert '"PIXELLE_BRAND_PROJECT_BOUNDARY_V1"' in source
    assert "feature_flags: RuntimeFeatureFlags" in source
    assert "parse_env_flag(" in source
    assert "brand_project_boundary_v1," in source
    assert "initializeDesktopRuntime" in main_source
    assert "applyRuntimeFeatureFlags(runtime.featureFlags)" in main_source
    assert "mergeRuntimeFeatureFlags" in feature_source
    assert "legacy interaction" in source


def test_artifact_manifest_requires_windows_executables_and_marks_install_pending():
    source = ARTIFACT_CHECK.read_text(encoding="utf-8")
    assert 'expected_suffix=".exe"' in source
    assert "x86_64-pc-windows-msvc" in source
    assert '"install_test": "pending_windows_manual_install"' in source
    assert '"name": path.name' in source
    assert '"path": str(path)' not in source
