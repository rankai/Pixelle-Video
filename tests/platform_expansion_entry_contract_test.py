import json
from pathlib import Path

from pixelle_video.services.publish.platforms.multiplatform import (
    KuaishouPublisher,
    ShipinhaoPublisher,
    XiaohongshuPublisher,
)

ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return json.loads(
        (ROOT / "docs/contracts/publishing/platform-expansion-entry.contract.json").read_text()
    )


def test_platform_expansion_entry_freezes_three_platforms_and_manual_stop():
    contract = _contract()
    assert contract["stage"] == "PLATFORM-EXPANSION"
    assert set(contract["platforms"]) == {"kuaishou", "shipinhao", "xiaohongshu"}
    invariants = contract["common_invariants"]
    assert invariants["runtime"] == "playwright"
    assert invariants["visible_headful"] is True
    assert invariants["human_confirmation_required"] is True
    assert invariants["allow_final_publish"] is False
    assert invariants["final_publish_click_count_expected"] == 0
    assert invariants["release_state_unchanged"] is True
    assert invariants["release_gate_authority"] == "repository_only_evidence_ref"
    assert invariants["default_platform_release_states"]["kuaishou"] == "unverified"
    assert invariants["default_platform_release_states"]["shipinhao"] == "unverified"
    assert invariants["default_platform_release_states"]["xiaohongshu"] == "unverified"


def test_platform_expansion_publishers_are_real_platform_types():
    class Runtime:
        pass

    assert KuaishouPublisher(Runtime()).platform == "kuaishou"
    assert ShipinhaoPublisher(Runtime()).platform == "shipinhao"
    assert XiaohongshuPublisher(Runtime()).platform == "xiaohongshu"


def test_video_channel_account_alias_uses_shipinhao_adapter_identity():
    from pixelle_video.services.publish.platforms.base import HumanConfirmedPublisher

    publisher = HumanConfirmedPublisher(object(), "video_channel")
    assert publisher.platform == "shipinhao"
    assert publisher.profile is not None
    assert publisher.profile.adapter_version == "shipinhao-video@1"


def test_platform_expansion_contract_requires_external_boundaries_and_readback():
    contract = _contract()
    assert {"qr_scan", "third_party_authorization", "captcha_or_challenge", "final_publish_button"}.issubset(
        contract["external_boundaries"]
    )
    assert {
        "single_video_upload_and_readback",
        "title_description_readback",
        "final_action_guard_armed",
        "final_publish_click_count",
    }.issubset(contract["required_evidence"])
    shipinhao = contract["platforms"]["shipinhao"]
    assert shipinhao["media_identity_policy"] == "explicit_boundary_allowed_no_fake_remote_id"
    assert shipinhao["media_identity_boundary"] == "SHIPINHAO_NO_STABLE_REMOTE_MEDIA_ID"
    assert shipinhao["cover_receipt_policy"] == "ui_confirmed_https_receipt"
    xiaohongshu = contract["platforms"]["xiaohongshu"]
    assert xiaohongshu["media_identity_policy"] == "explicit_boundary_allowed_no_fake_remote_id"
    assert xiaohongshu["media_identity_boundary"] == "XIAOHONGSHU_NO_STABLE_REMOTE_MEDIA_ID"
    assert xiaohongshu["cover_receipt_policy"] == "ui_confirmed_local_blob_preview_boundary_no_remote_url"
    assert xiaohongshu["cover_receipt_boundary"] == "XIAOHONGSHU_LOCAL_BLOB_PREVIEW_ONLY"


def test_platform_expansion_failure_matrix_is_fail_closed_for_each_platform():
    matrix = json.loads(
        (ROOT / "docs/contracts/publishing/platform-expansion-failure-matrix.contract.json").read_text()
    )
    assert set(matrix["platforms"]) == {"kuaishou", "shipinhao", "xiaohongshu"}
    assert len(matrix["cases"]) >= 10
    assert all(case["final_publish_click_count"] == 0 for case in matrix["cases"])
    assert matrix["invariants"]["retry_same_video_after_failure"] is False
    assert matrix["invariants"]["final_action_default"] == "deny"


def test_live_entry_probe_is_boundary_only_and_never_promotes_release_state():
    evidence = json.loads(
        (
            ROOT
            / "docs/reviews/application-publishing-program/qa/PLATFORM-EXPANSION-live-entry-probe-2026-07-22.json"
        ).read_text()
    )
    assert evidence["mutation_policy"]["navigation_only"] is True
    assert evidence["mutation_policy"]["upload_count"] == 0
    assert evidence["mutation_policy"]["final_publish_click_count"] == 0
    assert all(item["release_gate"] == "unverified" for item in evidence["platforms"].values())
    assert evidence["platforms"]["kuaishou"]["observed_state"] == "signed_out"
    assert evidence["platforms"]["xiaohongshu"]["observed_state"] == "signed_out"
    assert evidence["platforms"]["shipinhao"]["result"] == "blocked_browser_policy"


def test_kuaishou_live_gate_evidence_is_machine_asserted_and_fail_closed():
    evidence = json.loads(
        (
            ROOT
            / "docs/reviews/application-publishing-program/qa/PG-M-kuaishou-live-gate-2026-07-22.json"
        ).read_text()
    )
    assert evidence["schema_version"] == 1
    assert evidence["stage"] == "PLATFORM-EXPANSION"
    assert evidence["platform"] == "kuaishou"
    assert evidence["result"] == "passed_with_explicit_boundaries"
    assert evidence["runtime"] == "project_playwright_persistent_context"
    assert evidence["visible_headful"] is True
    assert evidence["authorization"]["human_qr_scan_completed"] is True
    assert evidence["authorization"]["credentials_read"] is False
    assert evidence["authorization"]["cookies_or_storage_read"] is False
    assert evidence["media"]["video_injection_count"] == 1
    assert evidence["media"]["duplicate_video_injection_count"] == 0
    assert evidence["restart_recovery"]["upload_calls_after_restart"] == 0
    assert evidence["restart_recovery"]["duplicate_video_injection_count"] == 0
    assert evidence["final_action_guard"]["request_final_action_result"] is False
    assert evidence["final_action_guard"]["final_publish_click_count"] == 0
    assert evidence["final_action_guard"]["final_publish_button_clicked"] is False
    assert evidence["final_action_guard"]["release_state_promoted"] is False
    assert evidence["cover_receipt_boundary"]["receipt_present"] is False
    assert evidence["cover_receipt_boundary"]["accepted_preview_token"] == "blob:accepted-preview"


def test_shipinhao_live_gate_blocked_evidence_is_machine_asserted_and_not_promoted():
    evidence = json.loads(
        (
            ROOT
            / "docs/reviews/application-publishing-program/qa/PG-M-shipinhao-live-gate-2026-07-22.json"
        ).read_text()
    )
    assert evidence["schema_version"] == 1
    assert evidence["stage"] == "PLATFORM-EXPANSION"
    assert evidence["platform"] == "shipinhao"
    assert evidence["result"] == "blocked_with_explicit_boundary"
    assert evidence["runtime"] == "project_playwright_persistent_context"
    assert evidence["visible_headful"] is True
    assert evidence["authorization"]["human_qr_scan_completed"] is True
    assert evidence["authorization"]["login_probe"] is True
    assert evidence["authorization"]["credentials_read"] is False
    assert evidence["authorization"]["cookies_or_storage_read"] is False
    assert evidence["platform_shell"]["subapp_dom_state"] == "empty_after_unmount"
    assert evidence["platform_shell"]["browser_boundary"] == "WUJIE_CONTENT_SUBAPP_UNMOUNTED"
    assert evidence["bounded_adapter_attempt"]["video_injection_attempt_count"] == 1
    assert evidence["bounded_adapter_attempt"]["video_preview_readback"] is False
    assert evidence["bounded_adapter_attempt"]["adapter_status"] == "failed"
    assert evidence["bounded_adapter_attempt"]["adapter_message"] == "VIDEO_PLATFORM_READBACK_UNAVAILABLE"
    assert evidence["bounded_adapter_attempt"]["final_publish_click_count"] == 0
    assert evidence["restart_readback"]["upload_calls_after_restart"] == 0
    assert evidence["restart_readback"]["video_preview_readback"] is False
    assert evidence["restart_readback"]["final_publish_click_count"] == 0
    assert evidence["release_gate"]["release_state_promoted"] is False
    assert evidence["release_gate"]["release_state"] == "unverified"


def test_shipinhao_wujie_fix_evidence_records_bounded_fill_and_restart_boundary():
    evidence = json.loads(
        (
            ROOT
            / "docs/reviews/application-publishing-program/qa/PG-M-shipinhao-live-gate-fix-2026-07-22.json"
        ).read_text()
    )
    assert evidence["result"] == "blocked_with_explicit_boundary"
    assert evidence["authorization"]["human_qr_scan_completed"] is True
    assert evidence["authorization"]["credentials_read"] is False
    assert evidence["wujie_runtime_fix"]["content_root"] == "wujie-app_shadow_dom_host"
    main = evidence["bounded_main_attempt"]
    assert main["adapter_status"] == "draft_ready"
    assert main["video_injection_count"] == 1
    assert main["duplicate_video_injection_count"] == 0
    assert main["filled_fields"] == ["video", "title", "description", "cover"]
    assert main["readback_fields"] == ["video", "title", "description", "cover"]
    assert main["cover_receipt_present"] is True
    assert main["cover_receipt_url_scheme"] == "https"
    assert main["cover_receipt_policy"] == "ui_confirmed_https_receipt"
    assert main["final_publish_click_count"] == 0
    restart = evidence["restart_recovery"]
    assert restart["adapter_message"] == "STATE_AMBIGUOUS"
    assert restart["upload_calls_after_restart"] == 0
    assert restart["draft_persisted_by_platform"] is False
    assert restart["boundary"] == "SHIPINHAO_DRAFT_NOT_PERSISTED_AFTER_RUNTIME_RESTART"
    assert evidence["release_gate"]["overall_gate_passed"] is False
    assert evidence["release_gate"]["release_state"] == "unverified"


def test_xiaohongshu_live_entry_remains_auth_boundary_without_mutation():
    evidence = json.loads(
        (
            ROOT
            / "docs/reviews/application-publishing-program/qa/PG-M-xiaohongshu-live-entry-2026-07-22.json"
        ).read_text()
    )
    assert evidence["result"] == "blocked_auth_required"
    assert evidence["authorization"]["human_qr_scan_completed"] is False
    assert evidence["authorization"]["credentials_read"] is False
    assert evidence["authorization"]["cookies_or_storage_read"] is False
    assert evidence["mutation_policy"]["upload_count"] == 0
    assert evidence["mutation_policy"]["field_mutation_count"] == 0
    assert evidence["mutation_policy"]["final_publish_click_count"] == 0
    assert evidence["release_gate"]["release_state"] == "unverified"


def test_xiaohongshu_login_challenge_is_manual_boundary_without_mutation():
    evidence = json.loads(
        (
            ROOT
            / "docs/reviews/application-publishing-program/qa/PG-M-xiaohongshu-login-challenge-2026-07-22.json"
        ).read_text()
    )
    assert evidence["result"] == "blocked_challenge_required"
    assert evidence["authorization"]["human_qr_scan_completed"] is True
    assert evidence["authorization"]["human_login_detected"] is True
    assert evidence["challenge"]["state"] == "captcha"
    assert evidence["challenge"]["manual_resolution_required"] is True
    assert evidence["challenge"]["automation_bypass_attempted"] is False
    assert evidence["mutation_policy"]["upload_count"] == 0
    assert evidence["mutation_policy"]["final_publish_click_count"] == 0


def test_xiaohongshu_live_gate_records_fill_readback_and_restart_boundary():
    evidence = json.loads(
        (
            ROOT
            / "docs/reviews/application-publishing-program/qa/PG-M-xiaohongshu-live-gate-2026-07-22.json"
        ).read_text()
    )
    assert evidence["result"] == "blocked_with_explicit_boundary"
    assert evidence["authorization"]["human_qr_scan_completed"] is True
    assert evidence["authorization"]["credentials_read"] is False
    main = evidence["bounded_main_attempt"]
    assert main["adapter_status"] == "draft_ready"
    assert main["video_injection_count"] == 1
    assert main["duplicate_video_injection_count"] == 0
    assert main["filled_fields"] == ["video", "title", "description", "hashtags", "cover"]
    assert main["readback_fields"] == ["video", "title", "description", "hashtags", "cover"]
    assert main["cover_receipt_present"] is False
    assert main["cover_receipt_policy"] == "ui_confirmed_local_blob_preview_boundary_no_remote_url"
    restart = evidence["restart_recovery"]
    assert restart["adapter_message"] == "STATE_AMBIGUOUS"
    assert restart["upload_calls_after_restart"] == 0
    assert restart["draft_persisted_by_platform"] is False
    assert restart["boundary"] == "XIAOHONGSHU_DRAFT_NOT_PERSISTED_AFTER_RUNTIME_RESTART"
    assert evidence["final_action_guard"]["final_publish_click_count"] == 0
    assert evidence["release_gate"]["release_state"] == "unverified"
