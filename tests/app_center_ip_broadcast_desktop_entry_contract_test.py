import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/app-center/ip-broadcast-desktop-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/app-center/fixtures/ip-broadcast-desktop-entry-fixtures.json")
QA_EVIDENCE_PATH = Path("docs/reviews/application-publishing-program/qa/AC-5-batch-7-local-gray-cycle-2026-07-20.json")


def test_desktop_entry_contract_freezes_routes_flags_sources_and_restart_policy():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "ip-broadcast-desktop-entry"
    assert contract["feature_flag"] == "digitalHumanInAppCenter"
    assert contract["defaults"]["backend_feature_flag"] is False
    assert contract["defaults"]["desktop_rollout_flag"] is False
    assert contract["route_ownership"]["legacy_route"]["path"] == "/ip"
    assert contract["route_ownership"]["legacy_route"]["preserved_when_new_flag_off"] is True
    assert contract["route_ownership"]["new_route"]["path"] == "/apps/digital-human-video"
    assert contract["route_ownership"]["new_route"]["must_not_alias_legacy_route"] is True
    assert contract["registry_projection"]["frontend_must_not_override_backend_readiness"] is True
    assert "backend_feature_flag=true" in contract["route_ownership"]["new_route"]["requires"]
    assert "backend_feature_flag=true" in contract["registry_projection"]["actionable_only_when"]
    assert "digitalHumanInAppCenter" in contract["registry_projection"]["backend_flag_to_manifest_mapping"]
    assert contract["source_projection"]["exactly_one_source_mode"] is True
    assert contract["response_projection"]["waiting_states_never_complete"] is True
    persistence = contract["desktop_persistence"]
    assert persistence["legacy_storage_keys_are_separate"] is True
    assert "read_existing_app_run_id_before_create" in persistence["restart_recovery"]
    assert "read_pending_idempotency_before_create" in persistence["restart_recovery"]
    assert "POST_new_run_for_existing_pointer" in persistence["restart_must_not"]
    assert persistence["pending_submission"]["persist_before_post"] is True
    assert "source_artifact_id" in persistence["pending_submission"]["fields"]
    assert persistence["pending_submission"]["restart_reuses_pending_key_only_on_same_payload"] is True


def test_desktop_entry_fixtures_cover_flag_matrix_three_sources_and_restart():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    by_id = {fixture["id"]: fixture for fixture in fixtures}
    required = {
        "flag-off-legacy-preserved",
        "flag-on-ready-card-actionable",
        "backend-disabled-non-actionable",
        "blank-source-run",
        "copywriting-source-run",
        "selected-title-source-run",
        "missing-copywriting-index",
        "cross-project-selected-title",
        "waiting-projection-nonterminal",
        "restart-reuses-binding",
        "local-gray-cycle-no-external-action",
        "final-publish-blocked",
    }
    assert set(by_id) == required
    assert all(by_id[item]["valid"] for item in required - {"missing-copywriting-index", "cross-project-selected-title"})
    assert not by_id["missing-copywriting-index"]["valid"]
    assert not by_id["cross-project-selected-title"]["valid"]
    assert by_id["missing-copywriting-index"]["error"] in contract["error_codes"]
    assert by_id["cross-project-selected-title"]["error"] in contract["error_codes"]
    assert by_id["final-publish-blocked"]["error"] == "FINAL_ACTION_BLOCKED"
    for mode in ("blank-source-run", "copywriting-source-run", "selected-title-source-run"):
        assert by_id[mode]["source_mode"] in contract["source_projection"]["modes"]
        assert by_id[mode]["external_actions"] == []
    restart = by_id["restart-reuses-binding"]
    assert restart["before_restart"]["app_run_id"] == restart["after_restart"]["app_run_id"]
    assert restart["before_restart"]["session_id"] == restart["after_restart"]["session_id"]
    assert restart["after_restart"]["new_post_runs"] == 0
    assert restart["after_restart"]["new_sessions"] == 0


def test_local_gray_cycle_is_explicitly_bounded_before_any_real_provider_or_publish():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    gray = next(item for item in fixtures if item["id"] == "local-gray-cycle-no-external-action")
    evidence = contract["gray_cycle_evidence"]
    assert set(gray["source_modes"]) == {"blank_project", "copywriting", "selected_title"}
    assert gray["terminal_before_accept"] == "needs_review"
    assert gray["explicit_accept"] is True
    assert gray["external_provider_calls"] == 0
    assert gray["platform_writes"] == 0
    assert gray["final_publish_clicks"] == 0
    assert {
        "project_id",
        "app_run_id",
        "session_id",
        "source_revision",
        "before_after_restart",
        "artifact_ids",
        "external_action_counters",
        "screenshot_or_dom_snapshot_sha256",
    } <= gray.keys()
    assert gray["external_action_counters"] == {"provider_calls": 0, "platform_writes": 0, "final_publish_clicks": 0}
    assert "real_browser_or_douyin_authorization" in evidence["does_not_prove"]
    assert "real_provider_or_browser_action" in contract["forbidden_in_batch"]


def test_local_gray_cycle_qa_evidence_contains_required_binding_and_flag_fields():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    qa = json.loads(QA_EVIDENCE_PATH.read_text(encoding="utf-8"))
    assert set(contract["gray_cycle_evidence"]["must_include"]) <= {
        "flag_values",
        "project_id",
        "app_run_id",
        "session_id",
        "source_mode",
        "source_revision",
        "before_after_restart",
        "artifact_ids",
        "external_action_counters",
        "screenshot_or_dom_snapshot_sha256",
    }
    assert qa["flag_values"] == {
        "desktop_rollout_flag": True,
        "backend_feature_flag": True,
        "isolated_executor_flag": True,
        "external_provider_enabled": False,
        "final_publish_enabled": False,
    }
    assert qa["before_after_restart"]["before"]["app_run_id"] == qa["before_after_restart"]["after"]["app_run_id"]
    assert qa["before_after_restart"]["before"]["session_id"] == qa["before_after_restart"]["after"]["session_id"]
    assert set(qa["source_mode"]) == {"blank_project", "copywriting", "selected_title"}
    assert qa["artifact_ids"] == qa["artifacts"]["artifact_ids"]
    assert qa["external_action_counters"] == {"provider_calls": 0, "browser_actions": 0, "platform_writes": 0, "final_publish_clicks": 0}
    assert qa["screenshot_or_dom_snapshot_sha256"].startswith("sha256:")
