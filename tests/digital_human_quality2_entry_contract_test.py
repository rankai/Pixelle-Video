import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/contracts/app-center/digital-human-quality2-live-entry.contract.json"
FIXTURES = (
    ROOT / "docs/contracts/app-center/fixtures/digital-human-quality2-live-entry-fixtures.json"
)


def test_quality2_entry_freezes_single_call_budget_and_shared_inputs():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    budget = contract["provider_call_budget"]
    assert budget["image_stable"] == 1
    assert budget["video_natural"] == 1
    assert budget["retry_after_failure"] == "at_most_one_with_recorded_root_cause"
    assert contract["input_fixture"]["same_script_for_all_modes"] is True
    assert contract["input_fixture"]["same_tts_for_all_modes"] is True


def test_quality2_entry_requires_media_and_restart_evidence_before_accept():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert set(
        ["provider_task_id", "ffprobe", "subtitle_frames_25_50_75", "restart_state", "accept_state"]
    ).issubset(contract["evidence_required"])
    assert contract["acceptance"]["required_artifacts"] == [
        "video",
        "cover",
        "publish_copy",
        "spoken_script",
    ]


def test_quality2_entry_keeps_platform_and_final_publish_closed():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["safety"]["entry_provider_calls"] == 0
    assert contract["safety"]["entry_platform_actions"] == 0
    assert contract["acceptance"]["platform_actions"] == 0
    assert contract["acceptance"]["final_publish_clicked"] is False


def test_quality2_fixture_records_duplicate_and_unplanned_retry_failures():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    by_id = {item["id"]: item for item in fixtures}
    assert by_id["duplicate-provider-task"]["error"] == "DH_QUALITY_PROVIDER_DUPLICATE_TASK"
    assert by_id["retry-without-root-cause"]["error"] == "DH_QUALITY_RETRY_PLAN_REQUIRED"
    assert (
        by_id["missing-subtitles-or-spoken-script"]["error"]
        == "DH_QUALITY_FINAL_ARTIFACT_INCOMPLETE"
    )
