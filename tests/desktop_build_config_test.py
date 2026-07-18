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
    assert 'apiBaseUrl: browserApiBaseUrl()' in source


def test_asset_center_v2_defaults_on_with_explicit_frontend_rollback():
    source = Path("desktop/src/featureFlags.ts").read_text()

    assert 'envFlag(import.meta.env.VITE_ASSET_CENTER_V2, true)' in source


def test_tauri_debug_runtime_matches_standalone_api_port():
    source = Path("desktop/src-tauri/src/main.rs").read_text()

    assert '"http://127.0.0.1:8100"' in source
    assert '"http://127.0.0.1:8000"' in source
    assert 'std::env::var("PIXELLE_API_BASE_URL")' in source
    assert "fn api_port" in source


def test_tauri_sidecar_uses_a_resource_aware_working_directory():
    source = Path("desktop/src-tauri/src/main.rs").read_text()

    assert "fn sidecar_working_dir" in source
    assert "current_dir(working_dir)" in source
    assert 'resource_dir()' in source


def test_tauri_bundle_maps_resources_to_stable_runtime_paths():
    source = Path("desktop/src-tauri/tauri.conf.json").read_text()

    assert '"../../templates": "templates"' in source
    assert '"../../workflows": "workflows"' in source


def test_desktop_sidecar_persists_data_and_config_outside_the_app_bundle():
    rust_source = Path("desktop/src-tauri/src/main.rs").read_text()
    config_source = Path("pixelle_video/config/manager.py").read_text()

    assert '"PIXELLE_VIDEO_ROOT"' in rust_source
    assert '"PIXELLE_CONFIG_PATH"' in rust_source
    assert 'os.environ.get("PIXELLE_CONFIG_PATH")' in config_source


def test_desktop_sidecar_receives_asset_center_rollout_flag():
    source = Path("desktop/src-tauri/src/main.rs").read_text()

    assert 'std::env::var("PIXELLE_ASSET_CENTER_V2")' in source
    assert '.env("PIXELLE_ASSET_CENTER_V2", asset_center_v2)' in source
    assert 'unwrap_or_else(|_| "1".to_string())' in source


def test_tauri_close_cleans_the_pyinstaller_sidecar_process_tree():
    source = Path("desktop/src-tauri/src/main.rs").read_text()

    assert "fn stop_backend" in source
    assert '"pkill"' in source
    assert '"taskkill"' in source
