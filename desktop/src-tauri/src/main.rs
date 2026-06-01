use serde::Serialize;
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

    let child = command
        .env("PIXELLE_DESKTOP_MODE", "1")
        .env("PIXELLE_DESKTOP_TOKEN", &runtime.desktop_token)
        .env("PIXELLE_DESKTOP_ORIGIN", "tauri://localhost")
        .args(["--host", "127.0.0.1", "--port", "8000"])
        .spawn()?;
    Ok(Some(child))
}

fn main() {
    let runtime = RuntimeInfo {
        api_base_url: "http://127.0.0.1:8000".to_string(),
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
                if let Some(mut child) = state.0.lock().expect("backend state lock poisoned").take() {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running Pixelle desktop app");
}
