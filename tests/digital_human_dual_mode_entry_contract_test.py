import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/app-center/digital-human-video-input-v2.contract.json")
FIXTURE_PATH = Path("docs/contracts/app-center/fixtures/digital-human-video-input-v2-fixtures.json")


def _load():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8")), json.loads(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )


def test_dual_mode_contract_separates_content_source_and_media_mode():
    contract, fixtures = _load()

    assert contract["contract_id"] == "digital-human-video-input-v2"
    assert contract["schema_version"] == 2
    assert contract["scope"]["content_source_and_digital_human_mode_are_independent"] is True
    assert {item["mode"] for item in contract["digital_human"]["modes"]} == {
        "image_talking",
        "video_lipsync",
    }
    assert {item["asset_media_type"] for item in contract["digital_human"]["modes"]} == {
        "image",
        "video",
    }
    assert {item["mode"] for item in contract["content_source"]["modes"]} >= {
        "custom_script",
        "copywriting_artifact",
        "generated_marketing_copy",
        "title_plus_copywriting",
    }
    assert (
        contract["content_source"]["forbidden_new_mode"] == "selected_title_without_script_source"
    )
    assert contract["delivery"]["default_preview_artifact"] == "final_video"
    assert contract["delivery"]["raw_artifact_role"] == "diagnostic_only"
    assert contract["outputs"]["accept_does_not_publish"] is True
    assert contract["registry_migration"]["mapping_required_before_dh_dual_1"] is True
    assert contract["registry_migration"]["entry_does_not_mutate_registry"] is True
    assert contract["feature_flags"]["joint_gate"]["both_flags_must_be_on_for_v2"] is True
    assert (
        contract["feature_flags"]["joint_gate"]["dual_flag_cannot_bypass_backend_readiness"] is True
    )
    assert fixtures["entry_expectations"] == {
        "provider_calls": 0,
        "browser_actions": 0,
        "platform_writes": 0,
        "final_publish_clicks": 0,
        "no_business_code_changed": True,
    }


def test_workflow_profiles_are_mode_bound_and_only_unverified_profiles_remain_candidate():
    contract, _ = _load()
    profiles = contract["workflow_profiles"]
    pairs = {(item["mode"], item["profile"]) for item in profiles}
    assert len(pairs) == len(profiles)
    for item in profiles:
        assert item["portrait_media_type"] == (
            "image" if item["mode"] == "image_talking" else "video"
        )
        assert (
            item[
                "provider_live_required_before_default"
                if item["mode"] == "image_talking"
                else "provider_live_required_before_available"
            ]
            is True
        )
    candidates = [item for item in profiles if item["release_state"] == "candidate"]
    assert {(item["mode"], item["profile"]) for item in candidates} == {
        ("image_talking", "natural")
    }
    video = next(item for item in profiles if item["mode"] == "video_lipsync")
    assert video["release_state"] == "stable"
    assert video["live_gate"] == "passed_with_boundary"
    assert video["default_mode"] is False


def test_v2_fixtures_cover_both_modes_compatibility_and_fail_closed_boundaries():
    contract, payload = _load()
    fixtures = payload["fixtures"]
    by_id = {item["id"]: item for item in fixtures}
    content_modes = {item["mode"]: item for item in contract["content_source"]["modes"]}
    digital_modes = {item["mode"]: item for item in contract["digital_human"]["modes"]}

    assert {"image-custom-script-valid", "video-copywriting-valid"} <= by_id.keys()
    assert {"v1-blank-project-compat", "v1-selected-title-resume-only"} <= by_id.keys()
    assert {item["id"] for item in fixtures if not item["valid"]} >= {
        "title-only-new-run-invalid",
        "image-mode-video-asset-invalid",
        "video-mode-image-asset-invalid",
        "video-too-short-invalid",
        "workflow-profile-not-released-invalid",
        "path-and-secret-injection-invalid",
        "asset-revision-drift-invalid",
    }

    error_codes = set(contract["error_codes"])
    for fixture in fixtures:
        if not fixture["valid"]:
            assert fixture["error"] in error_codes, fixture["id"]
            continue
        input_payload = fixture["input"]
        if input_payload.get("schema_version") == 2:
            content_source = input_payload["content_source"]
            digital_human = input_payload["digital_human"]
            content_mode = content_modes[content_source["mode"]]
            assert all(key in content_source for key in content_mode["required"]), fixture["id"]
            assert all(key in digital_human for key in contract["digital_human"]["required"]), (
                fixture["id"]
            )
            if fixture.get("asset"):
                assert (
                    fixture["asset"]["media_type"]
                    == digital_modes[digital_human["mode"]]["asset_media_type"]
                )
            expected_capability = fixture.get("expected", {}).get("workflow_capability")
            if expected_capability:
                assert (
                    expected_capability
                    in digital_modes[digital_human["mode"]]["workflow_capabilities"]
                )

    assert by_id["v1-blank-project-compat"]["input"]["source_mode"] == "blank_project"
    assert by_id["v1-selected-title-resume-only"]["input"]["resume_mode"] == "resume_existing"

    assert by_id["image-mode-video-asset-invalid"]["asset"]["media_type"] == "video"
    assert by_id["video-mode-image-asset-invalid"]["asset"]["media_type"] == "image"
    assert by_id["video-too-short-invalid"]["asset"]["duration_ms"] < 5000
    assert by_id["path-and-secret-injection-invalid"]["input"]["api_key"]
    assert by_id["path-and-secret-injection-invalid"]["input"]["provider_url"].startswith(
        "https://"
    )
    assert by_id["path-and-secret-injection-invalid"]["input"]["digital_human_workflow"].startswith(
        "/"
    )
    assert by_id["v1-selected-title-resume-only"]["expected"]["new_v2_run_allowed"] is False


def test_quality_and_safety_contract_is_explicit():
    contract, _ = _load()
    cover = contract["delivery"]["cover_title"]
    subtitle = contract["delivery"]["subtitle"]
    security = contract["security"]
    live = contract["live_test_policy"]

    assert cover["recommended_character_range"] == [12, 18]
    assert cover["hard_max_display_characters"] == 24
    assert cover["max_lines"] == 2
    assert cover["must_not_fallback_to_script_prefix"] is True
    assert subtitle["default_preset"] == "readable_v2"
    assert subtitle["burned_in"] is True
    assert subtitle["font_size_range"] == [44, 56]
    assert "absolute_path" in security["frontend_must_not_send"]
    assert "workflow_file_path" in security["frontend_must_not_send"]
    assert "provider_url" in security["frontend_must_not_send"]
    assert security["workflow_selection"] == "profile_allowlist_only"
    assert live["entry_provider_calls"] == 0
    assert live["post_entry_image_calls"] == 1
    assert live["post_entry_video_calls"] == 1
    assert live["blind_retries"] is False
    assert live["final_publish_clicks"] == 0
