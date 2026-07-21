import json
from pathlib import Path

from api.tasks.models import TaskStatus
from pixelle_video.app_center.registry import BUILTIN_MANIFESTS, FEATURE_FLAG_ENV


def _fixture_error(fixture: dict) -> str | None:
    input_payload = fixture.get("input") or {}
    mode = input_payload.get("source_mode")
    source_ids = input_payload.get("source_artifact_version_ids")
    if mode in {"copywriting", "selected_title"} and (not isinstance(source_ids, list) or len(source_ids) != 1):
        return "SOURCE_MODE_EXACTLY_ONE"
    source_versions = fixture.get("source_versions") or []
    if source_versions and source_ids and source_versions[0].get("artifact_version_id") not in source_ids:
        return "SOURCE_VERSION_ID_MISMATCH"
    if source_versions and any(item.get("project_id") != input_payload.get("project_id") for item in source_versions):
        return "SOURCE_VERSION_PROJECT_MISMATCH"
    if mode in {"copywriting", "selected_title"} and source_versions and source_versions[0].get("artifact_type") != mode:
        return "SOURCE_ARTIFACT_TYPE_MISMATCH"
    if mode == "copywriting":
        if not isinstance(input_payload.get("selected_variant_index"), int):
            return "COPYWRITING_VARIANT_REQUIRED"
        variants = ((source_versions[0].get("content") or {}).get("variants") if source_versions else None) or []
        index = input_payload["selected_variant_index"]
        if index < 0 or index >= len(variants) or not (variants[index].get("full_text") or "").strip():
            return "COPYWRITING_VARIANT_REQUIRED"
    if mode == "selected_title" and not (((source_versions[0].get("content") or {}).get("title") if source_versions else "") or "").strip():
        return "SELECTED_TITLE_REQUIRED"
    if input_payload.get("resume_mode") == "resume_existing":
        binding = fixture.get("binding")
        if not input_payload.get("project_id") or not input_payload.get("app_run_id") or not binding:
            return "LEGACY_SESSION_EXPLICIT_CLAIM_REQUIRED"
        if binding.get("project_id") != input_payload.get("project_id"):
            return "SESSION_PROJECT_MISMATCH"
    artifact = fixture.get("artifact")
    if artifact:
        relative_path = ((artifact.get("file_refs") or [{}])[0]).get("relative_path")
        if isinstance(relative_path, str) and (relative_path.startswith("/") or relative_path.startswith("../") or "/../" in relative_path):
            return "ARTIFACT_FILE_OUTSIDE_ROOT"
    if fixture.get("active_binding") and fixture["active_binding"].get("idempotency_key") == input_payload.get("idempotency_key"):
        return "ACTIVE_RUN_IDEMPOTENT_REPLAY_REQUIRED"
    return None


def test_ip_broadcast_adapter_entry_contract_matches_registry_and_task_statuses():
    contract = json.loads(Path("docs/contracts/app-center/ip-broadcast-adapter-entry.contract.json").read_text())
    manifest = next(item for item in BUILTIN_MANIFESTS if item["app_id"] == contract["app_id"])

    assert manifest["version"] == contract["app_version"]
    assert manifest["executor_type"] == contract["executor_type"]
    assert manifest["feature_flag"] == contract["feature_flag"]
    assert contract["feature_flag"] in FEATURE_FLAG_ENV
    assert set(contract["artifact_outputs"]) <= set(manifest["produced_artifact_types"])
    assert set(contract["source_modes"][1]["artifact_types"]) <= set(manifest["accepted_artifact_types"])
    assert set(contract["source_modes"][2]["artifact_types"]) <= set(manifest["accepted_artifact_types"])

    task_values = {status.value for status in TaskStatus}
    task_projection = {item["task_status"] for item in contract["state_projection"]}
    assert task_projection <= task_values
    assert "completed" in task_projection
    assert "waiting_for_human" in task_projection
    assert "real_platform_upload_or_final_publish" in contract["forbidden_in_entry"]
    assert contract["execution_bridge"]["mode"] == "local_or_isolated_executor_only"
    assert contract["execution_bridge"]["completion_path"] == "review_accept_only"
    assert contract["execution_bridge"]["waiting_states_never_complete"] is True
    assert contract["execution_bridge"]["external_actions"] == []
    assert contract["execution_bridge"]["binding_required"] == [
        "project_id", "app_id", "app_version", "session_id", "app_run_id", "source_revision", "context_snapshot_id"
    ]
    assert contract["execution_bridge"]["context_snapshot_policy"] == "nullable_but_equal_between_request_app_run_and_binding"
    assert {"APP_RUN_BINDING_MISMATCH", "APP_RUN_EXECUTION_CONFLICT", "APP_RUN_STATE_INVALID", "APP_FEATURE_DISABLED", "BINDING_MISSING", "SESSION_PROJECT_MISMATCH"} <= set(contract["execution_error_codes"])


def test_ip_broadcast_entry_contract_freezes_three_sources_and_legacy_safety():
    contract = json.loads(Path("docs/contracts/app-center/ip-broadcast-adapter-entry.contract.json").read_text())
    modes = {item["mode"]: item for item in contract["source_modes"]}

    assert set(modes) == {"blank_project", "copywriting", "selected_title"}
    assert modes["blank_project"]["required"] == ["project_id", "source_mode", "goal"]
    assert modes["copywriting"]["required"] == ["project_id", "source_mode", "source_artifact_version_ids", "selected_variant_index"]
    assert modes["selected_title"]["required"] == ["project_id", "source_mode", "source_artifact_version_ids"]
    assert "feature_flag_off_preserves_legacy_entry" in contract["invariants"]
    assert "rewrite_ip_broadcast_workflow" in contract["forbidden_in_entry"]


def test_ip_broadcast_entry_fixtures_cover_valid_invalid_sources_resume_states_and_paths():
    contract = json.loads(Path("docs/contracts/app-center/ip-broadcast-adapter-entry.contract.json").read_text())
    fixtures = json.loads(Path("docs/contracts/app-center/fixtures/ip-broadcast-adapter-entry-fixtures.json").read_text())["fixtures"]
    by_id = {item["id"]: item for item in fixtures}
    source_modes = {item["mode"]: item for item in contract["source_modes"]}

    assert {"blank-minimal-valid", "copywriting-selected-variant-valid", "selected-title-valid"} <= by_id.keys()
    assert {"mixed-sources-invalid", "cross-project-source-invalid", "legacy-session-cross-project-invalid", "artifact-path-outside-root-invalid"} <= by_id.keys()
    assert all(by_id[item]["valid"] for item in ("blank-minimal-valid", "copywriting-selected-variant-valid", "selected-title-valid", "legacy-session-resume-valid"))
    assert not any(by_id[item]["valid"] for item in ("mixed-sources-invalid", "cross-project-source-invalid", "copywriting-selection-missing-invalid", "selected-title-empty-invalid", "legacy-session-unbound-invalid", "legacy-session-cross-project-invalid", "artifact-path-outside-root-invalid", "duplicate-active-run-invalid"))
    assert source_modes["copywriting"]["source_version_count"] == 1
    assert source_modes["copywriting"]["selection"]["selected_item_key"] == "full_text"
    assert contract["session_binding"]["forbid_implicit_cross_project_recovery"] is True
    assert contract["legacy_session_resume"]["legacy_unbound_policy"].startswith("do_not_auto_claim")
    assert any(item["when"] == "waiting_for_login" and not item["completion_allowed"] for item in contract["state_projection"])
    assert any(item["when"] == "ip_learning_topic_confirmation" and item["current_step"] == "source" for item in contract["state_projection"])
    for fixture in fixtures:
        if "input" in fixture or "artifact" in fixture:
            actual_error = _fixture_error(fixture)
            if fixture["valid"]:
                assert actual_error is None, fixture["id"]
            else:
                assert actual_error == fixture["error"], fixture["id"]
    registration = by_id["legacy-output-registration-valid-boundary"]["registration"]
    assert registration["app_run_state"] == "needs_review"
    assert registration["source"] == "imported"
    assert registration["completion_allowed"] is False
    assert registration["external_actions"] == []
    assert by_id["legacy-output-registration-partial-invalid"]["error"] == "ARTIFACT_REGISTRATION_PARTIAL"
    accept = by_id["legacy-output-accept-valid"]["registration"]
    assert accept["reviewable_attempt"] is True
    assert accept["fingerprint_match"] is True
    assert accept["accept_transition"] == "completed"
    assert by_id["legacy-output-accept-fingerprint-drift-invalid"]["error"] == "ARTIFACT_FINGERPRINT_MISMATCH"
    assert by_id["generic-complete-bypass-invalid"]["error"] == "ARTIFACT_REVIEW_ATTEMPT_REQUIRED"
    assert {
        "local-executor-blank-valid", "local-executor-waiting-nonterminal", "executor-generic-completion-bypass-invalid",
        "executor-retry-preserves-history-valid", "executor-source-revision-drift-invalid", "executor-context-binding-mismatch-invalid",
        "executor-missing-session-invalid", "executor-missing-binding-invalid", "executor-duplicate-execute-valid",
        "executor-duplicate-concurrency-invalid", "executor-restart-reconcile-valid", "executor-cancel-idempotent-valid",
        "executor-failure-retry-valid", "executor-failure-invalid", "executor-cross-project-invalid", "executor-old-entry-isolation-invalid",
    } <= by_id.keys()
    assert by_id["local-executor-blank-valid"]["execution"]["external_actions"] == []
    assert by_id["local-executor-waiting-nonterminal"]["execution"]["completion_allowed"] is False
    assert by_id["executor-generic-completion-bypass-invalid"]["error"] == "ARTIFACT_ACCEPT_EXPLICIT_REQUIRED"
    assert by_id["executor-retry-preserves-history-valid"]["execution"]["preserve_old_attempt_and_artifacts"] is True
    assert by_id["executor-source-revision-drift-invalid"]["error"] == "SOURCE_REVISION_MISMATCH"
    assert by_id["executor-context-binding-mismatch-invalid"]["error"] == "APP_RUN_BINDING_MISMATCH"
    assert by_id["executor-missing-session-invalid"]["error"] == "SESSION_NOT_FOUND"
    assert by_id["executor-missing-binding-invalid"]["error"] == "BINDING_MISSING"
    assert by_id["executor-duplicate-execute-valid"]["execution"]["reuses_same_attempt_and_task"] is True
    assert by_id["executor-duplicate-concurrency-invalid"]["execution"]["creates_second_session"] is True
    assert by_id["executor-restart-reconcile-valid"]["execution"]["reuses_same_session_and_run"] is True
    assert by_id["executor-cancel-idempotent-valid"]["execution"]["idempotent"] is True
    assert by_id["executor-failure-retry-valid"]["execution"]["new_attempt_same_session"] is True
    assert by_id["executor-failure-invalid"]["error"] == "APP_EXECUTOR_FAILED"
    assert by_id["executor-failure-invalid"]["execution"]["completion_allowed"] is False
    execution_fixtures = [item for item in fixtures if "execution" in item]
    assert len(execution_fixtures) == 17
    execution_error_codes = set(contract["execution_error_codes"])
    for fixture in execution_fixtures:
        execution = fixture["execution"]
        assert execution["mode"] == contract["execution_bridge"]["mode"], fixture["id"]
        if fixture["valid"]:
            assert execution.get("external_actions") == [], fixture["id"]
        else:
            assert fixture["error"] in execution_error_codes, fixture["id"]


def test_ip_broadcast_entry_trusted_file_ref_rejects_absolute_and_symlink_escape(tmp_path):
    root = tmp_path / "trusted"
    outside = tmp_path / "outside.mp4"
    root.mkdir()
    outside.write_bytes(b"outside")
    escape = root / "escape.mp4"
    escape.symlink_to(outside)

    def is_trusted(raw_path: str) -> bool:
        candidate = (root / raw_path).resolve() if not Path(raw_path).is_absolute() else Path(raw_path).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            return False
        return candidate.is_file()

    assert is_trusted("inside.mp4") is False
    assert is_trusted(str(outside)) is False
    assert is_trusted("escape.mp4") is False
