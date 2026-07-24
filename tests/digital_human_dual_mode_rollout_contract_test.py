import json
from pathlib import Path

from pixelle_video.app_center.digital_human_feature_gate import evaluate_digital_human_feature_gate
from pixelle_video.app_center.digital_human_workflow_catalog import resolve_workflow_profile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/contracts/app-center/digital-human-dual-mode-rollout.contract.json"
FIXTURES = ROOT / "docs/contracts/app-center/fixtures/digital-human-dual-mode-rollout-fixtures.json"


def test_rollout_contract_freezes_joint_flags_and_safe_defaults():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    flags = contract["feature_flags"]
    assert flags["default"] is False
    assert flags["joint_gate"] is True
    assert flags["desktop_only_cannot_bypass_backend"] is True
    assert flags["backend_off_preserves_legacy_route"] is True
    assert contract["safety"]["final_publish_clicked"] is False
    assert contract["release_states"]["video_lipsync_natural"] == "stable"
    assert contract["release_states"]["video_default_mode"] is False
    assert contract["release_states"]["image_talking_stable"] == "pilot_verified"


def test_rollout_fixtures_match_backend_desktop_gate():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    for fixture in fixtures[:-1]:
        gate = evaluate_digital_human_feature_gate(
            backend_flag=fixture["backend_flag"],
            desktop_flag=fixture["desktop_flag"],
            backend_ready=fixture["backend_ready"],
            desktop_ready=fixture["desktop_ready"],
        )
        assert gate.v2_enabled is fixture["v2_enabled"]
        assert gate.legacy_route_available is fixture["legacy_route_available"]


def test_video_workflow_is_stable_but_not_default_after_live_quality_gate():
    fixture = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"][-1]
    assert fixture["id"] == "video-stable-non-default"
    assert fixture["available"] is True
    assert fixture["default"] is False
    assert (
        resolve_workflow_profile("video_lipsync", "natural", require_released=True).release_state
        == "stable"
    )
