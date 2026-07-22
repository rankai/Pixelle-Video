import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/publishing/pub-5-e2e-douyin-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/publishing/fixtures/pub-5-e2e-douyin-entry-fixtures.json")


def test_pub_5_entry_freezes_real_e2e_and_final_action_boundary():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "pub-5-e2e-douyin-entry"
    assert all(contract["required_evidence"].values())
    assert all(contract["forbidden"].values())
    assert contract["exit_gate"]["terminal_state_must_be_waiting_for_human"] is True
    assert contract["exit_gate"]["final_publish_click_count_must_be_zero"] is True


def test_pub_5_entry_fixture_matrix_keeps_user_pause_points_explicit():
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    by_id = {fixture["id"]: fixture for fixture in fixtures}
    assert {
        "production-session-artifact-chain",
        "real-account-profile-isolation",
        "run-idempotency-and-hash",
        "upload-field-cover-readback",
        "waiting-for-human-terminal",
        "restart-no-duplicate-upload",
        "final-action-guard-deny",
        "manual-final-publish-separate",
        "provider-blocker-truthful",
        "final-publish-click",
        "silent-qr-authorization",
        "fixture-fabricates-cloud-production",
    } == set(by_id)
    assert by_id["final-publish-click"]["error"] == "FORBIDDEN_AUTOMATIC_ACTION"
    assert by_id["silent-qr-authorization"]["error"] == "USER_AUTH_REQUIRED"
    assert by_id["fixture-fabricates-cloud-production"]["error"] == "PRODUCTION_SOURCE_UNVERIFIED"
