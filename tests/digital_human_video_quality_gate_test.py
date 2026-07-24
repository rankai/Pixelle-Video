import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = (
    ROOT
    / "docs/reviews/application-publishing-program/qa/DH-QUALITY-2-video-live-gate-2026-07-24.json"
)


def _load():
    return json.loads(EVIDENCE.read_text(encoding="utf-8"))


def test_video_live_quality_gate_has_single_provider_call_and_complete_outputs():
    evidence = _load()
    assert evidence["stage"] == "DH-QUALITY-2"
    assert evidence["gate"] == "PG-DH-E"
    assert evidence["status"] == "passed_with_boundary"
    provider = evidence["provider"]
    assert provider["workflow_profile"] == "video_lipsync/natural"
    assert provider["task_status"] == "succeeded"
    assert provider["task_create_count"] == 1
    assert provider["retry_count"] == 0
    assert provider["previous_task_ids"] == []
    assert all(evidence["run"]["artifacts"].values())


def test_video_live_quality_gate_captures_visual_and_technical_acceptance():
    evidence = _load()
    media = evidence["media"]
    probe = media["ffprobe"]
    assert probe["status"] == "ok"
    assert (probe["width"], probe["height"]) == (1080, 1920)
    assert probe["video_codec"] == "h264"
    assert probe["audio_codec"] == "aac"
    subtitle = media["subtitle"]
    assert subtitle["preset"] == "readable_v2"
    assert subtitle["burned_in"] is True
    assert subtitle["readability"] == "passed"
    assert evidence["visual_review"]["verdict"] == "passed_with_boundary"
    assert all(value.startswith("pass") for value in evidence["visual_review"]["criteria"].values())


def test_video_live_quality_gate_keeps_human_publish_boundary_and_no_machine_paths():
    evidence = _load()
    assert evidence["safety"] == {
        "platform_actions": 0,
        "final_publish_clicked": False,
        "default_publish_click": False,
        "accept_is_still_human_confirmed": True,
    }
    serialized = EVIDENCE.read_text(encoding="utf-8")
    assert "/private/" not in serialized
    assert "/Users/" not in serialized
    assert "api_key" not in serialized.lower()
    decision = evidence["release_decision"]
    assert decision["video_lipsync_natural"] == "stable"
    assert decision["availability"] == "stable_non_default"
    assert decision["default_mode"] is False
    assert decision["image_talking_natural"] == "candidate"
