import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/contracts/app-center/digital-human-dual-mode-recovery.contract.json"
FIXTURES = (
    ROOT / "docs/contracts/app-center/fixtures/digital-human-dual-mode-recovery-fixtures.json"
)


def test_recovery_contract_covers_restart_failure_and_acceptance_matrix():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    ids = {item["id"] for item in contract["recovery_matrix"]}
    assert {
        "provider-not-created-before-restart",
        "provider-running-before-restart",
        "provider-success-before-artifact-registration",
        "needs-review-restart",
        "failed-once",
        "balance-insufficient",
        "provider-timeout",
        "provider-no-video",
        "local-file-missing",
        "subtitle-or-cover-failure",
        "artifact-tampered-before-accept",
        "repeated-accept",
        "mode-switch-old-pending",
        "final-publish",
    }.issubset(ids)
    assert contract["artifact_acceptance"]["required_types"] == [
        "video",
        "cover",
        "publish_copy",
        "spoken_script",
    ]


def test_recovery_contract_keeps_external_actions_closed():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["safety"] == {
        "provider_calls_at_entry": 0,
        "platform_actions": 0,
        "final_publish_clicked": False,
    }


def test_recovery_fixtures_use_stable_errors_and_no_publish():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    by_id = {item["id"]: item for item in fixtures}
    assert by_id["asset-revision-change"]["expected_error"] == "DH_QUALITY_FIXED_INPUT_MUTATED"
    assert (
        by_id["accept-incomplete-artifacts"]["expected_error"]
        == "DH_QUALITY_FINAL_ARTIFACT_INCOMPLETE"
    )
    assert (
        by_id["artifact-tampered-before-accept"]["expected_error"]
        == "ARTIFACT_FINGERPRINT_MISMATCH"
    )
    assert by_id["final-publish"]["input"]["final_publish_clicked"] is False
