import json
import sqlite3
from pathlib import Path

import pytest

from pixelle_video.app_center.registry import (
    FEATURE_FLAG_ENV,
    get_app_readiness,
    list_effective_apps,
)
from pixelle_video.config import config_manager
from pixelle_video.config.schema import PixelleVideoConfig


def test_registry_returns_all_manifests_disabled_by_default(monkeypatch):
    for env_name in (
        "PIXELLE_APP_CENTER_CONTENT_APPS",
        "PIXELLE_APP_CENTER_DOUYIN_CAROUSEL",
        "PIXELLE_APP_CENTER_DIGITAL_HUMAN",
    ):
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setattr(config_manager, "config", PixelleVideoConfig())

    apps = list_effective_apps()

    assert len(apps) == 4
    assert {item["app_id"] for item in apps} == {
        "builtin.marketing-copy",
        "builtin.viral-titles",
        "builtin.douyin-carousel",
        "builtin.digital-human-video",
    }
    assert all(item["readiness"]["status"] == "disabled" for item in apps)
    assert all("api_key" not in item for item in apps)


def test_registry_readiness_reuses_current_config_without_second_model_source(monkeypatch):
    monkeypatch.setenv("PIXELLE_APP_CENTER_CONTENT_APPS", "true")
    monkeypatch.setenv("PIXELLE_APP_CENTER_DIGITAL_HUMAN", "true")
    monkeypatch.setenv("PIXELLE_APP_CENTER_DOUYIN_CAROUSEL", "false")
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(
            llm={"api_key": "qa-key", "base_url": "http://localhost/v1", "model": "qa-model"},
            comfyui={"runninghub_api_key": "qa-runninghub"},
        ),
    )

    by_id = {item["app_id"]: item for item in list_effective_apps()}

    assert by_id["builtin.viral-titles"]["readiness"]["status"] == "ready"
    assert by_id["builtin.digital-human-video"]["readiness"]["status"] == "ready"
    assert by_id["builtin.douyin-carousel"]["readiness"]["status"] == "disabled"
    assert get_app_readiness("builtin.viral-titles")["configured_capabilities"] == [
        "digital_human",
        "llm",
        "runninghub",
        "template",
    ]
    assert get_app_readiness("missing.app") is None


def test_registry_douyin_carousel_flag_off_is_explicitly_disabled(monkeypatch):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DOUYIN_CAROUSEL", "false")
    monkeypatch.setattr(
        config_manager,
        "config",
        PixelleVideoConfig(llm={"api_key": "qa-key", "base_url": "http://localhost/v1", "model": "qa-model"}),
    )

    carousel = next(item for item in list_effective_apps() if item["app_id"] == "builtin.douyin-carousel")

    assert carousel["enabled"] is False
    assert carousel["readiness"]["status"] == "disabled"


def test_registry_routes_are_wired_into_fastapi():
    from api.app import app

    paths = {route.path for route in app.routes}

    assert {"/api/apps", "/api/apps/{app_id}", "/api/apps/{app_id}/readiness"} <= paths


def test_registry_flag_env_names_match_the_shared_contract():
    contract = json.loads(Path("docs/contracts/app-center/app-registry-semantic-contract.json").read_text())

    assert {name: value["env"] for name, value in contract["known_feature_flags"].items()} == FEATURE_FLAG_ENV
    assert contract["ownership"] == {
        "manifest_source_of_truth": "pixelle_video.app_center.registry.BUILTIN_MANIFESTS",
        "sqlite_role": "read_only_versioned_snapshot",
        "sqlite_primary_key": ["app_id", "version"],
        "seed_trigger": "app_center_database_initialization",
        "seed_key": ["app_id", "version"],
        "seed_writer": "trusted_backend_only",
        "user_manifest_write_api": False,
        "foreign_key_precondition": "registry_seed_must_commit_before_app_run_or_handoff_insert",
    }


def test_ac2_entry_sql_matches_domain_fields_and_canonical_app_run_states():
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(Path("docs/contracts/app-center/app-center-v1.sql").read_text())

    columns = {
        table: {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
        for table in (
            "app_registry",
            "content_projects",
            "context_snapshots",
            "app_runs",
            "run_attempts",
            "artifacts",
            "artifact_versions",
            "artifact_handoffs",
        )
    }
    assert {"app_id", "version", "manifest_json", "source"} <= columns["app_registry"]
    assert {"schema_version", "status", "primary_goal", "brand_id", "current_context_snapshot_id"} <= columns["content_projects"]
    assert {"schema_version", "payload_json", "source_brand_id", "source_brand_revision_id", "fingerprint"} <= columns["context_snapshots"]
    assert {"app_version", "state", "state_version", "input_schema_version", "input_json", "context_snapshot_id", "prompt_version", "session_id", "completed_at"} <= columns["app_runs"]
    assert {"task_id", "state", "context_snapshot_id", "diagnostic_json", "model_ref", "provider_class", "duration_ms"} <= columns["run_attempts"]
    assert {"source_app_run_id", "name", "status"} <= columns["artifacts"]
    assert {"project_id", "version_number", "file_refs_json", "source", "content_fingerprint"} <= columns["artifact_versions"]
    assert {"project_id", "source_artifact_id", "source_artifact_version_id", "target_app_id", "target_app_version", "target_run_id", "mapping_version"} <= columns["artifact_handoffs"]
    migration_columns = {row[1] for row in connection.execute("PRAGMA table_info(app_schema_migrations)")}
    assert {"migration_id", "schema_version", "checksum", "applied_at"} <= migration_columns

    connection.execute(
        "INSERT INTO app_registry(app_id, schema_version, version, manifest_json, status, feature_flag, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("builtin.test", 1, "1.0.0", "{}", "stable", "contentApps", "builtin_code", "now", "now"),
    )
    connection.execute(
        "INSERT INTO app_registry(app_id, schema_version, version, manifest_json, status, feature_flag, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("builtin.test", 1, "1.1.0", "{}", "stable", "contentApps", "builtin_code", "now", "now"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO app_registry(app_id, schema_version, version, manifest_json, status, feature_flag, source, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("builtin.test", 1, "1.0.0", "different", "stable", "contentApps", "builtin_code", "now", "now"),
        )
    connection.execute(
        "INSERT INTO content_projects(project_id, name, primary_goal, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        ("project_1", "测试项目", "测试", "now", "now"),
    )
    connection.execute(
        "INSERT INTO app_runs(app_run_id, app_id, project_id, app_version, state, idempotency_key, input_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("run_1", "builtin.test", "project_1", "1.0.0", "draft", "idem-1", "{}", "now", "now"),
    )
    connection.execute(
        "INSERT INTO app_runs(app_run_id, app_id, project_id, app_version, state, idempotency_key, input_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ("run_2", "builtin.test", "project_1", "1.1.0", "draft", "idem-2", "{}", "now", "now"),
    )
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            "INSERT INTO app_runs(app_run_id, app_id, project_id, app_version, state, idempotency_key, input_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("run_bad_version", "builtin.test", "project_1", "9.9.9", "draft", "idem-bad", "{}", "now", "now"),
        )

    app_run_sql = connection.execute("SELECT sql FROM sqlite_master WHERE name='app_runs'").fetchone()[0]
    assert all(state in app_run_sql for state in ("draft", "queued", "running", "needs_review", "completed", "failed", "cancelled"))
    assert "succeeded" not in app_run_sql


def test_ac2_entry_state_transition_matrix_is_explicit():
    matrix = json.loads(Path("docs/contracts/app-center/app-run-state-transitions.json").read_text())

    assert matrix["states"] == ["draft", "queued", "running", "needs_review", "completed", "failed", "cancelled"]
    assert matrix["terminal_states"] == ["completed", "failed", "cancelled"]
    assert matrix["allowed_transitions"]["failed"] == ["queued", "cancelled"]
    assert matrix["allowed_transitions"]["completed"] == []
    assert set(matrix["forbidden_external_states"]) >= {"succeeded", "waiting_for_human", "needs_attention"}
