import copy
import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "docs/contracts/app-center"
FIXTURE_DIR = CONTRACT_DIR / "fixtures"


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str) -> Draft202012Validator:
    schema = _load(CONTRACT_DIR / name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _errors(validator: Draft202012Validator, payload: dict) -> list[str]:
    return [error.message for error in validator.iter_errors(payload)]


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield str(key).lower()
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def test_context_snapshot_v2_contract_accepts_project_brief_and_rejects_unknown_or_unpinned_assets():
    fixture = _load(FIXTURE_DIR / "app-workbench-entry-fixtures.json")
    validator = _validator("context-snapshot-v2.schema.json")
    valid = fixture["context_snapshot_valid"]
    assert _errors(validator, valid) == []

    unknown = copy.deepcopy(valid)
    unknown["provider"] = "forbidden"
    assert _errors(validator, unknown)

    missing_revision = copy.deepcopy(valid)
    missing_revision["asset_refs"][0].pop("asset_revision")
    assert _errors(validator, missing_revision)

    unsupported = copy.deepcopy(valid)
    unsupported["schema_version"] = 3
    assert _errors(validator, unsupported)


def test_style_registry_has_stable_unique_versions_and_full_first_release_catalog():
    registry = _load(FIXTURE_DIR / "style-preset-registry-v1.json")
    validator = _validator("style-preset.schema.json")
    presets = registry["presets"]
    assert all(_errors(validator, item) == [] for item in presets)

    identities = [(item["style_id"], item["version"]) for item in presets]
    assert len(identities) == len(set(identities))
    assert len([item for item in presets if item["family"] == "copy"]) == 8
    assert len([item for item in presets if item["family"] == "title"]) == 8
    assert len([item for item in presets if item["family"] == "carousel"]) == 4
    assert all(item["status"] == "active" for item in presets)
    assert {
        "copy.owner_voice",
        "copy.buyer_perspective",
        "title.contrast",
        "title.promotion",
        "carousel.store_recommendation",
        "carousel.case_breakdown",
    } <= {item["style_id"] for item in presets}


def test_workbench_input_v2_accepts_all_four_apps_and_rejects_forbidden_entry_cases():
    fixture = _load(FIXTURE_DIR / "app-workbench-entry-fixtures.json")
    validator = _validator("app-workbench-input-v2.schema.json")

    assert {item["app_id"] for item in fixture["input_valid"]} == {
        "builtin.marketing-copy",
        "builtin.viral-titles",
        "builtin.douyin-carousel",
        "builtin.digital-human-video",
    }
    for case in fixture["input_valid"]:
        assert _errors(validator, case) == [], case["app_id"]

    for case in fixture["input_invalid"]:
        assert _errors(validator, case["payload"]), case["id"]


def test_custom_style_reference_is_run_scoped_and_cannot_import_facts():
    fixture = _load(FIXTURE_DIR / "app-workbench-entry-fixtures.json")
    validator = _validator("app-workbench-input-v2.schema.json")
    payload = copy.deepcopy(fixture["input_valid"][0])
    payload["style_ref"] = None
    payload["custom_style_reference"] = {
        "text": "只参考短句节奏，不复制其中的品牌、价格和效果",
        "content_fingerprint": f"sha256:{'1' * 64}",
        "facts_imported": False,
    }
    assert _errors(validator, payload) == []

    payload["custom_style_reference"]["facts_imported"] = True
    assert _errors(validator, payload)


def test_result_projection_has_no_fake_failure_artifact_or_unknown_progress_percent():
    fixture = _load(FIXTURE_DIR / "app-workbench-entry-fixtures.json")
    validator = _validator("app-workbench-result-state.schema.json")
    for case in fixture["result_valid"]:
        assert _errors(validator, case) == [], case["view_state"]

    failed_with_artifact = copy.deepcopy(fixture["result_valid"][-1])
    failed_with_artifact["artifact_ids"] = ["artifact-fake"]
    assert _errors(validator, failed_with_artifact)

    running = copy.deepcopy(fixture["result_valid"][1])
    running["progress_percent"] = 37
    assert _errors(validator, running)


def test_handoff_contract_pins_source_version_and_never_hot_updates_or_publishes():
    contract = _load(CONTRACT_DIR / "app-workbench-entry.contract.json")
    fixture = _load(FIXTURE_DIR / "app-workbench-entry-fixtures.json")
    handoff = contract["handoff"]
    assert handoff["source_version_pinned"] is True
    assert handoff["same_project_required"] is True
    assert handoff["retry_idempotent"] is True
    assert handoff["source_update_behavior"] == "notify only; never hot-update target run"
    assert handoff["final_publish_click"] is False
    assert len(handoff["allowed_routes"]) == 7

    cases = {item["id"]: item for item in fixture["handoff_cases"]}
    assert cases["copy-to-title-valid"]["source_version_pinned"] is True
    assert cases["copy-to-title-valid"]["final_publish_click"] is False
    assert cases["cross-project-invalid"]["expected_error"] == "SOURCE_VERSION_PROJECT_MISMATCH"
    assert cases["source-update-not-hot-applied"]["target_action"] == "notify_only"
    assert (
        cases["source-update-not-hot-applied"]["target_run_source_artifact_version_id"]
        != cases["source-update-not-hot-applied"]["new_source_artifact_version_id"]
    )


def test_entry_contract_preserves_architecture_security_and_rollback_boundaries():
    contract = _load(CONTRACT_DIR / "app-workbench-entry.contract.json")
    assert contract["status"] == "entry_contract"
    assert contract["architecture"] == {
        "frontend": "React/Tauri",
        "api": "FastAPI",
        "domain": "pixelle_video.app_center",
        "database": "SQLite",
        "model_source": "existing AppLLMPort/local-default only",
        "asset_source": "existing AssetLibrary",
        "publishing_boundary": "typed handoff to PublishPackage; final publish remains human",
    }
    assert contract["migration"]["entry_database_writes"] == 0
    assert contract["migration"]["entry_business_ui_changes"] == 0
    assert contract["migration"]["old_projects_runs_artifacts_preserved"] is True
    assert contract["migration"]["running_app_run_survives_ui_rollback"] is True
    assert contract["concurrency"]["project_switch"].startswith("AbortController")
    assert contract["external_actions"] == {
        "llm_calls": 0,
        "runninghub_calls": 0,
        "browser_or_platform_actions": 0,
        "final_publish_clicks": 0,
    }


def test_entry_fixtures_and_contract_do_not_contain_credentials_or_absolute_paths():
    contract = _load(CONTRACT_DIR / "app-workbench-entry.contract.json")
    fixture_payloads = [
        _load(FIXTURE_DIR / "app-workbench-entry-fixtures.json"),
        _load(FIXTURE_DIR / "style-preset-registry-v1.json"),
    ]
    forbidden_keys = {"api_key", "authorization", "cookie", "base_url", "browser_profile"}
    for payload in fixture_payloads:
        assert forbidden_keys.isdisjoint(set(_walk_keys(payload)))
    for payload in [contract, *fixture_payloads]:
        encoded = json.dumps(payload, ensure_ascii=False).lower()
        assert "sk-" not in encoded
        assert "ark-" not in encoded
        assert "/users/" not in encoded
        assert "c:\\" not in encoded


def test_workbench_feature_flags_are_default_off_and_owned_by_later_stages():
    matrix = _load(CONTRACT_DIR / "feature-flag-matrix.json")
    flags = {item["name"]: item for item in matrix["flags"]}
    expected = {
        "appWorkbenchV2": ("PIXELLE_APP_WORKBENCH_V2", "APP-WORKBENCH-1"),
        "appWorkbenchTextV2": ("PIXELLE_APP_WORKBENCH_TEXT_V2", "APP-WORKBENCH-3"),
        "appWorkbenchCarouselV2": ("PIXELLE_APP_WORKBENCH_CAROUSEL_V2", "APP-WORKBENCH-4"),
        "appWorkbenchDigitalHumanV2": ("PIXELLE_APP_WORKBENCH_DIGITAL_HUMAN_V2", "APP-WORKBENCH-5"),
    }
    for name, (env, owner) in expected.items():
        assert flags[name]["env"] == env
        assert flags[name]["owner_stage"] == owner
        assert flags[name]["default"] is False
    assert matrix["unknown_flag_behavior"] == "false"
    assert matrix["frontend_cannot_write"] is True


def test_entry_visual_baseline_manifest_has_four_apps_at_three_requested_viewports():
    qa = _load(
        ROOT
        / "docs/reviews/application-publishing-program/qa/APP-WORKBENCH-0-entry-2026-07-28.json"
    )
    baselines = qa["baselines"]
    assert baselines["requested_viewports"] == ["1440x900", "1280x800", "900x760"]
    assert baselines["browser_reported_viewports_match_requested"] is True
    assert all(
        baselines["identity_and_backend_checks"][app]
        for app in (
            "marketing-copy",
            "viral-titles",
            "douyin-carousel",
            "digital-human",
        )
    )
    assert baselines["identity_and_backend_checks"]["backend_disconnected_banner"] is False
    assert baselines["identity_and_backend_checks"]["application_catalog_unavailable"] is False
    assert len(baselines["files"]) == 12

    seen = set()
    for item in baselines["files"]:
        path = ROOT / item["path"]
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
        assert data[:3] == b"\xff\xd8\xff"
        with Image.open(path) as image:
            assert image.format == "JPEG"
            width, height = image.size
        assert f"{width}x{height}" == item["image_pixels"]
        seen.add((path.name.split("-")[0], item["requested_viewport"]))

    assert {item["requested_viewport"] for item in baselines["files"]} == {
        "1440x900",
        "1280x800",
        "900x760",
    }
    assert qa["external_actions"]["final_publish_clicks"] == 0
