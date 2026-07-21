import hashlib

import pytest

from pixelle_video.services.publish.core_models import MediaManifest
from pixelle_video.services.publish.media_preflight import (
    MediaPreflightError,
    preflight_media,
    verify_manifest,
)


def test_preflight_accepts_trusted_video_and_detects_hash_change(tmp_path):
    path = tmp_path / "demo.mp4"
    path.write_bytes(b"00000000ftypisom")
    manifest = preflight_media(path, kind="video", roots=(tmp_path,))
    assert manifest.path_token.startswith("asset_")
    assert manifest.sha256 == "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(b"changed")
    with pytest.raises(MediaPreflightError, match="MEDIA_HASH_MISMATCH"):
        verify_manifest(path, manifest, roots=(tmp_path,))


def test_preflight_rejects_untrusted_path_invalid_media_and_symlink_escape(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("not media")
    with pytest.raises(MediaPreflightError, match="MEDIA_PATH_UNTRUSTED"):
        preflight_media(outside, kind="video", roots=(tmp_path / "trusted",))

    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not an mp4")
    with pytest.raises(MediaPreflightError, match="MEDIA_PROBE_FAILED"):
        preflight_media(invalid, kind="video", roots=(tmp_path,))

    trusted = tmp_path / "trusted"
    trusted.mkdir()
    link = trusted / "link.mp4"
    inside = trusted / "inside.mp4"
    inside.write_bytes(b"00000000ftypisom-inside")
    link.symlink_to(inside)
    with pytest.raises(MediaPreflightError):
        preflight_media(link, kind="video", roots=(trusted,))


def test_preflight_rejects_invalid_manifest_token_and_cover_magic(tmp_path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"bad")
    with pytest.raises(MediaPreflightError, match="MEDIA_PROBE_FAILED"):
        preflight_media(cover, kind="cover", roots=(tmp_path,))
    valid_cover = tmp_path / "cover2.png"
    valid_cover.write_bytes(b"\x89PNG\r\n\x1a\ncontent")
    with pytest.raises(MediaPreflightError, match="MEDIA_PATH_TOKEN_INVALID"):
        preflight_media(valid_cover, kind="cover", path_token="../escape", roots=(tmp_path,))
    assert MediaManifest(sha256="sha256:" + "b" * 64, size_bytes=1, mime_type="image/png", path_token="asset_cover")
