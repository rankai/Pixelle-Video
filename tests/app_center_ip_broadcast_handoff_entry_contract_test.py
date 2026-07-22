import hashlib
import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/app-center/ip-broadcast-handoff-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/app-center/fixtures/ip-broadcast-handoff-entry-fixtures.json")


def _stable_json(value):
    if isinstance(value, list):
        return [_stable_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _stable_json(value[key]) for key in sorted(value)}
    return value


def _digest(value):
    payload = json.dumps(_stable_json(value), ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_ip_broadcast_handoff_entry_contract_freezes_facts_and_boundaries():
    contract = json.loads(CONTRACT_PATH.read_text())
    assert contract["contract_id"] == "ip-broadcast-handoff-entry"
    assert contract["facts"] == {
        "app_run_source": "app_center.sqlite",
        "publish_package_source": "publishing.sqlite3",
        "publish_package_ref_source": "app_center.sqlite",
        "legacy_session_source": "legacy_ip_broadcast_session_store",
    }
    canonical = contract["canonical_output_identity"]
    assert canonical["algorithm"] == "sha256"
    assert canonical["same_content_across_sources_must_match"] is True
    assert {"source_kind", "source_revision", "session_id", "app_run_id", "artifact_id", "absolute_path", "provider", "credentials"} <= set(canonical["excludes"])
    assert contract["legacy_session_recovery"]["implicit_cross_project_recovery"] is False
    assert contract["package_idempotency"]["source_kind_audit_only"] is True
    assert contract["three_source_handoff"]["modes"] == ["blank_project", "copywriting", "selected_title"]
    assert contract["external_actions"] == []
    assert "douyin_authorization_upload_or_final_publish" in contract["forbidden_in_entry"]


def test_ip_broadcast_handoff_entry_fixtures_cover_recovery_sources_fingerprint_and_idempotency():
    contract = json.loads(CONTRACT_PATH.read_text())
    fixtures = json.loads(FIXTURE_PATH.read_text())["fixtures"]
    by_id = {fixture["id"]: fixture for fixture in fixtures}
    required = {
        "legacy-session-explicit-claim-valid",
        "legacy-session-unbound-invalid",
        "legacy-session-cross-project-invalid",
        "legacy-session-source-drift-invalid",
        "blank-handoff-valid",
        "copywriting-handoff-valid",
        "selected-title-handoff-valid",
        "missing-source-invalid",
        "cross-project-version-invalid",
        "empty-title-invalid",
        "empty-publish-copy-invalid",
        "context-drift-invalid",
        "same-content-cross-source-fingerprint-valid",
        "temporary-fields-excluded-valid",
        "same-package-replay-valid",
        "same-package-ref-replay-valid",
        "new-version-invalidates-old-ref-valid",
        "duplicate-video-invalid",
        "partial-output-invalid",
        "mixed-source-invalid",
        "waiting-state-nonterminal-valid",
        "feature-flag-off-no-write-valid",
        "partial-retry-preserves-history-valid",
    }
    assert required <= by_id.keys()
    assert len(fixtures) == 24
    assert all(by_id[item]["valid"] for item in ("legacy-session-explicit-claim-valid", "blank-handoff-valid", "copywriting-handoff-valid", "selected-title-handoff-valid", "same-content-cross-source-fingerprint-valid", "same-package-replay-valid", "same-package-ref-replay-valid", "new-version-invalidates-old-ref-valid", "waiting-state-nonterminal-valid", "needs-review-nonterminal-valid", "feature-flag-off-no-write-valid", "partial-retry-preserves-history-valid"))
    assert not any(by_id[item]["valid"] for item in ("legacy-session-unbound-invalid", "legacy-session-cross-project-invalid", "legacy-session-source-drift-invalid", "missing-source-invalid", "cross-project-version-invalid", "empty-title-invalid", "empty-publish-copy-invalid", "context-drift-invalid", "duplicate-video-invalid", "partial-output-invalid", "mixed-source-invalid"))
    error_codes = set(contract["error_codes"])
    negative_ids = ("legacy-session-unbound-invalid", "legacy-session-cross-project-invalid", "legacy-session-source-drift-invalid", "missing-source-invalid", "cross-project-version-invalid", "empty-title-invalid", "empty-publish-copy-invalid", "context-drift-invalid", "duplicate-video-invalid", "partial-output-invalid", "mixed-source-invalid")
    assert {by_id[item]["error"] for item in negative_ids} <= error_codes
    for item in ("blank-handoff-valid", "copywriting-handoff-valid", "selected-title-handoff-valid"):
        fixture = by_id[item]
        assert {"project_id", "app_id", "app_version", "source_revision", "context_snapshot_id"} <= fixture.keys()
    assert {"session_id", "project_id", "app_id", "app_version", "app_run_id", "source_revision", "context_snapshot_id"} <= by_id["legacy-session-explicit-claim-valid"]["binding"].keys()
    canonical = by_id["same-content-cross-source-fingerprint-valid"]
    assert canonical["canonical_equal"] is True
    assert canonical["legacy"]["video_sha256"] == canonical["artifact"]["video_sha256"]
    assert canonical["legacy"]["cover_sha256"] == canonical["artifact"]["cover_sha256"]
    assert canonical["legacy"]["publish_copy"] == canonical["artifact"]["publish_copy"]
    assert _digest(canonical["canonical_payload"]) == canonical["expected_digest"]
    assert _digest({key: canonical["legacy"][key] for key in ("project_id", "publishing_schema_version", "video_sha256", "cover_sha256", "publish_copy")}) == canonical["expected_digest"]
    assert _digest({key: canonical["artifact"][key] for key in ("project_id", "publishing_schema_version", "video_sha256", "cover_sha256", "publish_copy")}) == canonical["expected_digest"]
    replay = by_id["same-package-replay-valid"]
    assert replay["first_package_id"] == replay["replay_package_id"]
    assert replay["first_fingerprint"] == replay["replay_fingerprint"]
    ref_replay = by_id["same-package-ref-replay-valid"]
    assert ref_replay["ref_ids_before"] == ref_replay["ref_ids_after"]
    assert ref_replay["active_ref_count_after_replay"] == 1
    changed = by_id["new-version-invalidates-old-ref-valid"]
    assert changed["old_artifact_version_ids"] != changed["new_artifact_version_ids"]
    assert changed["content_fingerprint_changed"] is True
    assert changed["old_package_invalidated"] is True
    assert changed["old_ref_invalidated"] is True
    assert by_id["feature-flag-off-no-write-valid"]["new_package_write"] is False
    assert contract["canonical_output_identity"]["inputs"][-1] == "publish_copy.canonical_content"


def test_ip_broadcast_handoff_entry_requires_explicit_accept_and_no_external_action():
    contract = json.loads(CONTRACT_PATH.read_text())
    fixtures = json.loads(FIXTURE_PATH.read_text())["fixtures"]
    handoff = contract["three_source_handoff"]
    assert handoff["completion_path"] == "isolated_execute_then_explicit_accept"
    assert handoff["waiting_states_never_complete"] is True
    assert all("external_actions" not in fixture or fixture.get("external_actions") == [] for fixture in fixtures)
    by_id = {fixture["id"]: fixture for fixture in fixtures}
    assert by_id["waiting-state-nonterminal-valid"]["completion_allowed"] is False
    assert by_id["needs-review-nonterminal-valid"]["completion_allowed"] is False
    assert by_id["feature-flag-off-no-write-valid"]["legacy_entry_preserved"] is True
