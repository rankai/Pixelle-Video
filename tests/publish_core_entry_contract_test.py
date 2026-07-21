"""PUB-2 entry contract and failure matrix; no platform automation is allowed here."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from api.schemas.publish_v2 import PublishPackageFromSessionRequest

ROOT = Path(__file__).resolve().parents[1]


def read_json(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_publish_core_entry_schemas_and_state_machine_are_frozen():
    run_schema = read_json("docs/contracts/publishing/publish-run.schema.json")
    package_schema = read_json("docs/contracts/publishing/publish-package-v2.schema.json")
    state_machine_schema = read_json("docs/contracts/publishing/publish-run-state-machine.json")
    state_machine = read_json("docs/contracts/publishing/fixtures/publish-run-state-machine.json")
    Draft202012Validator.check_schema(run_schema)
    Draft202012Validator.check_schema(package_schema)
    Draft202012Validator.check_schema(state_machine_schema)
    Draft202012Validator(state_machine_schema).validate(state_machine)
    assert state_machine["human_confirmation_required"] is True
    assert state_machine["final_publish_action"] == "never_exposed"
    assert set(state_machine["terminal_states"]) == {"succeeded", "failed", "cancelled"}
    assert set(state_machine["states"]) == {
        "queued", "running", "waiting_for_login", "waiting_for_human",
        "needs_attention", "succeeded", "failed", "cancelled",
    }
    transitions = {item["from"]: set(item["to"]) for item in state_machine["transitions"]}
    assert "succeeded" not in transitions["running"]
    assert transitions["waiting_for_human"] == {"succeeded", "needs_attention", "cancelled"}
    assert all(not transitions[state] for state in state_machine["terminal_states"])
    assert "succeeded" not in transitions["needs_attention"]
    assert "waiting_for_human" in transitions["needs_attention"]
    guard = next(item for item in state_machine["transition_guards"] if item["from"] == "needs_attention" and item["to"] == "waiting_for_human")
    assert "checkpoint.last_stage=verify" in guard["requires"]
    assert "event_type=verified_checkpoint_reconciled" in guard["requires"]


def test_publish_core_entry_fixtures_cover_exactly_one_source_and_human_stop():
    package_validator = Draft202012Validator(read_json("docs/contracts/publishing/publish-package-v2.schema.json"))
    run_validator = Draft202012Validator(read_json("docs/contracts/publishing/publish-run.schema.json"))
    for fixture in (
        "publish-package-artifact-source.json",
        "publish-package-carousel-source.json",
        "publish-package-legacy-source.json",
    ):
        package_validator.validate(read_json(f"docs/contracts/publishing/fixtures/{fixture}"))
    run = read_json("docs/contracts/publishing/fixtures/publish-run-waiting-human.json")
    run_validator.validate(run)
    assert run["state"] == "waiting_for_human"
    assert run["human_confirmation"]["confirmed"] is False

    def reject_source(source: dict) -> None:
        if source["kind"] == "artifact_versions":
            if not source["artifact_version_ids"]:
                raise ValueError("SOURCE_ARTIFACT_VERSION_REQUIRED")
            if source["session_id"] is not None:
                raise ValueError("SOURCE_SESSION_MUST_BE_NULL")
            if len(source["artifact_ids"]) != len(source["artifact_version_ids"]):
                raise ValueError("SOURCE_ARTIFACT_ID_MISMATCH")
        if source["kind"] == "legacy_session":
            if not source["session_id"]:
                raise ValueError("LEGACY_SESSION_REQUIRED")
            if source["artifact_ids"] or source["artifact_version_ids"]:
                raise ValueError("LEGACY_ARTIFACT_VERSIONS_FORBIDDEN")

    invalid = read_json("docs/contracts/publishing/fixtures/publish-package-invalid.json")
    for case in invalid:
        with pytest.raises(ValueError, match=case["expected_error"]):
            reject_source(case["source"])

    semantic = read_json("docs/contracts/publishing/publish-source-semantic-contract.json")
    assert "SOURCE_VERSION_NOT_REFERENCED" in semantic["error_codes"]
    package = read_json("docs/contracts/publishing/fixtures/publish-package-artifact-source.json")
    source_ids = set(package["source"]["artifact_version_ids"])
    assert {item["artifact_version_id"] for item in package["artifact_refs"]}.issubset(source_ids)
    mismatched = dict(package)
    mismatched["artifact_refs"] = [dict(package["artifact_refs"][0], artifact_version_id="artifact_version_unreferenced")]
    assert not {item["artifact_version_id"] for item in mismatched["artifact_refs"]}.issubset(source_ids)
    assert package["package_fingerprint"] != "sha256:mutated"
    assert any("new application-center handoffs cannot use legacy_session" in rule for rule in semantic["rules"])
    carousel = read_json("docs/contracts/publishing/fixtures/publish-package-carousel-source.json")
    assert carousel["video_manifest"] is None
    assert len(carousel["carousel_manifests"]) == 3
    assert {item["artifact_type"] for item in carousel["artifact_refs"]} == {"carousel_package", "carousel_page"}


def test_publish_core_entry_prohibits_platform_automation_and_secret_persistence():
    plan = (ROOT / "docs/reviews/2026-07-18-desktop-auto-publishing-refactor-implementation-plan.md").read_text(encoding="utf-8")
    adr = (ROOT / "docs/adr/ADR-PublishV2-Boundaries.md").read_text(encoding="utf-8")
    assert "FinalActionGuard" in adr and "最终发布" in adr
    assert "无效媒体不打开浏览器" in plan
    assert "平台 selector" in plan
    forbidden = {"cookie", "qr_payload", "authorization", "api_key", "profile_path"}
    contract_text = json.dumps(read_json("docs/contracts/publishing/publish-run.schema.json")).lower()
    assert forbidden.isdisjoint(contract_text)


def test_publish_core_entry_freezes_media_manifest_and_v2_rollback_contract():
    package_schema = read_json("docs/contracts/publishing/publish-package-v2.schema.json")
    video_manifest = package_schema["properties"]["video_manifest"]
    assert video_manifest["additionalProperties"] is False
    assert {"sha256", "size_bytes", "mime_type", "path_token"}.issubset(video_manifest["required"])
    assert video_manifest["properties"]["path_token"]["pattern"].startswith("^asset_")
    policy = package_schema["properties"]["policy"]
    assert policy["additionalProperties"] is False
    assert policy["properties"]["allow_final_publish"]["const"] is False
    token = read_json("docs/contracts/publishing/publish-path-token.contract.json")
    Draft202012Validator.check_schema(token)
    assert token["properties"]["symlink_policy"]["const"] == "reject"
    assert token["properties"]["toctou_policy"]["const"] == "re-resolve-and-rehash-before-open"


def test_publish_core_entry_freezes_local_capability_token_and_origin_allowlist():
    contract = read_json("docs/contracts/publishing/publish-local-capability.contract.json")
    Draft202012Validator.check_schema(contract)
    assert contract["properties"]["mode"]["const"] == "desktop_local"
    assert contract["properties"]["token_ttl_seconds"]["minimum"] >= 60
    assert contract["properties"]["wrong_origin"]["const"] == "403 ORIGIN_NOT_ALLOWED"
    assert contract["properties"]["missing_or_expired_token"]["const"] == "403 CAPABILITY_REQUIRED"
    negatives = read_json("docs/contracts/publishing/fixtures/publish-local-capability-negative.json")
    assert {case["error_code"] for case in negatives} == {"CAPABILITY_REQUIRED", "ORIGIN_NOT_ALLOWED", "DESKTOP_LOCAL_ONLY"}
    assert all(case["status"] == 403 for case in negatives)
    rollback = read_json("docs/contracts/publishing/fixtures/v1-rollback-smoke.json")
    assert rollback["v2_flag_before"] is True and rollback["v2_flag_after"] is False
    assert rollback["profile_preserved"] is True and rollback["v1_material_copy_available"] is True


def test_publish_core_entry_freezes_canonical_v2_api_and_no_final_publish_route():
    openapi = read_json("docs/contracts/publishing/publish-v2.openapi.json")
    assert openapi["servers"] == [{"url": "/api/publish/v2"}]
    paths = openapi["paths"]
    assert "/packages/from-session" in paths
    assert "/packages/{package_id}/preflight" in paths
    assert paths["/runs"]["post"]["responses"]["202"]
    for suffix in ("events", "resume", "verify", "retry-step", "cancel", "mark-outcome"):
        assert f"/runs/{{run_id}}/{suffix}" in paths
    assert not any("publish" in path.rsplit("/", 1)[-1].lower() for path in paths)
    assert openapi["securityPolicy"]["final_publish_action"] == "never_exposed"
    idem = read_json("docs/contracts/publishing/publish-idempotency.contract.json")
    assert idem["properties"]["same_key_different_payload"]["const"] == "409 IDEMPOTENCY_CONFLICT"
    assert "terminal_state" in idem["properties"]["same_key_same_payload"]["const"]
    assert "RUN_ALREADY_ACTIVE" in idem["properties"]["different_package_active_run"]["const"]
    assert "RUN_ALREADY_ACTIVE" in openapi["components"]["schemas"]["PublishError"]["properties"]["error_code"]["enum"]
    assert {"ACCOUNT_NOT_FOUND", "ACCOUNT_PLATFORM_MISMATCH"}.issubset(openapi["components"]["schemas"]["PublishError"]["properties"]["error_code"]["enum"])
    event_payload = read_json("docs/contracts/publishing/publish-event-payload.contract.json")
    assert event_payload["properties"]["sanitizer"]["const"] == "allowlist_before_json_persist"
    assert "cookie" in event_payload["properties"]["forbidden_fields"]["items"]["enum"]
    accepted_states = set(openapi["components"]["schemas"]["PublishRunAcceptedResponse"]["properties"]["state"]["enum"])
    assert {"succeeded", "failed", "cancelled"}.issubset(accepted_states)
    assert "idempotent_replay" in openapi["components"]["schemas"]["PublishRunAcceptedResponse"]["required"]
    assert paths["/packages/from-session"]["post"]["requestBody"]["content"]["application/json"]["$ref"].endswith("PublishPackageFromSessionRequest")
    assert paths["/runs"]["post"]["requestBody"]["content"]["application/json"]["$ref"].endswith("PublishRunCreateRequest")
    session_schema = openapi["components"]["schemas"]["PublishPackageFromSessionRequest"]
    assert session_schema["additionalProperties"] is False
    runtime_schema = PublishPackageFromSessionRequest.model_json_schema()
    assert set(session_schema["required"]) == set(runtime_schema["required"])
    assert set(session_schema["properties"]) == set(runtime_schema["properties"])
    assert all("path" not in name for name in session_schema["properties"])
    for suffix, operation_id in (("connect", "connectPublishAccountV2"), ("verify", "verifyPublishAccountV2"), ("open", "openPublishAccountV2")):
        operation = paths[f"/accounts/{{account_id}}/{suffix}"]["post"]
        assert operation["operationId"] == operation_id
        assert "200" in operation["responses"] and "202" not in operation["responses"]
    for path, methods in paths.items():
        for method, operation in methods.items():
            if method.lower() in {"post", "put", "patch", "delete"}:
                assert operation.get("security") == [{"DesktopCapability": []}], path
    assert "DesktopCapability" in openapi["components"]["securitySchemes"]


def test_publish_core_entry_canonicalizes_run_fields_across_schema_sql_and_typescript():
    run_schema = read_json("docs/contracts/publishing/publish-run.schema.json")
    fields = run_schema["properties"]
    assert {"state_version", "attempt", "current_step", "human_confirmation", "created_at", "updated_at"}.issubset(fields)
    sql = (ROOT / "docs/contracts/publishing/publishing-v2.sql").read_text(encoding="utf-8")
    types = (ROOT / "docs/contracts/publishing/publish-v2.types.ts").read_text(encoding="utf-8")
    assert "human_confirmation_required" in sql and "human_confirmed" in sql
    assert all(token in types for token in ("state_version", "attempt", "current_step", "created_at", "updated_at"))
    assert "video_manifest?:" not in types and "policy?:" not in types
    assert "updated_at" in run_schema["required"]
    assert "publish_run_step_attempts" in sql and "UNIQUE(run_id, step, attempt)" in sql
    assert "CREATE TABLE IF NOT EXISTS publish_events" in sql
    assert "ON publish_events(run_id, event_seq)" in sql
    assert "publish_active_run_by_account_platform" in sql
    step_facts = read_json("docs/contracts/publishing/publish-step-facts.contract.json")
    assert step_facts["properties"]["canonical_table"]["const"] == "publish_run_step_attempts"
    assert "never overwrite" in step_facts["properties"]["retry_policy"]["const"]
    concurrency = read_json("docs/contracts/publishing/publish-profile-run-concurrency.contract.json")
    assert concurrency["properties"]["active_run_key"]["const"] == "account_id+platform"
    assert concurrency["properties"]["same_profile_policy"]["const"] == "at_most_one_active_run"
    cursor = read_json("docs/contracts/publishing/publish-event-cursor.contract.json")
    assert cursor["properties"]["allocation"]["const"] == "repository_transaction_max_plus_one"
    storage = read_json("docs/contracts/publishing/publish-package-storage.contract.json")
    assert "domain validator" in storage["properties"]["json_validation_authority"]["const"]


def test_publish_core_entry_sql_enforces_active_run_attempt_event_and_immutable_package_rules():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript((ROOT / "docs/contracts/publishing/publishing-v2.sql").read_text(encoding="utf-8"))
    connection.execute("INSERT INTO publish_accounts(account_id, platform, display_name, profile_ref, created_at) VALUES ('acct_core','douyin','core','profile_core','now')")
    connection.execute("INSERT INTO publish_accounts(account_id, platform, display_name, profile_ref, created_at) VALUES ('acct_video','video_channel','video','profile_video','now')")
    connection.execute("INSERT INTO publish_packages_v2(package_id, project_id, source_kind, source_artifact_ids_json, source_artifact_version_ids_json, source_revision, artifact_refs_json, package_fingerprint, created_at) VALUES ('pkg_core','project_core','artifact_versions','[\"a\"]','[\"v\"]','r1','[]','sha256:core','now')")
    for invalid_state, version, attempt, confirmed in (("running", 1, 1, 0), ("queued", 9, 1, 0), ("queued", 1, 5, 0), ("succeeded", 1, 1, 1)):
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO publish_runs_v2(run_id, package_id, account_id, platform, state, state_version, attempt, human_confirmed, idempotency_key, created_at, updated_at) VALUES (?, 'pkg_core', 'acct_core', 'douyin', ?, ?, ?, ?, ?, 'now', 'now')", (f"invalid_{invalid_state}_{version}_{attempt}", invalid_state, version, attempt, confirmed, f"idem_{invalid_state}_{version}_{attempt}"))
    connection.execute("INSERT INTO publish_runs_v2(run_id, package_id, account_id, platform, state, idempotency_key, created_at, updated_at) VALUES ('run_core','pkg_core','acct_core','douyin','queued','idem_core','now','now')")
    connection.execute("INSERT INTO publish_packages_v2(package_id, project_id, source_kind, source_artifact_ids_json, source_artifact_version_ids_json, source_revision, artifact_refs_json, package_fingerprint, created_at) VALUES ('pkg_core_2','project_core','artifact_versions','[\"a2\"]','[\"v2\"]','r1','[]','sha256:core2','now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_runs_v2(run_id, package_id, account_id, platform, state, idempotency_key, created_at, updated_at) VALUES ('run_same_profile','pkg_core_2','acct_core','douyin','queued','idem_same_profile','now','now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_runs_v2(run_id, package_id, account_id, platform, state, idempotency_key, created_at, updated_at) VALUES ('run_dup','pkg_core','acct_core','douyin','running','idem_dup','now','now')")
    connection.execute("INSERT INTO publish_run_step_attempts(step_attempt_id, run_id, step, attempt, state, created_at, updated_at) VALUES ('step_core','run_core','preflight',1,'queued','now','now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_run_step_attempts(step_attempt_id, run_id, step, attempt, state, created_at, updated_at) VALUES ('step_dup','run_core','preflight',1,'queued','now','now')")
    connection.execute("INSERT INTO publish_events(event_id, run_id, event_seq, event_type, state, state_version, created_at) VALUES ('event_core','run_core',1,'run.created','queued',1,'now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_events(event_id, run_id, event_seq, event_type, state, state_version, redacted, created_at) VALUES ('event_bad','run_core',2,'run.created','queued',1,0,'now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_events(event_id, run_id, event_seq, event_type, state, state_version, created_at) VALUES ('event_dup','run_core',1,'run.created','queued',1,'now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE publish_packages_v2 SET package_fingerprint='sha256:mutated' WHERE package_id='pkg_core'")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE publish_runs_v2 SET state='succeeded', state_version=2 WHERE run_id='run_core'")
    connection.execute("UPDATE publish_runs_v2 SET state='running', state_version=2 WHERE run_id='run_core'")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE publish_runs_v2 SET state='queued', state_version=4 WHERE run_id='run_core'")
    connection.execute("UPDATE publish_packages_v2 SET invalidated_at='now', invalidation_reason='source changed' WHERE package_id='pkg_core'")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_runs_v2(run_id, package_id, account_id, platform, state, idempotency_key, created_at, updated_at) VALUES ('run_stale','pkg_core','acct_core','douyin','queued','idem_stale','now','now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_runs_v2(run_id, package_id, account_id, platform, state, idempotency_key, created_at, updated_at) VALUES ('run_mismatch','pkg_core','acct_video','douyin','queued','idem_mismatch','now','now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE publish_packages_v2 SET invalidated_at=NULL, invalidation_reason=NULL WHERE package_id='pkg_core'")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE publish_packages_v2 SET invalidation_reason='mutated reason' WHERE package_id='pkg_core'")
