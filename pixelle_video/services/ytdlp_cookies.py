"""Cookie option helpers for yt-dlp based extractors."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BUILTIN_BROWSER_COOKIE_SPECS = (
    "chrome",
    "edge",
    "safari",
    "firefox",
    "brave",
    "vivaldi",
    "opera",
    "chromium",
    "whale",
)

_COOKIE_UNAVAILABLE_PATTERNS = (
    "could not find",
    "cookies database",
    "failed to load cookies",
    "no such file or directory",
    "profile",
    "does not exist",
)
_COOKIE_PERMISSION_PATTERNS = (
    "operation not permitted",
    "permission denied",
    "errno 1",
    "errno 13",
)


def ytdlp_cookie_options() -> list[list[str]]:
    """Return yt-dlp cookie argument candidates, starting with no-cookie mode."""
    options: list[list[str]] = [[]]
    for spec in ytdlp_cookie_specs():
        options.append(["--cookies-from-browser", spec])
    return options


def ytdlp_cookie_specs() -> list[str]:
    """Return browser cookie specs accepted by yt-dlp's --cookies-from-browser."""
    specs: list[str] = []
    seen: set[str] = set()

    for spec in _BUILTIN_BROWSER_COOKIE_SPECS:
        _append_cookie_spec(specs, seen, spec)

    for profile_path in _domestic_chromium_profile_paths():
        _append_cookie_spec(specs, seen, f"chrome:{profile_path}")

    return specs


def is_cookie_unavailable_error(message: str) -> bool:
    """Whether yt-dlp failed only because a browser/profile cookie DB is absent."""
    lower = message.lower()
    mentions_cookie = "cookies" in lower or "binarycookies" in lower
    if mentions_cookie and any(pattern in lower for pattern in _COOKIE_PERMISSION_PATTERNS):
        return True
    return mentions_cookie and "database" in lower and any(
        pattern in lower for pattern in _COOKIE_UNAVAILABLE_PATTERNS
    )


def _append_cookie_spec(specs: list[str], seen: set[str], spec: str):
    if spec in seen:
        return
    seen.add(spec)
    specs.append(spec)


def _domestic_chromium_profile_paths() -> list[Path]:
    roots = [path for path in _domestic_chromium_roots() if path.exists()]
    return _chromium_profile_paths_from_roots(roots)


def _domestic_chromium_roots() -> list[Path]:
    home = Path.home()
    if sys.platform == "darwin":
        support = home / "Library" / "Application Support"
        return [
            support / "360Chrome",
            support / "360ChromeX",
            support / "360极速浏览器",
            support / "360Browser",
            support / "QQBrowser",
            support / "Tencent" / "QQBrowser",
            support / "SogouExplorer",
        ]

    if sys.platform == "win32":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        roaming = Path(os.environ.get("APPDATA", ""))
        return [
            local / "360Chrome" / "Chrome" / "User Data",
            local / "360ChromeX" / "Chrome" / "User Data",
            local / "360se6" / "User Data",
            roaming / "360se6" / "User Data",
            local / "Tencent" / "QQBrowser" / "User Data",
            roaming / "Tencent" / "QQBrowser" / "User Data",
            local / "SogouExplorer" / "User Data",
        ]

    config = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))
    return [
        config / "360chrome",
        config / "qqbrowser",
        config / "sogouexplorer",
    ]


def _chromium_profile_paths_from_roots(roots: list[Path]) -> list[Path]:
    profiles: list[Path] = []
    seen: set[Path] = set()
    for root in roots:
        for cookie_db in _find_cookie_databases(root):
            profile = _profile_dir_from_cookie_db(cookie_db)
            if profile in seen:
                continue
            seen.add(profile)
            profiles.append(profile)
    return profiles


def _find_cookie_databases(root: Path, max_depth: int = 4) -> list[Path]:
    cookie_dbs: list[Path] = []
    root_depth = len(root.parts)
    for current_root, dirs, files in os.walk(root):
        current_path = Path(current_root)
        depth = len(current_path.parts) - root_depth
        if depth >= max_depth:
            dirs[:] = []
        if "Cookies" in files:
            cookie_dbs.append(current_path / "Cookies")
    return cookie_dbs


def _profile_dir_from_cookie_db(cookie_db: Path) -> Path:
    if cookie_db.parent.name == "Network":
        return cookie_db.parent.parent
    return cookie_db.parent
