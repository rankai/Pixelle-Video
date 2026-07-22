"""Helpers for launching Playwright with a system Chromium binary."""

import os
import shutil


def get_chromium_executable_path() -> str | None:
    """Return a Chromium executable path when one is configured or installed."""
    configured = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if configured:
        return configured

    for candidate in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        path = shutil.which(candidate)
        if path:
            return path

    return None


def playwright_chromium_launch_options() -> dict[str, str]:
    """Return launch kwargs that make Playwright use system Chromium when available."""
    executable_path = get_chromium_executable_path()
    return {"executable_path": executable_path} if executable_path else {}
