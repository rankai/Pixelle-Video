"""Contract checks for the bounded PG-G Douyin live-smoke evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/reviews/application-publishing-program/qa/PG-G-douyin-live-smoke-2026-07-20.json"
SCREENSHOT = ROOT / "docs/reviews/application-publishing-program/qa/PG-G-douyin-live-smoke-2026-07-20.png"


def test_pg_g_live_smoke_evidence_is_complete_and_redacted():
    evidence = json.loads(EVIDENCE.read_text())

    assert evidence["stage"] == "PUB-DOUYIN/PUB-3"
    assert evidence["gate"] == "PG-G"
    assert evidence["status"] == "live_smoke_passed_with_boundary"
    assert evidence["login"]["login_markers"] == []
    assert evidence["login"]["third_party_challenge"] is False
    assert evidence["media"]["upload_observed"] is True
    assert evidence["media"]["processing_completed"] is True
    assert evidence["field_readback"]["title"] == "门店短视频测试标题"
    assert evidence["field_readback"]["topics"] == ["#问答"]
    assert evidence["cover"]["vertical_editor_complete_clicked"] is True
    assert evidence["cover"]["horizontal_cover_skip_clicked"] is True
    assert evidence["final_action_guard"]["publish_button_clicked"] is False
    assert evidence["final_action_guard"]["final_publish"] == "not_attempted"
    assert evidence["privacy"]["account_identifier_recorded"] is False
    assert evidence["privacy"]["signed_url_recorded"] is False
    assert SCREENSHOT.exists()
    expected_sha = evidence["screenshot"]["sha256"].removeprefix("sha256:")
    assert hashlib.sha256(SCREENSHOT.read_bytes()).hexdigest() == expected_sha
    assert SCREENSHOT.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"

    serialized = json.dumps(evidence, ensure_ascii=False).lower()
    assert "sign_token" not in serialized
    assert "x-orig-authkey" not in serialized
    assert "cookie" not in serialized
