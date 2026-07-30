from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from dataclasses import fields
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

import api.routers.app_center as app_center_api
import api.routers.assets_v2 as assets_v2_api
from api.schemas.asset_library_v2 import BrandKitV2Request
from pixelle_video.app_center.models import ContentProject, ContextSnapshot
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "docs/contracts/app-center"
FIXTURE_DIR = CONTRACT_DIR / "fixtures"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = _load(CONTRACT_DIR / name)
    Draft202012Validator.check_schema(schema)
    schemas = [
        _load(CONTRACT_DIR / "context-snapshot-v2.schema.json"),
        _load(CONTRACT_DIR / "context-snapshot-v3.schema.json"),
        _load(CONTRACT_DIR / "context-snapshot-v3-write-request.schema.json"),
    ]
    registry = Registry().with_resources(
        (item["$id"], Resource.from_contents(item)) for item in schemas
    )
    return Draft202012Validator(schema, registry=registry)


def _errors(validator: Draft202012Validator, payload: dict[str, Any]) -> list[str]:
    return [error.message for error in validator.iter_errors(payload)]


def _v3_to_v2(payload: dict[str, Any]) -> dict[str, Any]:
    brand = payload["brand_context"]
    project = payload["project_brief"]
    brand_values = brand["values"] if brand else {}
    asset_refs = list(project["asset_refs"])
    for key in ("logo_ref", "default_bgm_ref"):
        ref = brand_values.get(key)
        if ref and ref not in asset_refs:
            asset_refs.append(ref)
    return {
        "schema_version": 2,
        "subject_type": project["subject_type"],
        "store_or_brand": {
            "name": brand_values.get("display_name") or project["offer"]["name"],
            "industry": project["offer"]["category"],
            "address": brand_values.get("store_address") or None,
            "contact": brand_values.get("phone") or None,
        },
        "offer": project["offer"],
        "audience": project["audience"],
        "selling_points": project["selling_points"],
        "proof_points": project["proof_points"],
        "required_facts": project["required_facts"],
        "forbidden_claims": project["forbidden_claims"],
        "asset_refs": asset_refs,
        "brand_revision_ref": (
            f"brand:{brand['brand_id']}@{brand['domain_revision']}" if brand else None
        ),
    }


def _table_rows(db_path: Path, table: str) -> list[tuple[Any, ...]]:
    with sqlite3.connect(db_path) as connection:
        columns = [
            str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        ]
        order_by = ", ".join(columns) if columns else "rowid"
        return connection.execute(f"SELECT * FROM {table} ORDER BY {order_by}").fetchall()


def _database_state(db_path: Path) -> dict[str, list[tuple[Any, ...]]]:
    with sqlite3.connect(db_path) as connection:
        table_names = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ]
    return {table: _table_rows(db_path, table) for table in table_names}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _typescript_exported_function(source: str, function_name: str) -> str:
    marker = f"export function {function_name}("
    start = source.index(marker)
    next_export = source.find("\nexport function ", start + len(marker))
    return source[start : next_export if next_export >= 0 else len(source)]


def test_context_snapshot_v3_schema_accepts_inherited_override_and_unbranded_cases():
    fixtures = _load(FIXTURE_DIR / "brand-project-boundary-entry-fixtures.json")
    validator = _validator("context-snapshot-v3.schema.json")
    for case_id, payload in fixtures["valid"].items():
        assert _errors(validator, payload) == [], case_id


def test_context_snapshot_v3_rejects_unpinned_revision_duplicate_override_and_unknown_field():
    fixtures = _load(FIXTURE_DIR / "brand-project-boundary-entry-fixtures.json")
    validator = _validator("context-snapshot-v3.schema.json")
    valid = fixtures["valid"]

    missing_domain_revision = copy.deepcopy(valid["inherited_brand"])
    missing_domain_revision["brand_context"].pop("domain_revision")
    assert _errors(validator, missing_domain_revision)

    missing_media_revision = copy.deepcopy(valid["inherited_brand"])
    missing_media_revision["brand_context"]["values"]["logo_ref"].pop("asset_revision")
    assert _errors(validator, missing_media_revision)

    duplicate_override = copy.deepcopy(valid["project_overrides"])
    duplicate_override["brand_context"]["overridden_fields"].append("display_name")
    assert _errors(validator, duplicate_override)

    unknown = copy.deepcopy(valid["inherited_brand"])
    unknown["provider"] = "forbidden"
    assert _errors(validator, unknown)

    offer_required = _load(CONTRACT_DIR / "context-snapshot-v3.schema.json")["$defs"]["offer"][
        "required"
    ]
    assert len(offer_required) == len(set(offer_required))
    assert offer_required.count("price_facts") == 1


def test_v3_client_contract_rejects_forged_brand_context_and_server_projection_matches_revision():
    fixtures = _load(FIXTURE_DIR / "brand-project-boundary-entry-fixtures.json")
    resolver = fixtures["resolver_cases"]
    request_validator = _validator("context-snapshot-v3-write-request.schema.json")
    stored_validator = _validator("context-snapshot-v3.schema.json")

    assert _errors(request_validator, resolver["valid_client_request"]) == []
    assert _errors(request_validator, resolver["valid_unbranded_client_request"]) == []
    forged_errors = _errors(request_validator, resolver["forged_client_request"])
    assert forged_errors
    assert any("brand_context" in message for message in forged_errors)

    unbranded_override = copy.deepcopy(resolver["valid_unbranded_client_request"])
    unbranded_override["project_overrides"]["display_name"] = "无品牌伪覆盖"
    assert _errors(request_validator, unbranded_override)

    logo_clear = copy.deepcopy(resolver["valid_client_request"])
    logo_clear["project_overrides"]["logo_ref"] = None
    assert _errors(request_validator, logo_clear)

    bgm_clear = copy.deepcopy(resolver["valid_client_request"])
    bgm_clear["project_overrides"]["default_bgm_ref"] = None
    assert _errors(request_validator, bgm_clear)
    assert {item["id"] for item in resolver["invalid_client_policy_cases"]} == {
        "unbranded-project-override",
        "logo-null-clear",
        "bgm-null-clear",
    }

    revision_values = resolver["pinned_brand_revision"]["values"]
    expected_context = resolver["expected_server_brand_context"]
    overrides = resolver["valid_client_request"]["project_overrides"]
    overridden_fields = set(expected_context["overridden_fields"])
    for field_name, stored_value in expected_context["values"].items():
        if field_name in overridden_fields:
            assert stored_value == overrides[field_name]
        else:
            assert stored_value == revision_values[field_name]

    stored_payload = {
        "schema_version": 3,
        "brand_context": expected_context,
        "project_brief": resolver["valid_client_request"]["project_brief"],
    }
    assert _errors(stored_validator, stored_payload) == []

    contract = _load(CONTRACT_DIR / "brand-project-boundary-entry.contract.json")
    trust = contract["snapshot_trust_boundary"]
    assert trust["stored_brand_context_generation_authority"] == "server_resolver_only"
    assert trust["client_brand_context_field_allowed"] is False
    assert trust["unbranded_project_overrides"] == "must_be_empty"
    assert (
        trust["client_forgery_result_code"]
        == resolver["forged_client_request"]["expected_result_code"]
    )
    assert trust["entry_runtime_resolver_implemented"] is False

    clear_policy = contract["override_clear_policy"]
    assert clear_policy["entry_supports_null_clear"] is False
    assert clear_policy["logo_ref_null_override_allowed"] is False
    assert clear_policy["default_bgm_ref_null_override_allowed"] is False
    assert clear_policy["restore_brand_default"].startswith("Remove the project override field")
    assert "Enterprise Asset Library" in clear_policy["brand_without_logo_or_bgm"]


def test_zero_one_multiple_ready_brand_and_legacy_null_creation_matrix_is_frozen():
    fixtures = _load(FIXTURE_DIR / "brand-project-boundary-entry-fixtures.json")
    cases = {item["id"]: item for item in fixtures["project_creation_cases"]}
    assert set(cases) == {
        "zero-ready-brands",
        "one-ready-brand",
        "multiple-ready-brands",
        "legacy-null-brand-with-one-ready-brand",
    }
    assert cases["zero-ready-brands"]["expected_create_default_brand_id"] is None
    assert cases["zero-ready-brands"]["requires_brand_choice"] is False
    assert cases["one-ready-brand"]["expected_create_default_brand_id"] == "brand-only"
    assert cases["one-ready-brand"]["expected_existing_project_brand_id_after_read"] is None
    assert cases["multiple-ready-brands"]["expected_create_default_brand_id"] is None
    assert cases["multiple-ready-brands"]["requires_brand_choice"] is True
    assert (
        cases["legacy-null-brand-with-one-ready-brand"][
            "expected_existing_project_brand_id_after_read"
        ]
        is None
    )


def test_rollback_contract_is_complete_and_machine_fixtures_preserve_last_commit():
    contract = _load(CONTRACT_DIR / "brand-project-boundary-entry.contract.json")
    rollback = contract["rollback"]
    flag_off = rollback["flag_off"]
    assert flag_off == {
        "legacy_interaction_remains_active": True,
        "context_snapshot_read_versions": [1, 2, 3],
        "v3_remains_permanently_readable": True,
        "new_v3_writes_allowed": False,
        "brand_sync_allowed": False,
    }
    assert all(rollback["sync_failure_atomicity"].values())
    assert rollback["destructive_actions"] == {
        "delete_project": False,
        "delete_brand": False,
        "delete_context_snapshot": False,
        "archive_is_not_delete": True,
    }
    assert rollback["restart_recovery"]["read_v3_after_restart"] is True
    assert rollback["restart_recovery"]["resume_half_applied_sync"] is False
    assert rollback["reenable"]["continue_from_last_committed_state"] is True
    assert rollback["reenable"]["rebind_or_resnapshot_on_read"] is False

    fixtures = _load(FIXTURE_DIR / "brand-project-boundary-entry-fixtures.json")
    cases = {item["id"]: item for item in fixtures["rollback_cases"]}
    flag_case = cases["flag-off-preserves-v3-read-and-legacy-interaction"]
    assert flag_case["expected_readable"] is True
    assert flag_case["expected_new_v3_write_allowed"] is False
    assert flag_case["expected_interaction"] == "legacy"
    failed = cases["failed-sync-is-atomic"]
    assert failed["after"] == failed["before"]
    assert failed["deletes"] == []
    restarted = cases["restart-recovers-last-commit"]
    assert restarted["after_restart"]["brand_id"] == restarted["before_restart"]["brand_id"]
    assert (
        restarted["after_restart"]["current_context_snapshot_id"]
        == restarted["before_restart"]["current_context_snapshot_id"]
    )
    assert restarted["after_restart"]["snapshot_readable"] is True
    assert cases["reenable-continues-without-read-mutation"]["expected_read_mutation"] is False


def test_v3_to_v2_projection_is_frozen_and_valid_without_mutating_source():
    fixtures = _load(FIXTURE_DIR / "brand-project-boundary-entry-fixtures.json")
    source = copy.deepcopy(fixtures["valid"][fixtures["v2_projection"]["source"]])
    original = copy.deepcopy(source)
    projected = _v3_to_v2(source)

    assert projected == fixtures["v2_projection"]["expected"]
    assert source == original
    assert _errors(_validator("context-snapshot-v2.schema.json"), projected) == []

    unbranded = _v3_to_v2(fixtures["valid"]["unbranded_legacy_compatible"])
    assert unbranded["brand_revision_ref"] is None
    assert unbranded["store_or_brand"]["name"] == "到店咨询"
    assert unbranded["store_or_brand"]["address"] is None


def test_boundary_contract_freezes_ownership_revision_sync_and_legacy_rules():
    contract = _load(CONTRACT_DIR / "brand-project-boundary-entry.contract.json")
    assert contract["status"] == "entry_contract"
    assert contract["ownership"]["relationship"] == (
        "BrandKit 1:N ContentProject; ContentProject has zero or one BrandKit."
    )
    assert "ContentProject" in contract["ownership"]["content_project"]
    assert contract["field_ownership"]["override_user_label"] == "仅本项目使用"
    assert contract["field_ownership"]["override_writes_brand_kit"] is False
    assert set(contract["field_ownership"]["project_override_fields"]) == set(
        contract["field_ownership"]["brand_fields"]
    )

    creation = contract["project_creation"]
    assert creation["one_ready_brand"].endswith("explicit create POST carries brand_id")
    assert creation["read_auto_binds_brand"] is False
    assert creation["read_creates_context_snapshot"] is False

    revision = contract["revision"]
    assert revision["brand_domain_revision_required"] is True
    assert revision["logo_media_revision_required"] is True
    assert revision["default_bgm_media_revision_required"] is True
    assert revision["historical_snapshot_mutation"] is False
    assert revision["brand_update_auto_propagates"] is False
    assert revision["sync_requires_explicit_user_confirmation"] is True
    assert revision["sync_appends_snapshot"] is True
    assert revision["sync_no_change_appends_snapshot"] is False

    compatibility = contract["compatibility"]
    assert compatibility["legacy_null_brand_id_auto_bind"] is False
    assert compatibility["context_snapshot_read_versions"] == [1, 2, 3]
    assert compatibility["context_snapshot_new_write_version"] == 3
    assert compatibility["v3_to_v2_projection_required_before_v3_writes"] is True
    assert compatibility["feature_flag_off_can_read_v3"] is True


def test_error_codes_and_feature_flag_are_frozen_default_off():
    contract = _load(CONTRACT_DIR / "brand-project-boundary-entry.contract.json")
    errors = contract["error_codes"]
    assert [item["code"] for item in errors] == [
        "PROJECT_BRAND_NOT_FOUND",
        "PROJECT_BRAND_NOT_BOUND",
        "PROJECT_BRAND_NOT_AVAILABLE",
        "PROJECT_BRAND_REVISION_NOT_FOUND",
        "PROJECT_CONTEXT_CONFLICT",
        "PROJECT_BRAND_ASSET_REVISION_MISSING",
        "PROJECT_BRAND_CONTEXT_UNTRUSTED",
        "BRAND_PROJECT_BOUNDARY_DISABLED",
    ]
    assert len({item["code"] for item in errors}) == len(errors)
    assert all(item["user_message"] and "brand_" not in item["user_message"] for item in errors)
    result_codes = contract["result_codes"]
    assert result_codes == [
        {
            "code": "PROJECT_BRAND_SYNC_NO_CHANGE",
            "http_status": 200,
            "user_message": "已是最新品牌资料",
            "changes_committed": False,
        }
    ]
    assert result_codes[0]["code"] not in {item["code"] for item in errors}

    flag = contract["feature_flag"]
    assert flag == {
        "name": "brandProjectBoundaryV1",
        "env": "PIXELLE_BRAND_PROJECT_BOUNDARY_V1",
        "default": False,
        "owner_stage": "BRAND-PROJECT-3",
        "controls_new_writes": True,
        "controls_v3_read_compatibility": False,
        "unknown_or_conflicting": False,
    }
    matrix = _load(CONTRACT_DIR / "feature-flag-matrix.json")
    matrix_flag = {item["name"]: item for item in matrix["flags"]}[flag["name"]]
    assert matrix_flag == {
        "name": flag["name"],
        "env": flag["env"],
        "default": False,
        "owner_stage": flag["owner_stage"],
    }


def test_entry_contract_hides_technical_fields_and_forbids_external_actions():
    contract = _load(CONTRACT_DIR / "brand-project-boundary-entry.contract.json")
    assert set(contract["ordinary_user_hidden_fields"]) == {
        "brand_id",
        "domain_revision",
        "asset_revision",
        "context_snapshot_id",
        "source_brand_id",
        "source_brand_revision_id",
        "fingerprint",
    }
    assert contract["entry_boundaries"] == {
        "business_ui_changes": 0,
        "business_write_logic_changes": 0,
        "production_database_writes": 0,
        "llm_calls": 0,
        "runninghub_calls": 0,
        "browser_or_platform_actions": 0,
        "final_publish_clicks": 0,
        "desktop_live_db_before_after_assertion": ("deferred_to_BRAND-PROJECT-3_PG-BP-D"),
        "program_rollout_checkpoint": "PROGRAM-ROLLOUT/PG-L paused_external and unchanged",
    }

    payloads = [
        contract,
        _load(CONTRACT_DIR / "context-snapshot-v3.schema.json"),
        _load(FIXTURE_DIR / "brand-project-boundary-entry-fixtures.json"),
    ]
    encoded = json.dumps(payloads, ensure_ascii=False).lower()
    assert "sk-" not in encoded
    assert "ark-" not in encoded
    assert "/users/" not in encoded
    assert "c:\\" not in encoded


def test_existing_models_have_the_required_brand_project_revision_seams():
    assert "brand_id" in {item.name for item in fields(ContentProject)}
    assert {
        "source_brand_id",
        "source_brand_revision_id",
        "fingerprint",
    } <= {item.name for item in fields(ContextSnapshot)}
    assert {
        "brand_name",
        "logo_asset_id",
        "default_bgm_asset_id",
        "primary_color",
        "secondary_color",
        "font_family",
        "default_subtitle_style",
        "ending_card_text",
        "store_address",
        "phone",
        "coupon_phrase",
    } <= set(BrandKitV2Request.model_fields)


def test_app_center_repository_reads_do_not_mutate_project_or_snapshots(tmp_path: Path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite3")
    project = repository.create_project("旧项目", "保持读取兼容", None)
    snapshot = repository.save_context_snapshot(
        project.project_id,
        {"store_name": "旧门店", "offer_name": "旧服务"},
        schema_version=1,
    )
    before = {
        "projects": _table_rows(repository.db_path, "content_projects"),
        "snapshots": _table_rows(repository.db_path, "context_snapshots"),
    }

    for _ in range(3):
        listed = repository.list_projects()
        loaded = repository.get_project(project.project_id)
        loaded_snapshot = repository.get_context_snapshot(snapshot.context_snapshot_id)
        assert listed[0].brand_id is None
        assert loaded.brand_id is None
        assert loaded_snapshot.project_id == project.project_id

    after = {
        "projects": _table_rows(repository.db_path, "content_projects"),
        "snapshots": _table_rows(repository.db_path, "context_snapshots"),
    }
    assert after == before


def test_asset_library_brand_reads_do_not_mutate_brand_or_domain_revisions(tmp_path: Path):
    repository = AssetLibraryRepository(tmp_path / "asset-root")
    brand = repository.create_brand_kit(
        {
            "brand_id": "brand-only",
            "brand_name": "唯一品牌",
            "primary_color": "#6C5CE7",
            "secondary_color": "#F2EEFF",
        }
    )
    before = {
        "brands": _table_rows(repository.db_path, "brand_kits_v2"),
        "revisions": _table_rows(repository.db_path, "domain_revisions"),
    }

    for _ in range(3):
        items = repository.list_domain_items("brand", "", False, 100, 0)
        loaded = repository.get_domain_item("brand", brand["resource_id"])
        metadata = repository.domain_snapshot_metadata("brand", brand["resource_id"])
        revisions = repository.list_domain_revisions("brand", brand["resource_id"])
        assert len(items) == 1
        assert loaded and metadata["domain_revision"] == 1
        assert len(revisions) == 1

    after = {
        "brands": _table_rows(repository.db_path, "brand_kits_v2"),
        "revisions": _table_rows(repository.db_path, "domain_revisions"),
    }
    assert after == before


def test_api_and_desktop_owned_read_routes_leave_both_sqlite_databases_byte_equivalent(
    monkeypatch, tmp_path: Path
):
    app_repository = AppCenterRepository(tmp_path / "app-center-api.sqlite3")
    project = app_repository.create_project("API 读取项目", "保持零写入", None)
    snapshot = app_repository.save_context_snapshot(
        project.project_id,
        {"store_name": "旧门店", "offer_name": "旧服务"},
        schema_version=1,
    )
    asset_repository = AssetLibraryRepository(tmp_path / "asset-api-root")
    brand = asset_repository.create_brand_kit(
        {
            "brand_id": "brand-api-read",
            "brand_name": "API 只读品牌",
            "primary_color": "#6C5CE7",
            "secondary_color": "#F2EEFF",
        }
    )

    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app_repository)
    monkeypatch.setattr(assets_v2_api, "get_asset_repository", lambda: asset_repository)
    monkeypatch.setattr(assets_v2_api.api_config, "asset_center_v2_enabled", True)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    api.include_router(assets_v2_api.router, prefix="/api")
    client = TestClient(api)

    before = {
        "app_center": _database_state(app_repository.db_path),
        "asset_library": _database_state(asset_repository.db_path),
    }
    for _ in range(3):
        listed_projects = client.get("/api/content-projects")
        loaded_project = client.get(f"/api/content-projects/{project.project_id}")
        loaded_snapshot = client.get(
            f"/api/content-projects/{project.project_id}/context-snapshots"
        )
        listed_brands = client.get(
            "/api/v2/library/items", params={"kind": "brand", "status": "ready"}
        )
        loaded_brand = client.get(f"/api/v2/library/items/{brand['resource_id']}")
        assert listed_projects.status_code == 200
        assert listed_projects.json()[0]["brand_id"] is None
        assert loaded_project.status_code == 200
        assert loaded_project.json()["brand_id"] is None
        assert loaded_snapshot.status_code == 200
        assert loaded_snapshot.json()["context_snapshot_id"] == snapshot.context_snapshot_id
        assert listed_brands.status_code == 200
        assert listed_brands.json()["items"][0]["resource_id"] == "brand-api-read"
        assert loaded_brand.status_code == 200
        assert loaded_brand.json()["resource_id"] == "brand-api-read"

    after = {
        "app_center": _database_state(app_repository.db_path),
        "asset_library": _database_state(asset_repository.db_path),
    }
    assert after == before

    desktop_api_source = (ROOT / "desktop/src/api.ts").read_text(encoding="utf-8")
    desktop_read_contracts = {
        "listContentProjects": "/api/content-projects?include_archived=",
        "getCurrentContextSnapshot": "/context-snapshots",
        "listLibraryItemsV2": "/api/v2/library/items?",
    }
    for function_name, route_fragment in desktop_read_contracts.items():
        function_block = _typescript_exported_function(desktop_api_source, function_name)
        assert route_fragment in function_block
        assert "method:" not in function_block

    contract = _load(CONTRACT_DIR / "brand-project-boundary-entry.contract.json")
    read_contract = contract["read_no_write"]
    assert read_contract["entry_claim_scope"].startswith(
        "API integration has full SQLite before/after equality"
    )
    assert read_contract["desktop_live_db_before_after_owner_gate"] == "BRAND-PROJECT-3/PG-BP-D"


def test_entry_attribution_and_visual_evidence_hashes_are_verifiable():
    qa_root = ROOT / "docs/reviews/application-publishing-program/qa"
    attribution = _load(qa_root / "BRAND-PROJECT-0-entry-attribution-baseline-2026-07-29.json")
    assert attribution["entry_starting_commit"] == ("8de798d260459bb0e62d44b0bb7ab670f4b8b92f")
    implemented_stage_owners = {
        "api/routers/app_center.py",
        "api/schemas/app_center.py",
        "pixelle_video/app_center/models.py",
        "pixelle_video/app_center/repository.py",
        "pixelle_video/app_center/project_context.py",
        "desktop/src/api.ts",
        "desktop/src/styles.css",
        "desktop/src/features/app-workbench/ProjectContextSelector.tsx",
    }
    for item in attribution["prohibited_business_files"]:
        path = ROOT / item["path"]
        assert path.is_file(), item["path"]
        if item["path"] not in implemented_stage_owners:
            assert _sha256(path) == item["sha256"], item["path"]

    visual_root = qa_root / "BRAND-PROJECT-0-visual-baseline-2026-07-29"
    manifest = _load(visual_root / "manifest.json")
    assert manifest["business_ui_changes_during_capture"] == 0
    assert manifest["baseline_only"] is True
    assert manifest["remediation_owner_stage"] == "BRAND-PROJECT-3"
    for item in manifest["files"]:
        path = visual_root / item["path"]
        assert path.is_file(), item["path"]
        assert _sha256(path) == item["sha256"], item["path"]

    dom_text = (visual_root / "marketing-copy-current-dom.txt").read_text(encoding="utf-8")
    for visible_label in ("选择项目", "项目名称", "本次营销目标", "项目操作"):
        assert visible_label in dom_text
