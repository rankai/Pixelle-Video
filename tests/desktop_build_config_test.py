import json
from pathlib import Path


def test_desktop_production_build_does_not_emit_source_maps_by_default():
    source = Path("desktop/vite.config.ts").read_text()

    assert "sourcemap: false" in source


def test_desktop_build_splits_heavy_ui_dependencies():
    source = Path("desktop/vite.config.ts").read_text()

    assert "rolldownOptions" in source
    assert "codeSplitting" in source
    assert 'name: "antd-ui"' in source


def test_browser_dev_defaults_to_standalone_api_port():
    source = Path("desktop/src/api.ts").read_text()

    assert '["5173", "5174", "1420"].includes(window.location.port)' in source
    assert '"http://127.0.0.1:8100"' in source
    # Tauri receives its debug/release URL through desktop_runtime.
    assert "apiBaseUrl: browserApiBaseUrl()" in source


def test_asset_center_v2_defaults_on_with_explicit_frontend_rollback():
    source = Path("desktop/src/flagResolver.ts").read_text()

    assert 'assetCenterV2: readFlag(env, "VITE_ASSET_CENTER_V2", true)' in source


def test_app_center_shell_defaults_off_and_uses_hash_router_boundary():
    flags = Path("desktop/src/flagResolver.ts").read_text()
    shell = Path("desktop/src/features/app-center/AppShell.tsx").read_text()

    assert 'appCenterShell: readFlag(env, "VITE_APP_CENTER_SHELL", false)' in flags
    assert "export function HashRouter" in shell
    assert "window.location.hash" in shell
    assert "pixelle_app_center_last_route" in shell
    assert "function normalizePath" in shell
    assert "if (!featureFlags.appCenterShell)" in shell


def test_production_desktop_build_explicitly_enables_application_center_rollout():
    production_env = Path("desktop/.env.production").read_text(encoding="utf-8")

    assert "VITE_APP_CENTER_SHELL=true" in production_env
    assert "VITE_CONTENT_APPS=true" in production_env
    assert "VITE_DOUYIN_CAROUSEL=true" in production_env
    assert "VITE_APP_CENTER_DIGITAL_HUMAN=true" in production_env
    assert "VITE_APP_CENTER_DIGITAL_HUMAN_DUAL_MODE=true" in production_env
    assert "VITE_BRAND_PROJECT_BOUNDARY_V1=true" in production_env


def test_desktop_navigation_keeps_workspace_before_application_center():
    source = Path("desktop/src/StudioApp.tsx").read_text(encoding="utf-8")
    home_index = source.index('{ key: "home", icon: <Home')
    apps_index = source.index('key: "apps", icon: <Images')

    assert home_index < apps_index


def test_app_shell_smoke_evidence_covers_flag_rollback_and_route_contract():
    evidence = json.loads(
        Path(
            "docs/reviews/application-publishing-program/qa/AC-1-app-shell-smoke-2026-07-19.json"
        ).read_text()
    )

    assert evidence["stage"] == "APP-SHELL"
    assert evidence["gate"] == "PG-B"
    assert evidence["registry"]["list_endpoint"] == "GET /api/apps"
    assert evidence["registry"]["manifest_count"] == 4
    assert (
        evidence["registry"]["canonical_flag_env"]["contentApps"]
        == "PIXELLE_APP_CENTER_CONTENT_APPS"
    )
    assert evidence["flag_on"]["pass"] is True
    assert evidence["flag_on"]["console_errors"] == 0
    assert evidence["flag_on"]["network_failures"] == 0
    assert [step["hash"] for step in evidence["flag_on"]["steps"] if "hash" in step] == [
        "/apps",
        "/ip",
    ]
    assert evidence["flag_on"]["readiness"]["configured"]["button_enabled"] is True
    assert (
        evidence["flag_on"]["readiness"]["after_isolated_config_change_to_missing"][
            "button_enabled"
        ]
        is False
    )
    assert evidence["flag_on"]["desktop_restart_route"]["pass"] is True
    assert evidence["flag_on"]["forbidden_non_get_requests"] == []
    assert evidence["flag_on"]["route_normalization"]["after_mount"] == "/apps"
    assert evidence["flag_off"]["pass"] is True
    assert evidence["flag_off"]["legacy_fallback"]["app_center_heading_count"] == 0


def test_desktop_app_shell_has_vitest_and_registry_render_smokes():
    package = json.loads(Path("desktop/package.json").read_text())
    config = Path("desktop/vitest.config.ts").read_text()

    assert package["scripts"]["test"] == "vitest"
    assert "vitest" in package["devDependencies"]
    assert "@testing-library/react" in package["devDependencies"]
    assert 'environment: "jsdom"' in config
    assert Path("desktop/src/features/app-center/AppShell.test.tsx").exists()
    assert Path("desktop/src/features/app-center/ApplicationCenterView.test.tsx").exists()


def test_tauri_debug_runtime_matches_standalone_api_port():
    source = Path("desktop/src-tauri/src/main.rs").read_text()

    assert '"http://127.0.0.1:8100"' in source
    assert '"http://127.0.0.1:8000"' in source
    assert 'std::env::var("PIXELLE_API_BASE_URL")' in source
    assert "fn api_port" in source


def test_tauri_sidecar_uses_a_user_writable_working_directory():
    source = Path("desktop/src-tauri/src/main.rs").read_text()

    # The sidecar reads bundled resources from Tauri's resource map, with a
    # user-writable app-data fallback if the resource bundle is unavailable.
    assert "fn sidecar_resource_root" in source
    assert "let command = command.current_dir(&resource_root);" in source
    assert '.env("PIXELLE_RESOURCE_ROOT", &resource_root)' in source
    assert "resources are" in source and "unavailable" in source


def test_tauri_bundle_maps_resources_to_stable_runtime_paths():
    source = Path("desktop/src-tauri/tauri.conf.json").read_text()

    assert '"../../templates": "templates"' in source
    assert '"../../workflows": "workflows"' in source


def test_desktop_sidecar_persists_data_and_config_outside_the_app_bundle():
    rust_source = Path("desktop/src-tauri/src/main.rs").read_text()
    config_source = Path("pixelle_video/config/manager.py").read_text()

    assert '"PIXELLE_VIDEO_ROOT"' in rust_source
    assert '"PIXELLE_CONFIG_PATH"' in rust_source
    assert '"PIXELLE_DESKTOP_TASKS_DB"' in rust_source
    assert '"PIXELLE_APP_CENTER_DB"' in rust_source
    assert 'os.environ.get("PIXELLE_CONFIG_PATH")' in config_source


def test_desktop_sidecar_receives_asset_center_rollout_flag():
    source = Path("desktop/src-tauri/src/main.rs").read_text()

    assert 'std::env::var("PIXELLE_ASSET_CENTER_V2")' in source
    assert '.env("PIXELLE_ASSET_CENTER_V2", asset_center_v2)' in source
    assert 'unwrap_or_else(|_| "1".to_string())' in source


def test_desktop_sidecar_receives_brand_project_rollout_flag():
    source = Path("desktop/src-tauri/src/main.rs").read_text()
    main_source = Path("desktop/src/main.tsx").read_text()
    feature_source = Path("desktop/src/featureFlags.ts").read_text()

    assert 'std::env::var("PIXELLE_BRAND_PROJECT_BOUNDARY_V1")' in source
    assert (
        '.env(\n            "PIXELLE_BRAND_PROJECT_BOUNDARY_V1",\n'
        "            brand_project_boundary_v1,\n        )"
    ) in source
    assert "feature_flags: RuntimeFeatureFlags" in source
    assert "parse_env_flag(" in source
    assert "brand_project_boundary_v1," in source
    assert "initializeDesktopRuntime" in main_source
    assert "applyRuntimeFeatureFlags(runtime.featureFlags)" in main_source
    assert "mergeRuntimeFeatureFlags" in feature_source
    assert "legacy interaction" in source


def test_desktop_sidecar_keeps_result_history_rollout_flag_aligned():
    source = Path("desktop/src-tauri/src/main.rs").read_text()
    main_source = Path("desktop/src/main.tsx").read_text()
    feature_source = Path("desktop/src/featureFlags.ts").read_text()

    assert 'std::env::var("PIXELLE_APP_RESULT_HISTORY_V1")' in source
    assert '.env("PIXELLE_APP_RESULT_HISTORY_V1", app_result_history_v1)' in source
    assert "app_result_history_v1," in source
    assert "feature_flags: RuntimeFeatureFlags" in source
    assert "initializeDesktopRuntime" in main_source
    assert "applyRuntimeFeatureFlags(runtime.featureFlags)" in main_source
    assert "mergeRuntimeFeatureFlags" in feature_source


def test_digital_human_source_tabs_stay_inside_the_workbench_pane():
    styles = Path("desktop/src/styles.css").read_text()

    assert ".app-workbench-adopted .digital-human-app-source-tabs {" in styles
    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in styles
    assert ".app-workbench-adopted .digital-human-app-source-tabs button {" in styles
    assert "min-width: 0;" in styles


def test_tauri_close_cleans_the_pyinstaller_sidecar_process_tree():
    source = Path("desktop/src-tauri/src/main.rs").read_text()

    assert "fn stop_backend" in source
    assert '"pkill"' in source
    assert '"taskkill"' in source
