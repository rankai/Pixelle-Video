import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/contracts/publishing/program-rollout-entry.contract.json"
FIXTURES = ROOT / "docs/contracts/publishing/fixtures/program-rollout-entry-fixtures.json"


def test_program_rollout_entry_contract_freezes_scope_and_gate():
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "program-rollout-entry"
    assert contract["stage"] == "PROGRAM-ROLLOUT"
    assert contract["upstream_gates"]["required"] == [f"PG-{letter}" for letter in "ABCDEFGHIJK"]
    assert contract["upstream_gates"]["all_required"] is True
    assert all(contract["required_evidence"].values())
    assert all(contract["forbidden"].values())
    assert contract["feature_flags"]["fail_closed_unknown_or_conflicting"] is True
    required_flags = set(contract["feature_flags"]["required"])
    assert {
        "VITE_APP_CENTER_SHELL",
        "VITE_CONTENT_PROJECTS",
        "VITE_CONTENT_APPS",
        "VITE_DOUYIN_CAROUSEL",
        "VITE_APP_CENTER_DIGITAL_HUMAN",
        "VITE_APP_CENTER_NEW_NAV",
        "VITE_PUBLISH_CENTER_V2",
        "PIXELLE_APP_CENTER_CONTENT_APPS",
        "PIXELLE_APP_CENTER_DOUYIN_CAROUSEL",
        "PIXELLE_APP_CENTER_DIGITAL_HUMAN",
        "PIXELLE_PUBLISH_V2_ENABLED",
    } <= required_flags
    assert contract["feature_flags"]["canonical_env"]["publishV2"] == {
        "backend_env": "PIXELLE_PUBLISH_V2_ENABLED",
        "desktop_env": "VITE_PUBLISH_CENTER_V2",
        "default": False,
    }
    assert contract["feature_flags"]["alias_policy"]["VITE_PUBLISH_V2_ENABLED"] == {
        "canonical": "VITE_PUBLISH_CENTER_V2",
        "action": "normalize_before_build",
    }
    assert contract["feature_flags"]["matrix_cases"] == [
        "all_off_legacy",
        "douyin_gray_only",
        "unknown_flag_fail_closed",
        "conflicting_v2_off_platform_on",
    ]
    assert contract["soak_requirements"]["each_cycle_requires"] == [
        "health",
        "port_released",
        "run_state_reconciled",
        "external_actions_zero",
    ]
    assert contract["performance_requirements"]["sample_count_per_fixture"] == 10
    assert set(contract["privacy_requirements"]["forbidden_fields"]) >= {
        "api_key",
        "authorization",
        "qr",
        "account_nickname",
        "profile_path",
        "signed_url",
        "media_content",
    }
    assert contract["rollback_requirements"]["upload_count_delta"] == 0
    assert contract["stable_observation_window"]["minimum_hours"] == 1
    assert contract["exit_gate"] == {
        "requires_independent_six_dimension_review": True,
        "p0_p1_must_be_zero": True,
        "stable_observation_window_required": True,
        "only_then_may_close_pg_l": True,
    }


def test_program_rollout_entry_fixture_matrix_is_explicit():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))["fixtures"]
    by_id = {fixture["id"]: fixture for fixture in fixtures}
    assert len(by_id) == 15
    assert {
        "pg-k-prerequisite",
        "flag-matrix-v2-off-v1-fallback",
        "flag-matrix-douyin-gray-only",
        "flag-matrix-unknown-fail-closed",
        "flag-canonical-alias-policy",
        "redacted-telemetry",
        "packaged-lifecycle",
        "restart-and-run-soak",
        "performance-fixture-baseline",
        "bidirectional-rollback",
        "navigation-scale-and-windows-boundary",
        "stable-observation-window",
        "release-policy-boundary",
        "final-publish-blocked",
        "real-platform-success-claim",
    } == set(by_id)
    assert all(item["valid"] for item in by_id.values() if item["id"] != "real-platform-success-claim")
    assert by_id["real-platform-success-claim"]["error"] == "FORBIDDEN_BOUNDARY"
    assert by_id["restart-and-run-soak"]["duplicate_uploads"] == 0
    assert by_id["restart-and-run-soak"]["crash_recovery_cases"] == 2
    assert by_id["redacted-telemetry"]["local_only"] is True
    assert by_id["bidirectional-rollback"]["active_and_waiting_runs_preserved"] is True
    assert by_id["stable-observation-window"]["minimum_hours"] == 1
    assert by_id["flag-canonical-alias-policy"]["aliases"]["VITE_PUBLISH_V2_ENABLED"] == "VITE_PUBLISH_CENTER_V2"
    assert by_id["release-policy-boundary"]["douyin"]["release_state"] == "gray"
    assert by_id["release-policy-boundary"]["kuaishou"]["release_state"] == "unchanged"
    assert by_id["final-publish-blocked"]["final_publish_click_count"] == 0
