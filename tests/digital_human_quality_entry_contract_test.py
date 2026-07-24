import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/app-center/digital-human-quality-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/app-center/fixtures/digital-human-quality-entry-fixtures.json")


def _load():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8")), json.loads(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )


def test_quality_entry_freezes_source_ownership_and_field_separation():
    contract, _ = _load()

    assert contract["stage"] == "DH-QUALITY-1"
    assert contract["entry_policy"]["business_code_changed"] is False
    assert {item["mode"] for item in contract["content_sources"]} == {
        "custom_script",
        "copywriting_artifact",
        "generated_marketing_copy",
        "title_plus_copywriting",
    }
    assert contract["mode_aliases"] == {
        "marketing_copy_artifact": "copywriting_artifact",
        "selected_title_with_copy": "title_plus_copywriting",
        "alias_policy": "accept_only_at_boundary_then_normalize_to_canonical",
        "server_normalizer_owner": "pixelle_video.app_center.digital_human_input",
    }
    required_fields = contract["field_separation"]["required_run_fields"]
    assert (
        required_fields["spoken_script"]["path"]
        == "content_source.script | source_artifact.variants[selected_variant_index].full_text"
    )
    assert contract["content_sources"][0]["run_field"] == "spoken_script"
    assert contract["delivery_payload"]["fields"]["publish_description"]["type"] == "string"
    assert required_fields["hashtags"]["type"] == "array<string>"
    assert contract["field_separation"]["source_version_pinned_at_run_creation"] is True
    assert contract["field_separation"]["source_changes_do_not_hot_update_run"] is True


def test_quality_entry_freezes_cover_subtitle_and_artifact_acceptance():
    contract, _ = _load()
    cover = contract["cover"]
    subtitle = contract["subtitle"]
    artifacts = contract["artifact_delivery"]

    assert cover["title"]["recommended_characters"] == [12, 18]
    assert cover["title"]["hard_max_display_characters"] == 24
    assert cover["title"]["max_lines"] == 2
    assert "spoken_script_first_40_characters" in cover["title"]["forbidden_fallbacks"]
    assert subtitle["preset"] == "readable_v2"
    assert subtitle["default_enabled"] is True
    assert subtitle["burned_in"] is True
    assert subtitle["font_size_px"] == 48
    assert subtitle["old_run_without_preset"] == "preserve_original_render_semantics"
    assert artifacts["default_preview"] == "final_video"
    assert artifacts["raw_digital_human_video"] == "diagnostic_only"
    assert artifacts["accept_does_not_publish"] is True


def test_quality_entry_fixtures_cover_valid_sources_and_failure_matrix():
    contract, payload = _load()
    fixtures = payload["fixtures"]
    by_id = {item["id"]: item for item in fixtures}
    failure_codes = {item["code"] for item in contract["failure_matrix"]}

    assert {
        "custom-script-exact",
        "marketing-copy-upstream-artifact",
        "selected-title-bound-copy",
    } <= by_id.keys()
    assert {
        "goal-is-not-spoken-script",
        "title-only-rejected",
        "cross-project-binding-rejected",
        "cover-title-hard-limit",
        "cover-prefix-fallback-rejected",
        "artifact-incomplete-blocks-accept",
    } <= by_id.keys()
    for fixture in fixtures:
        if not fixture["valid"]:
            assert fixture["error"] in failure_codes

    assert by_id["custom-script-exact"]["expected"]["script_mutated"] is False
    assert by_id["marketing-copy-upstream-artifact"]["expected"]["media_adapter_llm_calls"] == 0
    assert by_id["selected-title-bound-copy"]["expected"]["spoken_script_source"] == "av-copy-1"
    assert by_id["new-run-readable-v2"]["expected"]["default_preview"] == "final_video"
    assert by_id["old-run-style-preserved"]["expected"]["render_semantics"] == "preserve_original"
    assert contract["mode_aliases"]["marketing_copy_artifact"] == "copywriting_artifact"


def test_quality_entry_forbids_provider_and_platform_side_effects():
    contract, payload = _load()

    assert payload["entry_expectations"] == {
        "business_code_changed": False,
        "provider_calls": 0,
        "browser_platform_actions": 0,
        "final_publish_clicks": 0,
        "default_flags_changed": False,
    }
    assert "call_tts_or_runninghub" in contract["forbidden_in_entry"]
    assert "final_publish_click" in contract["forbidden_in_entry"]
    assert contract["rollback"]["preserve_v1_and_existing_runs"] is True
