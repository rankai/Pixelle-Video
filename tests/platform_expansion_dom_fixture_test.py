import hashlib
import json
from pathlib import Path

from pixelle_video.services.publish.platform_profiles import get_platform_profile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/contracts/publishing/fixtures/platform-expansion-dom-manifest.json"


def test_three_platform_dom_fixture_manifest_is_complete_and_redacted():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest["platforms"]) == {"kuaishou", "shipinhao", "xiaohongshu"}
    for platform, entry in manifest["platforms"].items():
        profile = get_platform_profile(platform)
        assert entry["entry_url"] == profile.entry_url
        assert entry["adapter_version"] == profile.adapter_version
        assert {item["state"] for item in entry["fixtures"]} >= {
            "signed_out", "captcha", "loading", "unknown", "editor_ready"
        }
        for fixture in entry["fixtures"]:
            path = ROOT / fixture["path"]
            body = path.read_text(encoding="utf-8")
            assert path.is_file()
            assert all(marker in body for marker in fixture["required_markers"])
            assert "cookie" not in body.lower()
            assert "qr" not in body.lower()
            assert "signed" not in body.lower() or "signed_in" in body.lower() or "signed_out" in body.lower()
            assert fixture["sha256"] == f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def test_platform_profiles_match_editor_fixture_contract():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for platform, entry in manifest["platforms"].items():
        body = (ROOT / next(item["path"] for item in entry["fixtures"] if item["state"] == "editor_ready")).read_text(encoding="utf-8")
        profile = get_platform_profile(platform)
        assert any(selector.split("[")[0] in body for selector in profile.title_selectors)
        assert any(selector.split("[")[0] in body for selector in profile.description_selectors)
        assert "data-media-id" in body
        assert "data-testid=\"cover-preview\"" in body
        assert "data-guard=\"deny\"" in body
        assert any("input[type='file']" in selector for selector in profile.video_input_selectors)
        assert any("input[type='file']" in selector for selector in profile.cover_input_selectors)
