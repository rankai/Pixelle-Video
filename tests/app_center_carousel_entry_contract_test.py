"""AC-4 Entry contract checks; no renderer, executor, or platform action is imported."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def _read(relative: str):
    return json.loads((ROOT / relative).read_text())


def _pages(case: dict) -> list[dict]:
    if isinstance(case["pages"], list) and case["pages"] and isinstance(case["pages"][0], dict):
        return case["pages"]
    if case["pages"] == "generated_contiguous_pages":
        dimensions = case.get("dimensions", {"width_px": 1080, "height_px": 1440})
        state = case.get("render_state", "ready")
        return [
            {
                "page_index": index,
                "text": f"第{index}页",
                "asset_refs": [] if case.get("missing_asset_on_page") == index else [f"asset:page-{index}"],
                "render_state": state,
                "dimensions": dimensions,
            }
            for index in range(1, case["page_count"] + 1)
        ]
    if isinstance(case["pages"], list):
        return [
            {"page_index": index, "text": f"第{index}页", "asset_refs": [f"asset:page-{index}"], "render_state": "ready", "dimensions": {"width_px": 1080, "height_px": 1440}}
            for index in case["pages"]
        ]
    raise AssertionError(f"unsupported fixture pages: {case['pages']}")


def _validate_case(case: dict, contract: dict) -> None:
    page_spec = contract["page_spec"]
    pages = _pages(case)
    if case["page_count"] not in page_spec["allowed_counts"]:
        raise ValueError("PAGE_COUNT_NOT_ALLOWED")
    indexes = [page["page_index"] for page in pages]
    if indexes != list(range(1, case["page_count"] + 1)):
        raise ValueError("PAGE_INDEX_NOT_CONTIGUOUS")
    for page in pages:
        dimensions = page["dimensions"]
        if dimensions != {"width_px": page_spec["width_px"], "height_px": page_spec["height_px"]}:
            raise ValueError("DIMENSIONS_NOT_3_4")
        if not page["asset_refs"]:
            raise ValueError("ASSET_REF_REQUIRED")
        if page["render_state"] == "text_overflow":
            raise ValueError("TEXT_OVERFLOW")
        if page["render_state"] == "missing_font":
            raise ValueError("FONT_MISSING")


def _validate_artifact_case(case: dict, contract: dict) -> None:
    artifact_spec = contract["artifact_contract"][case["artifact_type"].removeprefix("carousel_")]
    content = case["content"]
    missing = [field for field in artifact_spec["required_fields"] if field not in content]
    if missing:
        raise ValueError("ARTIFACT_REQUIRED_FIELD")
    if case["artifact_type"] == "carousel_plan" and not content["source_artifact_version_ids"]:
        raise ValueError("SOURCE_VERSION_REQUIRED")
    if case["artifact_type"] == "carousel_package" and len(content["page_artifact_version_ids"]) != content["page_count"]:
        raise ValueError("PAGE_VERSION_COUNT_MISMATCH")
    if case["artifact_type"] == "carousel_page" and not content.get("source_plan_artifact_version_id"):
        raise ValueError("SOURCE_PLAN_VERSION_REQUIRED")


def test_ac4_entry_contract_schema_and_scope_are_frozen():
    contract = _read("docs/contracts/app-center/carousel-entry.contract.json")
    Draft202012Validator.check_schema(contract)
    assert contract["app_id"] == "builtin.douyin-carousel"
    assert contract["feature_flag"] == "douyinCarousel"
    assert contract["feature_flag_default"] is False
    assert contract["page_spec"]["allowed_counts"] == [3, 5, 8]
    assert contract["page_spec"]["aspect_ratio"] == "3:4"
    assert contract["render_contract"]["zip_must_contain_exactly_page_count_files"] is True
    assert contract["retry_contract"]["single_page_retry_only"] is True
    assert contract["handoff_contract"]["target_artifact_type"] == "publish_package_ref"
    assert "final_publish" in contract["forbidden_in_entry"]


def test_ac4_entry_fixture_matrix_covers_valid_counts_and_failure_boundaries():
    contract = _read("docs/contracts/app-center/carousel-entry.contract.json")
    fixture = _read("docs/contracts/app-center/fixtures/carousel-entry-fixtures.json")
    assert {case["page_count"] for case in fixture["cases"] if case["valid"]} == {3, 5, 8}
    for case in fixture["cases"]:
        if case["valid"]:
            _validate_case(case, contract)
        else:
            try:
                _validate_case(case, contract)
            except ValueError as raised:
                assert str(raised) == case["expected_error"]
            else:
                raise AssertionError(f"invalid fixture accepted: {case['case_id']}")


def test_ac4_artifact_fixtures_lock_plan_page_package_required_fields_and_sources():
    contract = _read("docs/contracts/app-center/carousel-entry.contract.json")
    fixture = _read("docs/contracts/app-center/fixtures/carousel-entry-fixtures.json")
    valid_types = {case["artifact_type"] for case in fixture["artifact_cases"] if case["valid"]}
    assert valid_types == {"carousel_plan", "carousel_page", "carousel_package"}
    for case in fixture["artifact_cases"]:
        if case["valid"]:
            _validate_artifact_case(case, contract)
        else:
            try:
                _validate_artifact_case(case, contract)
            except ValueError as raised:
                assert str(raised) == case["expected_error"]
            else:
                raise AssertionError(f"invalid artifact fixture accepted: {case['case_id']}")


def test_ac4_single_page_retry_is_isolated_and_creates_new_version():
    fixture = _read("docs/contracts/app-center/fixtures/carousel-entry-fixtures.json")
    allowed = {"missing_image", "missing_font", "text_overflow"}
    for case in fixture["retry_cases"]:
        assert case["failure"] in allowed
        assert case["asset_ref_present"] is True
        successful_pages = {1: "v1-page-1", 2: "v1-page-2", 3: "v1-page-3"}
        failed_page = case["failed_page"]
        before = dict(successful_pages)
        after = dict(successful_pages)
        after[failed_page] = f"v2-page-{failed_page}"
        assert {index: version for index, version in before.items() if index != failed_page} == {index: version for index, version in after.items() if index != failed_page}
        assert before[failed_page] != after[failed_page]
        assert case["expected_error"] in {"ASSET_NOT_FOUND", "FONT_MISSING", "TEXT_OVERFLOW"}


def test_ac4_zip_and_publish_handoff_fixture_is_ordered_and_source_pinned():
    fixture = _read("docs/contracts/app-center/fixtures/carousel-entry-fixtures.json")["zip_handoff"]
    assert fixture["files"] == fixture["zip_order"]
    assert len(fixture["files"]) == fixture["page_count"]
    assert all(name == f"page-{index:02d}.png" for index, name in enumerate(fixture["files"], start=1))
    assert fixture["file_format"] == "png"
    assert fixture["dimensions"] == {"width_px": 1080, "height_px": 1440}
    handoff = fixture["publish_package_ref"]
    assert len(handoff["source_artifact_version_ids"]) == fixture["page_count"]
    assert handoff["publish_copy_required"] is True
    assert handoff["publish_v2_compatible"] is True
    assert fixture["source_change"]["old_ref_invalidated"] is True
    assert fixture["source_change"]["old_source_artifact_version_ids"] != fixture["source_change"]["new_source_artifact_version_ids"]


def test_ac4_flag_contract_and_entry_has_no_executor_ui_or_platform_action():
    contract = _read("docs/contracts/app-center/carousel-entry.contract.json")
    flags = _read("docs/contracts/app-center/feature-flag-matrix.json")
    carousel_flag = next(flag for flag in flags["flags"] if flag["name"] == "douyinCarousel")
    assert carousel_flag["default"] is False
    assert flags["unknown_flag_behavior"] == "false"
    assert flags["frontend_cannot_write"] is True
    assert contract["feature_flag_contract"]["legacy_templates_and_video_rendering_unchanged_when_disabled"] is True
    assert contract["entry_implementation_boundary"] == {
        "executor_implemented": False,
        "renderer_implemented": False,
        "frontend_ui_implemented": False,
        "platform_action_enabled": False,
        "allowed_changes": ["contract", "fixture", "entry_test", "review_evidence"],
    }
    assert not (ROOT / "pixelle_video/app_center/executors/douyin_carousel_v1.py").exists()
    assert not (ROOT / "desktop/src/features/app-center/carousel").exists()


def test_ac4_entry_review_keeps_business_implementation_out_of_scope():
    review = (ROOT / "docs/reviews/application-publishing-program/AC-4-entry-review-2026-07-20.md").read_text()
    for marker in ("entry_in_progress", "不实现真实图文 Executor", "不上传到抖音", "不点击最终发布", "AC-4 implementation"):
        assert marker in review
