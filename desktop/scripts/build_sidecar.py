"""Build the Pixelle FastAPI sidecar for Tauri packaging."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN_DIR = ROOT / "desktop" / "src-tauri" / "bin"


def target_triple() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if system == "windows":
        return "x86_64-pc-windows-msvc"
    if system == "darwin":
        return (
            "aarch64-apple-darwin"
            if "arm" in machine or "aarch64" in machine
            else "x86_64-apple-darwin"
        )
    return "x86_64-unknown-linux-gnu"


def executable_name() -> str:
    suffix = ".exe" if platform.system().lower() == "windows" else ""
    return f"pixelle-api-{target_triple()}{suffix}"


def data_separator() -> str:
    """Return PyInstaller's platform-specific ``source:destination`` separator."""

    return ";" if platform.system().lower() == "windows" else ":"


def main() -> int:
    pyinstaller = shutil.which("pyinstaller")
    if not pyinstaller:
        print("PyInstaller is required. Install it in the uv environment first.", file=sys.stderr)
        return 1

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    build_dir = ROOT / "build" / "desktop-sidecar"
    dist_dir = ROOT / "dist" / "desktop-sidecar"
    command = [
        pyinstaller,
        "--clean",
        "--onefile",
        "--name",
        "pixelle-api",
        "--distpath",
        str(dist_dir),
        "--workpath",
        str(build_dir),
        # The frozen API constructs local repositories during startup.  Those
        # repositories load their SQLite schemas from the contracts directory
        # at runtime, so it must be present inside PyInstaller's extraction
        # root rather than only in the source checkout.
        "--add-data",
        f"{ROOT / 'docs' / 'contracts'}{data_separator()}docs/contracts",
        str(ROOT / "api" / "app.py"),
    ]
    subprocess.run(command, check=True, cwd=ROOT)

    built_name = "pixelle-api.exe" if platform.system().lower() == "windows" else "pixelle-api"
    source = dist_dir / built_name
    target = BIN_DIR / executable_name()
    shutil.copy2(source, target)
    print(f"Sidecar written to {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
