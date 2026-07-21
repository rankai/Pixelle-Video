import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/publishing/pub-4-batch-2-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/publishing/fixtures/pub-4-batch-2-entry-fixtures.json")


def test_pub4_batch2_entry_freezes_safe_handoff_and_projection():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "pub-4-batch-2-entry"
    assert contract["handoff"]["must_reuse_publish_facts"] is True
    assert set(contract["handoff"]["application_handoff_refs"]) == {"package_id", "artifact_id"}
    assert contract["handoff"]["recovery_route_refs"] == ["run_id"]
    assert contract["handoff"]["unknown_ref_policy"] == "reject"
    assert contract["handoff"]["unknown_field_policy"] == "reject"
    assert {"absolute_path", "access_token", "qr_payload", "browser_storage"} <= set(contract["handoff"]["forbidden_fields"])
    assert contract["projection"]["invalid_package_fail_closed"] is True
    assert contract["projection"]["event_order_is_monotonic"] is True
    assert contract["projection"]["duplicate_or_out_of_order_events_fail_closed"] is True
    assert set(contract["projection"]["forbidden_states"]) == {"published", "auto_published"}

    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    assert len(fixtures) == 8
    assert all(not fixture["valid"] for fixture in fixtures)
    assert {fixture["error"] for fixture in fixtures} == {
        "PUBLISH_REF_REQUIRED",
        "PUBLISH_REF_UNKNOWN",
        "PUBLISH_FACT_MISMATCH",
        "PUBLISH_PACKAGE_STALE",
        "PUBLISH_READ_FAILED",
        "PUBLISH_EVENT_ORDER_INVALID",
        "PUBLISH_HANDOFF_FIELD_FORBIDDEN",
        "PUBLISH_V2_DISABLED",
    }
    fixture_by_id = {fixture["id"]: fixture for fixture in fixtures}
    assert fixture_by_id["invalidated-package-new-run-rejected"]["valid"] is False
    assert fixture_by_id["invalidated-package-new-run-rejected"]["error"] == "PUBLISH_PACKAGE_STALE"
    assert fixture_by_id["flag-off-v2-request-rejected"]["valid"] is False
    assert fixture_by_id["flag-off-v2-request-rejected"]["error"] == "PUBLISH_V2_DISABLED"


def test_pub4_batch2_entry_forbids_external_actions_and_preserves_fallback():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["flag_off"] == {"v2_requests": 0, "legacy_fallback_reachable": True}
    assert contract["external_actions"] == {
        "browser": 0,
        "authorization": 0,
        "upload": 0,
        "final_publish": 0,
        "publish_run_create": 0,
        "platform_selection": 0,
        "business_writes": 0,
    }
