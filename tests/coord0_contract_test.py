"""COORD-0 contract tests; these deliberately do not import or mutate business code."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def read_json(relative: str):
    return json.loads((ROOT / relative).read_text())


def schema(relative: str):
    value = read_json(relative)
    Draft202012Validator.check_schema(value)
    return value


def validate(relative: str, fixture):
    validator = Draft202012Validator(schema(relative))
    errors = sorted(validator.iter_errors(fixture), key=lambda error: list(error.path))
    assert not errors, "{}: {}".format(relative, "; ".join(error.message for error in errors))


def reject_manifest_semantic(manifest: dict, registry: dict) -> None:
    if manifest["executor_key"] not in registry["known_executor_keys"]:
        raise ValueError("EXECUTOR_NOT_REGISTERED")
    if manifest["icon"] not in registry["known_icons"]:
        raise ValueError("ICON_NOT_ALLOWLISTED")
    if any(target not in registry["known_app_ids"] for target in manifest["handoff_targets"]):
        raise ValueError("HANDOFF_TARGET_NOT_REGISTERED")
    if manifest["app_id"] in manifest["handoff_targets"]:
        raise ValueError("HANDOFF_SELF_REFERENCE")
    if any(cap not in registry["known_capabilities"] for cap in manifest["required_capabilities"]):
        raise ValueError("CAPABILITY_NOT_REGISTERED")
    if manifest["feature_flag"] not in registry["known_feature_flags"]:
        raise ValueError("FEATURE_FLAG_NOT_REGISTERED")
    manifests = read_json("docs/contracts/app-center/fixtures/app-manifests.json")
    by_id = {item["app_id"]: item for item in manifests}
    for target in manifest["handoff_targets"]:
        if not set(manifest["produced_artifact_types"]).intersection(by_id[target]["accepted_artifact_types"]):
            raise ValueError("HANDOFF_ARTIFACT_INCOMPATIBLE")


def reject_artifact_semantic(artifact: dict) -> None:
    version_ids = [item["artifact_version_id"] for item in artifact["versions"]]
    revisions = [item["revision"] for item in artifact["versions"]]
    if artifact["current_version_id"] not in version_ids:
        raise ValueError("CURRENT_VERSION_NOT_FOUND")
    if len(revisions) != len(set(revisions)):
        raise ValueError("REVISION_NOT_UNIQUE")
    if sorted(revisions) != list(range(1, len(revisions) + 1)):
        raise ValueError("REVISION_GAP")
    if artifact["artifact_type"] == "publish_package_ref":
        content = artifact["versions"][0]["content"]
        if not content.get("source_artifact_version_ids"):
            raise ValueError("PUBLISH_REF_SOURCE_REQUIRED")


def reject_publish_source(source: dict) -> None:
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


def guard_decision(action_id: str, matrix: dict) -> str:
    allowed = {item["action_id"] for item in matrix["allowed"]}
    return "allow" if action_id in allowed else "deny"


def reject_unsupported_schema_version(version: int, current: int = 1) -> None:
    if version > current:
        raise ValueError("UNSUPPORTED_FUTURE_SCHEMA")


def test_all_contract_json_is_valid_and_schemas_are_draft_2020_12():
    for path in (ROOT / "docs/contracts").rglob("*.json"):
        value = json.loads(path.read_text())
        if isinstance(value, dict) and value.get("$schema") == "https://json-schema.org/draft/2020-12/schema":
            Draft202012Validator.check_schema(value)


def test_manifest_and_artifact_fixtures_validate():
    manifests = read_json("docs/contracts/app-center/fixtures/app-manifests.json")
    validator = Draft202012Validator(schema("docs/contracts/app-center/app-manifest.schema.json"))
    for manifest in manifests:
        validator.validate(manifest)
    assert {item["app_id"] for item in manifests} == {
        "builtin.marketing-copy", "builtin.viral-titles", "builtin.douyin-carousel", "builtin.digital-human-video"
    }
    for relative in ("artifact-copywriting.json", "artifact-publish-package-ref.json"):
        validate("docs/contracts/app-center/artifact-contract.schema.json", read_json(f"docs/contracts/app-center/fixtures/{relative}"))
    assert len({item["app_id"] for item in manifests}) == len(manifests)
    assert len({item["executor_key"] for item in manifests}) == len(manifests)
    by_id = {item["app_id"]: item for item in manifests}
    for manifest in manifests:
        for target in manifest["handoff_targets"]:
            assert set(manifest["produced_artifact_types"]).intersection(by_id[target]["accepted_artifact_types"])


def test_app_input_output_state_error_and_flag_contracts_validate():
    fixture = read_json("docs/contracts/app-center/fixtures/app-input-output.json")
    validate("docs/contracts/app-center/app-input.schema.json", fixture["input"])
    validate("docs/contracts/app-center/app-output.schema.json", fixture["output"])
    validate("docs/contracts/app-center/app-run-state.schema.json", fixture["state"])
    errors = read_json("docs/contracts/app-center/app-error-codes.json")
    flags = read_json("docs/contracts/app-center/feature-flag-matrix.json")
    assert "STRUCTURED_OUTPUT_INVALID" in errors["codes"]
    assert all(flag["default"] is False for flag in flags["flags"])
    assert flags["unknown_flag_behavior"] == "false"
    readiness = read_json("docs/contracts/app-center/fixtures/app-readiness.json")
    for case in readiness:
        if not case["flag_enabled"]:
            expected = "disabled"
        elif not set(case["configured_capabilities"]) >= ({"llm"} if case["app_id"] != "builtin.digital-human-video" else {"llm", "runninghub", "digital_human"}):
            expected = "not_ready"
        else:
            expected = "ready"
        assert expected == case["expected"]


def test_manifest_registry_semantic_invalid_cases_are_rejected():
    manifests = read_json("docs/contracts/app-center/fixtures/app-manifests.json")
    registry = read_json("docs/contracts/app-center/app-registry-semantic-contract.json")
    base = manifests[0]
    for case in read_json("docs/contracts/app-center/fixtures/app-registry-invalid.json"):
        candidate = deepcopy(base)
        candidate.update(case["patch"])
        with pytest.raises(ValueError, match=case["expected_error"]):
            reject_manifest_semantic(candidate, registry)


def test_artifact_semantic_invariants_are_executable():
    artifact = read_json("docs/contracts/app-center/fixtures/artifact-publish-package-ref.json")
    versions = artifact["versions"]
    assert artifact["current_version_id"] in {item["artifact_version_id"] for item in versions}
    assert [item["revision"] for item in versions] == sorted({item["revision"] for item in versions})
    content = versions[0]["content"]
    assert artifact["artifact_type"] == "publish_package_ref"
    assert content["package_id"] and content["publishing_schema_version"] == 2
    assert content["package_fingerprint"].startswith("sha256:")
    assert content["source_artifact_version_ids"]
    for case in read_json("docs/contracts/app-center/fixtures/artifact-invalid.json"):
        candidate = deepcopy(artifact)
        if case["case"] == "duplicate_revision":
            candidate["versions"] = [deepcopy(artifact["versions"][0]), deepcopy(artifact["versions"][0])]
        elif case["case"] == "revision_gap":
            candidate["versions"] = [deepcopy(artifact["versions"][0])]
            candidate["versions"][0]["revision"] = 2
        elif case["case"] == "publish_ref_missing_source":
            candidate["versions"][0]["content"].pop("source_artifact_version_ids", None)
        else:
            candidate.update(case["patch"])
        with pytest.raises(ValueError, match=case["expected_error"]):
            reject_artifact_semantic(candidate)


def test_publish_package_run_and_step_fixtures_validate():
    package_schema = "docs/contracts/publishing/publish-package-v2.schema.json"
    for fixture in (
        "publish-package-artifact-source.json",
        "publish-package-carousel-source.json",
        "publish-package-legacy-source.json",
    ):
        validate(package_schema, read_json(f"docs/contracts/publishing/fixtures/{fixture}"))
    artifact_source = read_json("docs/contracts/publishing/fixtures/publish-package-artifact-source.json")["source"]
    assert len(artifact_source["artifact_ids"]) == len(artifact_source["artifact_version_ids"])
    validate("docs/contracts/publishing/publish-account.schema.json", read_json("docs/contracts/publishing/fixtures/publish-account-douyin-pilot.json"))
    run = read_json("docs/contracts/publishing/fixtures/publish-run-waiting-human.json")
    validate("docs/contracts/publishing/publish-run.schema.json", run)
    validate("docs/contracts/publishing/publish-step-result.schema.json", read_json("docs/contracts/publishing/fixtures/publish-step-result-waiting-human.json"))
    assert run["state"] == "waiting_for_human" and run["human_confirmation"]["confirmed"] is False


def test_profile_discovery_is_read_only_and_redacted():
    report = read_json("docs/contracts/publishing/fixtures/profile-discovery-report-2026-07-19.json")
    validate("docs/contracts/publishing/profile-discovery-report.schema.json", report)
    assert report["writes_performed"] == 0
    assert all("cookie" not in json.dumps(candidate).lower() for candidate in report["candidates"])
    assert all(candidate["candidate_ref"].startswith("relative:") for candidate in report["candidates"])


def test_v1_rollback_smoke_fixture_preserves_legacy_path():
    smoke = read_json("docs/contracts/publishing/fixtures/v1-rollback-smoke.json")
    validate("docs/contracts/publishing/v1-rollback-smoke.schema.json", smoke)
    assert smoke["duplicate_uploads"] == 0
    assert smoke["profile_preserved"] and smoke["v1_material_copy_available"]


def test_current_publishing_baseline_has_nine_explicit_external_rows():
    baseline = read_json("docs/contracts/publishing/fixtures/publish-v2-current-baseline-2026-07-19.json")
    validate("docs/contracts/publishing/publish-v2-current-baseline.schema.json", baseline)
    assert [row["task_id"] for row in baseline["tasks"]] == list(range(1, 10))
    assert baseline["evidence_status"] == "complete_with_boundary"
    metrics_ref = "docs/reviews/application-publishing-program/qa/COORD-0-pub-a-nine-task-metrics-2026-07-19.json"
    assert (ROOT / metrics_ref).exists()
    metrics = read_json(metrics_ref)
    assert metrics["result"] == "complete_with_explicit_bases"
    assert [item["task_id"] for item in metrics["tasks"]] == list(range(1, 10))
    assert baseline["tasks"][7]["status"] == "failed"
    assert metrics["tasks"][7]["status"] == "failed"
    assert metrics["metric_semantics"]["task8_failure_is_baseline_outcome"] is True
    for row in baseline["tasks"]:
        assert row["metrics_ref"] == metrics_ref
        metric = metrics["tasks"][row["task_id"] - 1]
        assert (row["click_count"], row["automation_ms"], row["human_wait_ms"]) == (
            metric["click_count"], metric["automation_ms"], metric["human_wait_ms"]
        )
        assert isinstance(row["click_count"], int) and row["click_count"] >= 0
        assert isinstance(row["automation_ms"], int) and row["automation_ms"] >= 0
        assert isinstance(row["human_wait_ms"], int) and row["human_wait_ms"] >= 0
        assert row["evidence_ref"] is not None and (ROOT / row["evidence_ref"]).exists()


def test_minimal_douyin_dom_fixtures_are_present_redacted_and_cover_gate_states():
    manifest = read_json("tests/fixtures/publishing/manifest.json")
    assert manifest["schema_version"] == 1
    assert manifest["platform"] == "douyin"
    fixtures = manifest["fixtures"]
    assert len(fixtures) == 13
    assert {item["state"] for item in fixtures} >= {
        "signed_in", "signed_out", "captcha", "loading", "network_error",
        "upload_entry", "uploading", "processing", "editor_ready", "cover_modal",
        "cover_error", "waiting_for_human", "unknown",
    }
    for item in fixtures:
        path = ROOT / "tests/fixtures/publishing" / item["path"]
        assert path.exists(), item["fixture_id"]
        html = path.read_text()
        assert "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"], item["fixture_id"]
        assert "<html" in html and "data-platform=\"douyin\"" in html
        assert all(marker in html for marker in item["required_markers"]), item["fixture_id"]
        lowered = html.lower()
        assert "cookie" not in lowered
        assert "sign_token" not in lowered
        assert "authorization" not in lowered


def test_media_fixture_manifest_covers_valid_and_invalid_inputs():
    manifest = read_json("docs/contracts/publishing/media-fixtures.manifest.json")
    assert manifest["generation"]["writes_to_production"] is False
    assert {fixture["expected"] for fixture in manifest["fixtures"]} == {"accepted", "rejected"}
    assert {fixture["fixture_id"] for fixture in manifest["fixtures"]} >= {"valid_mp4_h264", "missing_moov_atom", "zero_byte", "fake_extension", "valid_cover_png"}
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg unavailable in test environment")
    with tempfile.TemporaryDirectory(prefix="pixelle-coord0-media-") as directory:
        result = subprocess.run(
            [sys.executable, "docs/contracts/publishing/generate_media_fixtures.py", "--output-dir", directory],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        generated = json.loads(result.stdout)["generated_files"]
        assert len(generated) == 6
        assert all(item["sha256"].startswith("sha256:") and item["bytes"] >= 0 for item in generated)
        expected = {item["fixture_id"]: item["sha256"] for item in manifest["fixtures"]}
        actual = {Path(item["name"]).stem: item["sha256"] for item in generated}
        assert actual == expected


def test_publish_source_invalid_fixtures_cover_both_sources():
    for case in read_json("docs/contracts/publishing/fixtures/publish-package-invalid.json"):
        with pytest.raises(ValueError, match=case["expected_error"]):
            reject_publish_source(case["source"])


def test_projection_and_llm_contracts_freeze_redaction_and_waiting_states():
    matrix = read_json("docs/contracts/coordination/app-run-task-projection-matrix.json")
    assert matrix["facts"][0]["task_cleanup_must_delete_fact"] is False
    assert "waiting_for_human" in matrix["waiting_states"]
    assert "waiting_for_human" in matrix["success_states_must_not_include"]
    assert "absolute_file_path" in matrix["projection_contract"]["redacted_fields"]
    llm = read_json("docs/contracts/coordination/app-llm-port.contract.json")
    assert {"api_key", "provider", "model"}.issubset(llm["forbidden_request_fields"])
    assert llm["request"]["context"].startswith("JSON object")
    assert "prompt_variables" in llm["request"]


def test_final_action_guard_and_model_redaction_fixtures_are_safe():
    matrix = read_json("docs/contracts/publishing/final-action-guard.matrix.json")
    allowed = {item["action_id"] for item in matrix["allowed"]}
    denied = {item["action_id"] for item in matrix["denied"]}
    assert matrix["default"] == "deny"
    assert {"publish", "confirm_publish", "submit", "unknown"}.issubset(denied)
    for case in read_json("docs/contracts/publishing/fixtures/final-action-guard-cases.json"):
        assert guard_decision(case["action_id"], matrix) == case["expected"]
        if case["expected"] == "allow":
            assert case["action_id"] in allowed
        else:
            assert case["action_id"] in denied
            assert case["error_code"] == "FINAL_ACTION_BLOCKED"
    redaction = read_json("docs/contracts/coordination/model-redaction-fixtures.json")
    assert all(case["expected"] == "reject_model_override" for case in redaction["request_override_cases"])
    assert all(not any(secret in json.dumps(redaction["response_metadata"]) for secret in redaction["forbidden_persisted_values"]) for _ in [0])
    assert redaction["response_metadata"]["model_ref"].startswith("local-default:")


def test_guard_and_v1_rollback_local_smoke_evidence_is_explicitly_bounded():
    evidence = read_json("docs/reviews/application-publishing-program/qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json")
    assert evidence["result"] == "passed_local_contract_smoke"
    assert evidence["no_platform_actions"] is True
    assert evidence["rollback"] == {
        "v2_flag_before": True,
        "v2_flag_after": False,
        "profile_preserved": True,
        "v1_material_copy_available": True,
        "duplicate_uploads": 0,
        "production_writes": 0,
    }
    decisions = {item["action_id"]: item for item in evidence["final_action_guard"]["decisions"]}
    assert decisions["save_cover"]["decision"] == "allow"
    for action_id in ("publish", "confirm_publish", "unknown"):
        assert decisions[action_id] == {"action_id": action_id, "decision": "deny", "error_code": "FINAL_ACTION_BLOCKED"}
    assert evidence["final_action_guard"]["stop_state"] == "waiting_for_human"


def test_sqlite_migrations_are_idempotent_and_constraints_hold():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("CREATE TABLE publish_packages (id TEXT PRIMARY KEY, session_id TEXT NOT NULL)")
    for relative in ("docs/contracts/app-center/app-center-v1.sql", "docs/contracts/publishing/publishing-v2.sql"):
        sql = (ROOT / relative).read_text()
        connection.executescript(sql)
        connection.executescript(sql)
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"app_schema_migrations", "app_registry", "content_projects", "artifacts", "artifact_versions", "app_runs", "context_snapshots", "run_attempts", "app_events", "artifact_handoffs", "publishing_schema_migrations", "publish_accounts", "publish_packages_v2", "publish_runs_v2", "publish_step_results", "publish_run_step_attempts", "publish_events"}.issubset(tables)
    assert "publish_packages" in tables
    connection.execute("INSERT INTO publish_packages(id, session_id) VALUES ('legacy_1', 'session_1')")
    assert connection.execute("SELECT count(*) FROM publish_packages").fetchone()[0] == 1
    assert connection.execute("SELECT schema_version FROM app_schema_migrations WHERE migration_id='app-center-v1'").fetchone()[0] == 1
    assert connection.execute("SELECT schema_version FROM publishing_schema_migrations WHERE migration_id='publishing-v2'").fetchone()[0] == 2
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO app_schema_migrations(migration_id, schema_version, applied_at) VALUES ('future', 99, 'now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publishing_schema_migrations(migration_id, schema_version, applied_at) VALUES ('future', 99, 'now')")
    connection.execute("INSERT INTO publish_accounts(account_id, platform, display_name, profile_ref, created_at) VALUES ('acct_1','douyin','pilot','profile_1','now')")
    connection.execute("INSERT INTO publish_packages_v2(package_id, project_id, source_kind, source_artifact_ids_json, source_artifact_version_ids_json, source_revision, artifact_refs_json, package_fingerprint, created_at) VALUES ('pkg_1','p','artifact_versions','[\"a\"]','[\"v\"]','r1','[]','sha256:p','now')")
    connection.execute("INSERT INTO publish_runs_v2(run_id, package_id, account_id, platform, state, idempotency_key, created_at, updated_at) VALUES ('run_1','pkg_1','acct_1','douyin','queued','idem_1','now','now')")
    connection.execute("UPDATE publish_runs_v2 SET state='running', state_version=2 WHERE run_id='run_1'")
    connection.execute("UPDATE publish_runs_v2 SET state='waiting_for_human', state_version=3 WHERE run_id='run_1'")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_packages_v2(package_id, project_id, source_kind, source_artifact_ids_json, source_artifact_version_ids_json, source_revision, artifact_refs_json, package_fingerprint, created_at) VALUES ('pkg_bad','p','artifact_versions','[]','[]','r1','[]','sha256:bad','now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("UPDATE publish_runs_v2 SET human_confirmed=1 WHERE run_id='run_1'")
    connection.execute("INSERT INTO publish_step_results(step_result_id, run_id, step, state, evidence_kind, evidence_redacted, created_at) VALUES ('step_1','run_1','await_human_publish','waiting_for_human','none',1,'now')")
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute("INSERT INTO publish_step_results(step_result_id, run_id, step, state, evidence_kind, evidence_redacted, created_at) VALUES ('step_bad','run_1','await_human_publish','waiting_for_human','log_ref',0,'now')")
    connection.commit()
    try:
        connection.execute("BEGIN")
        connection.execute("CREATE TABLE injected_migration_table (id TEXT)")
        raise RuntimeError("injected failure")
    except RuntimeError:
        connection.rollback()
    assert connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='injected_migration_table'").fetchone() is None


def test_coordination_and_plan_convergence_is_explicit():
    progress = (ROOT / "docs/reviews/2026-07-18-application-center-publishing-program-progress.md").read_text()
    assert re.search(r"^current_stage: (APP-TEXT|PUB-ACCOUNT|PUB-CORE|PUB-DOUYIN|APP-CAROUSEL|APP-IPB|PUB-INTEGRATION|E2E-DOUYIN|PROGRAM-ROLLOUT)$", progress, re.MULTILINE)
    assert re.search(r"^current_stage_status: (in_progress|waiting_user|implementation_in_progress)$", progress, re.MULTILINE)
    assert re.search(r"^gate_status: (PG-D/entry_passed_with_boundary|PUB-ACCOUNT/entry_passed_with_boundary|PUB-CORE/entry_in_progress|PUB-CORE/entry_passed_with_boundary|PUB-DOUYIN/entry_in_progress|PUB-DOUYIN/entry_passed_with_boundary|PUB-DOUYIN/implementation_pass_with_boundary|PUB-DOUYIN/pg_g_in_progress|APP-CAROUSEL/entry_in_progress|APP-CAROUSEL/entry_passed_with_boundary|APP-CAROUSEL/implementation_in_progress|APP-CAROUSEL/implementation_pass_with_boundary|APP-CAROUSEL/PG-H_in_progress|APP-CAROUSEL/PG-H_passed_with_boundary|APP-IPB/entry_in_progress|APP-IPB/implementation_in_progress|APP-IPB/implementation_pass_with_boundary|PUB-INTEGRATION/pg-j-closure-entry_passed_with_boundary|PUB-INTEGRATION/pg-j-closure-implementation_pass_with_boundary_pending_review|E2E-DOUYIN/pub-5-entry_in_progress|E2E-DOUYIN/pub-5-entry_passed_with_boundary|PROGRAM-ROLLOUT/entry_passed_with_boundary|PROGRAM-ROLLOUT/implementation_in_progress)$", progress, re.MULTILINE)
    assert re.search(r"\| 0 \| COORD-0 \| AC-0 \+ PUB-0 \| `completed` \| PG-A \| `passed` \|", progress)
    assert re.search(r"\| 1 \| APP-SHELL \| AC-1 \| `completed` \| PG-B \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 2 \| APP-CORE \| AC-2 \| `completed` \| PG-C \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 3 \| APP-TEXT \| AC-3 \| `completed` \| PG-D \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 4 \| PUB-ACCOUNT \| PUB-1 \| `completed` \| PG-E \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 5 \| PUB-CORE \| PUB-2 \| `completed` \| PG-F \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 6 \| PUB-DOUYIN \| PUB-3 \| `completed` \| PG-G \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 7 \| APP-CAROUSEL \| AC-4 \| `completed` \| PG-H \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 8 \| APP-IPB \| AC-5 \| `completed` \| PG-I \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 9 \| PUB-INTEGRATION \| PUB-4 \| `completed` \| PG-J \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 10 \| E2E-DOUYIN \| PUB-5 \| `completed_with_boundary` \| PG-K \| `passed_with_boundary` \|", progress)
    assert re.search(r"\| 11 \| PROGRAM-ROLLOUT \| AC-6 \+ PUB-7D \| `implementation_in_progress` \| PG-L \| `entry_passed_with_boundary` \|", progress)
    app_plan = (ROOT / "docs/superpowers/specs/2026-07-18-application-center-product-architecture-implementation-plan.md").read_text()
    publish_plan = (ROOT / "docs/reviews/2026-07-18-desktop-auto-publishing-refactor-implementation-plan.md").read_text()
    assert "video + publish_package_ref" in app_plan
    assert "source_session_id TEXT NOT NULL" not in publish_plan
    assert "只能在上位 Program 的 COORD-0" in publish_plan


def test_frontend_tooling_and_deferred_admin_are_frozen():
    decision = (ROOT / "docs/contracts/coordination/frontend-test-tooling-decision.md").read_text()
    assert "APP-SHELL（PG-B）" in decision and "landed_for_pg_b" in decision
    master = (ROOT / "docs/superpowers/specs/2026-07-18-application-center-publishing-program-master-plan.md").read_text()
    for trigger in ("应用数量明显增加", "不发版远程上下架", "组织、多人或多租户", "套餐决定应用权益", "按客户或渠道灰度", "第三方应用或插件", "运营审计或远程熔断"):
        assert trigger in master
