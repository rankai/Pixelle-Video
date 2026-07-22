# Pixelle Video Desktop

Tauri + React desktop shell for the IP broadcast workflow.

## Development

Prerequisites:

- Node.js 22+
- npm 10+
- Rust + Cargo
- Python 3.11+
- uv
- FFmpeg
- Playwright Chromium

Install frontend dependencies:

```bash
npm install
```

Run React only:

```bash
npm run dev
```

For browser-only development, start the API on the standalone browser port
and point Vite at it explicitly (the frontend probes this port when
`VITE_API_BASE_URL` is omitted):

```bash
PIXELLE_ASSET_CENTER_V2=true uv run python api/app.py --host 127.0.0.1 --port 8100
VITE_API_BASE_URL=http://127.0.0.1:8100 VITE_ASSET_CENTER_V2=true npm run dev -- --host 127.0.0.1 --port 1420
```

The Tauri shell is different: in debug mode it uses the standalone API on
`127.0.0.1:8100` by default, matching the browser workflow; in a release build
it starts the bundled sidecar on `127.0.0.1:8000`. Set
`PIXELLE_API_BASE_URL` to override either mode.

The V2 asset center is enabled by default after Gate C. Set
`PIXELLE_ASSET_CENTER_V2=false` and `VITE_ASSET_CENTER_V2=false` together for a
rollback rehearsal. The shell forwards the flag to the sidecar, maps packaged
`templates/` and `workflows/` to stable resource paths, and stores release
data/config under the app data directory instead of inside the `.app` bundle.

Run Tauri:

```bash
npm run tauri:dev
```

## Sidecar

The desktop app expects a bundled Python API sidecar named `pixelle-api`.

Build it from the repository root:

```bash
uv pip install -e ".[desktop]"
uv run python desktop/scripts/build_sidecar.py
```

On Windows, the script writes the binary to:

```text
desktop/src-tauri/bin/pixelle-api-x86_64-pc-windows-msvc.exe
```

On macOS/Linux, the binary name follows Tauri sidecar target naming. The sidecar starts `api.app` with:

```text
PIXELLE_DESKTOP_MODE=1
PIXELLE_DESKTOP_TOKEN=<per-launch-token>
PIXELLE_DESKTOP_ORIGIN=tauri://localhost
PIXELLE_VIDEO_ROOT=<app-data-directory>
PIXELLE_CONFIG_PATH=<app-data-directory>/config.yaml
PIXELLE_ASSET_CENTER_V2=<rollout-flag>
```

## v1 Scope

- IP broadcast workflow only.
- Home and History remain in Streamlit.
- The backend listens on `127.0.0.1`.
- React talks to FastAPI through the desktop token header.
- Windows installer is the first release target.
