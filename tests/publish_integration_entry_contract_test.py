import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/publishing/pub-4-integration-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/publishing/fixtures/pub-4-integration-entry-fixtures.json")


def test_pub4_contract_freezes_single_publish_center_and_facts():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "pub-4-integration-entry"
    assert contract["route"] == {
        "canonical_path": "/publish",
        "hash_path": "#/publish",
        "single_publish_center": True,
        "legacy_publish_workspace_must_not_orchestrate": True,
    }
    assert contract["facts"] == {
        "package": "PublishPackage",
        "package_ref": "publish_package_ref",
        "run": "PublishRun",
        "account": "AccountProfile",
        "project_artifact_handoff": "ArtifactVersion",
    }
    assert "published" in contract["forbidden_projection_states"]
    assert contract["flows"]["first_publish"]["terminal"] == "waiting_for_human"


def test_pub4_fixtures_cover_first_repeat_recovery_failure_and_invalidation():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    by_id = {fixture["id"]: fixture for fixture in fixtures}
    positive_ids = {
        "first-publish-human-handoff",
        "repeat-publish-idempotent",
        "refresh-leave-restart-recovery",
        "adapter-failure-safe-fallback",
        "fingerprint-change-invalidates-old-package",
        "final-publish-never-claimed",
    }
    negative_ids = {
        "published-state-rejected",
        "legacy-secondary-orchestration-rejected",
        "stale-package-new-run-rejected",
        "account-package-mismatch-rejected",
        "fallback-secret-path-rejected",
        "missing-checklist-or-duplicate-upload-rejected",
        "keyboard-narrow-dead-end-rejected",
    }
    assert positive_ids | negative_ids == set(by_id)
    assert all(by_id[fixture_id]["valid"] for fixture_id in positive_ids)
    assert all(not by_id[fixture_id]["valid"] for fixture_id in negative_ids)
    assert {by_id[fixture_id]["error"] for fixture_id in negative_ids} == set(contract["negative_case_errors"])
    first = by_id["first-publish-human-handoff"]
    assert first["state"] == contract["flows"]["first_publish"]["terminal"]
    assert first["final_publish_clicks"] == 0
    repeat = by_id["repeat-publish-idempotent"]
    assert repeat["first_run_id"] == repeat["replayed_run_id"]
    assert repeat["duplicate_package_refs"] == repeat["duplicate_uploads"] == 0
    recovery = by_id["refresh-leave-restart-recovery"]
    assert {
        recovery["before_run_id"],
        recovery["after_refresh_run_id"],
        recovery["after_leave_return_run_id"],
        recovery["after_restart_run_id"],
    } == {"run_recovery"}
    fallback = by_id["adapter-failure-safe-fallback"]
    assert fallback["copy_available"] is True
    assert fallback["download_available"] is True
    assert fallback["exposed_absolute_paths"] == []
    invalidation = by_id["fingerprint-change-invalidates-old-package"]
    assert invalidation["old_package_state"] == "invalidated"
    assert invalidation["old_history_auditable"] is True
    final = by_id["final-publish-never-claimed"]
    assert set(final["must_not_contain"]) <= set(contract["forbidden_projection_states"])
    assert final["final_publish_clicks"] == 0
    assert contract["forbidden_in_entry"]
    assert by_id["stale-package-new-run-rejected"]["new_run_allowed"] is False
    assert by_id["account-package-mismatch-rejected"]["allowed"] is False
    assert by_id["fallback-secret-path-rejected"]["allowed"] is False
    assert by_id["missing-checklist-or-duplicate-upload-rejected"]["allowed"] is False
    assert by_id["keyboard-narrow-dead-end-rejected"]["allowed"] is False
