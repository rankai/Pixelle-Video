use serde::Serialize;
use std::path::PathBuf;
use std::sync::Mutex;
use tauri::{Manager, State};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;
use uuid::Uuid;

#[derive(Default)]
struct BackendProcess(Mutex<Option<CommandChild>>);

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
struct RuntimeInfo {
    api_base_url: String,
    desktop_token: String,
}

#[tauri::command]
fn desktop_runtime(runtime: State<RuntimeInfo>) -> RuntimeInfo {
    runtime.inner().clone()
}

fn spawn_backend(app: &tauri::App, runtime: &RuntimeInfo) -> tauri::Result<Option<CommandChild>> {
    let sidecar = app.shell().sidecar("pixelle-api");
    let command = match sidecar {
        Ok(command) => command,
        Err(error) => {
            eprintln!("Pixelle API sidecar is not bundled yet: {error}");
            return Ok(None);
        }
    };

    let data_root = sidecar_data_root(app)?;
    let config_path = data_root.join("config.yaml");
    let port = api_port(&runtime.api_base_url);
    let command = if let Some(working_dir) = sidecar_working_dir(app) {
        command.current_dir(working_dir)
    } else {
        command
    };
    // Keep the API feature gate aligned with the frontend launch flag. The
    // desktop binary is often started with PIXELLE_ASSET_CENTER_V2=true for
    // staged rollout, but child processes do not inherit that flag through
    // tauri-plugin-shell unless it is explicitly forwarded.
    let asset_center_v2 = std::env::var("PIXELLE_ASSET_CENTER_V2").unwrap_or_else(|_| "1".to_string());
    let asset_center_smb_ux = std::env::var("PIXELLE_ASSET_CENTER_SMB_UX").unwrap_or_else(|_| "0".to_string());
    let (_, child) = command
        .env("PIXELLE_DESKTOP_MODE", "1")
        .env("PIXELLE_DESKTOP_TOKEN", &runtime.desktop_token)
        .env("PIXELLE_DESKTOP_ORIGIN", "tauri://localhost")
        .env("PIXELLE_VIDEO_ROOT", &data_root)
        .env("PIXELLE_CONFIG_PATH", &config_path)
        .env("PIXELLE_ASSET_CENTER_V2", asset_center_v2)
        .env("PIXELLE_ASSET_CENTER_SMB_UX", asset_center_smb_ux)
        .args(["--host", "127.0.0.1", "--port", port.as_str()])
        .spawn()
        .map_err(|error| std::io::Error::other(error.to_string()))?;
    Ok(Some(child))
}

fn sidecar_data_root(app: &tauri::App) -> tauri::Result<PathBuf> {
    let root = if cfg!(debug_assertions) {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
    } else {
        app.path().app_data_dir()?
    };
    std::fs::create_dir_all(&root)?;
    Ok(root)
}

fn sidecar_working_dir(app: &tauri::App) -> Option<PathBuf> {
    // In development the Tauri CLI starts from `desktop/`, while the API
    // resolves `templates/`, `workflows/`, and the local config relative to
    // the repository root. In a packaged app those resources are copied into
    // Tauri's resource directory instead.
    let repository_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
    if cfg!(debug_assertions) && repository_root.join("templates").is_dir() {
        return Some(repository_root);
    }

    app.path()
        .resource_dir()
        .ok()
        .filter(|resource_dir| resource_dir.join("templates").is_dir())
}

fn api_port(api_base_url: &str) -> String {
    api_base_url
        .rsplit(':')
        .next()
        .unwrap_or("8000")
        .trim_end_matches('/')
        .to_string()
}

fn stop_backend(child: CommandChild) {
    // PyInstaller one-file executables keep the actual Python process as a
    // child of the bootloader. Killing only CommandChild would leave that
    // child listening on the API port after the Tauri window closes.
    let pid = child.pid().to_string();
    #[cfg(unix)]
    {
        let _ = std::process::Command::new("pkill")
            .args(["-TERM", "-P", pid.as_str()])
            .status();
    }
    #[cfg(windows)]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", pid.as_str(), "/T", "/F"])
            .status();
    }
    let _ = child.kill();
}

fn default_api_base_url() -> String {
    if let Ok(value) = std::env::var("PIXELLE_API_BASE_URL") {
        let trimmed = value.trim().trim_end_matches('/');
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }
    if cfg!(debug_assertions) {
        "http://127.0.0.1:8100".to_string()
    } else {
        "http://127.0.0.1:8000".to_string()
    }
}

fn main() {
    let runtime = RuntimeInfo {
        api_base_url: default_api_base_url(),
        desktop_token: Uuid::new_v4().to_string(),
    };

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(runtime.clone())
        .manage(BackendProcess::default())
        .invoke_handler(tauri::generate_handler![desktop_runtime])
        .setup(move |app| {
            let child = spawn_backend(app, &runtime)?;
            if let Some(child) = child {
                let state = app.state::<BackendProcess>();
                *state.0.lock().expect("backend state lock poisoned") = Some(child);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<BackendProcess>();
                let child = state
                    .0
                    .lock()
                    .expect("backend state lock poisoned")
                    .take();
                if let Some(child) = child {
                    stop_backend(child);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Pixelle desktop app");
}
