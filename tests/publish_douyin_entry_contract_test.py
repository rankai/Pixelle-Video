"""PUB-3 Entry contract: local fixtures and action boundaries only."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pixelle_video.services.publish.browser_runtime import CREATOR_UPLOAD_URLS
from pixelle_video.services.publish.platforms.douyin import DouyinPublisher

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "tests/fixtures/publishing"


class _NoopRuntime:
    async def launch_persistent_context(self, *args, **kwargs):
        raise AssertionError("PUB-3 Entry must not launch a real browser")


def _read_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_douyin_fixture_inventory_is_complete_and_deterministic():
    manifest = _read_json("tests/fixtures/publishing/manifest.json")
    assert manifest["platform"] == "douyin"
    assert manifest["coverage_scope"].startswith("state markers")
    fixtures = manifest["fixtures"]
    assert len(fixtures) == 13
    assert {item["state"] for item in fixtures} >= {
        "signed_in", "signed_out", "captcha", "loading", "network_error",
        "upload_entry", "uploading", "processing", "editor_ready", "cover_modal",
        "cover_error", "waiting_for_human", "unknown",
    }
    assert len({item["fixture_id"] for item in fixtures}) == len(fixtures)
    for item in fixtures:
        path = FIXTURE_ROOT / item["path"]
        assert path.is_file()
        assert "account" not in path.read_text(encoding="utf-8").lower()
        assert "cookie" not in path.read_text(encoding="utf-8").lower()
        assert "qr" not in path.read_text(encoding="utf-8").lower()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert item["sha256"] == f"sha256:{digest}"
        body = path.read_text(encoding="utf-8")
        assert all(marker in body for marker in item["required_markers"])


def test_douyin_entry_freezes_platform_registration_and_guard_boundaries():
    adapter_contract = _read_json("docs/contracts/publishing/douyin-adapter-entry.contract.json")
    assert adapter_contract["platform"] == "douyin"
    assert adapter_contract["adapter_version"] == "douyin-entry@1"
    assert adapter_contract["browser_runtime"] == "playwright"
    assert adapter_contract["state_mapping"]["signed_out"] == "waiting_for_login"
    assert adapter_contract["state_mapping"]["captcha"] == "waiting_for_human"
    assert adapter_contract["state_mapping"]["unknown"] == "needs_attention"
    assert adapter_contract["external_action_policy"]["final_publish"] == "never_automated"
    guard = _read_json("docs/contracts/publishing/final-action-guard.matrix.json")
    allowed = {item["action_id"] for item in guard["allowed"]}
    denied = {item["action_id"] for item in guard["denied"]}
    assert allowed == {"upload_media", "fill_title", "fill_description", "select_topic", "save_cover"}
    assert {"publish", "confirm_publish", "submit", "unknown", "coordinate_click"} <= denied
    assert guard["default"] == "deny"
    assert guard["stop_state"] == "waiting_for_human"
    assert guard["deny_error_code"] == "FINAL_ACTION_BLOCKED"
    assert CREATOR_UPLOAD_URLS["douyin"].startswith("https://creator.douyin.com/")
    publisher = DouyinPublisher(_NoopRuntime())
    assert publisher.platform == "douyin"
    assert not hasattr(publisher, "publish")
    assert not hasattr(publisher, "submit")
