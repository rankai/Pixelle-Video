from pathlib import Path

from pixelle_video.services.ytdlp_cookies import (
    _chromium_profile_paths_from_roots,
    is_cookie_unavailable_error,
    ytdlp_cookie_options,
)


def test_cookie_options_include_more_common_browsers():
    specs = [args[-1] for args in ytdlp_cookie_options() if args]

    assert specs[:9] == [
        "chrome",
        "edge",
        "safari",
        "firefox",
        "brave",
        "vivaldi",
        "opera",
        "chromium",
        "whale",
    ]


def test_cookie_unavailable_error_detects_missing_firefox_profile():
    message = (
        "ERROR: could not find firefox cookies database in "
        "'/Users/nickfury/Library/Application Support/Firefox/Profiles'"
    )

    assert is_cookie_unavailable_error(message)


def test_cookie_unavailable_error_detects_macos_safari_permission_denied():
    message = (
        "ERROR: [Errno 1] Operation not permitted: "
        "'/Users/nickfury/Library/Containers/com.apple.Safari/Data/Library/"
        "Cookies/Cookies.binarycookies'"
    )

    assert is_cookie_unavailable_error(message)


def test_chromium_profile_paths_detect_network_cookie_db(tmp_path: Path):
    profile = tmp_path / "360Chrome" / "Default"
    network = profile / "Network"
    network.mkdir(parents=True)
    (network / "Cookies").write_text("", encoding="utf-8")

    assert _chromium_profile_paths_from_roots([tmp_path / "360Chrome"]) == [profile]
