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
```

## v1 Scope

- IP broadcast workflow only.
- Home and History remain in Streamlit.
- The backend listens on `127.0.0.1`.
- React talks to FastAPI through the desktop token header.
- Windows installer is the first release target.
