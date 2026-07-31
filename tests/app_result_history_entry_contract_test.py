from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "docs/contracts/app-center"
FIXTURE_DIR = CONTRACT_DIR / "fixtures"


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validator(name: str = "generation-record-block-v1.schema.json") -> Draft202012Validator:
    schema = _load(CONTRACT_DIR / "generation-record-block-v1.schema.json")
    Draft202012Validator.check_schema(schema)
    selected = (
        schema if name == "generation-record-block-v1.schema.json" else _load(CONTRACT_DIR / name)
    )
    Draft202012Validator.check_schema(selected)
    registry = Registry().with_resource(schema["$id"], Resource.from_contents(schema))
    return Draft202012Validator(
        selected,
        registry=registry,
        format_checker=FormatChecker(),
    )


def _errors(
    payload: dict[str, Any],
    name: str = "generation-record-block-v1.schema.json",
) -> list[str]:
    return [error.message for error in _validator(name).iter_errors(payload)]


def _assert_record_semantics(record: dict[str, Any]) -> None:
    expected = {
        "multi_copy": ("copy", None),
        "multi_title": ("title", None),
        "single_carousel": ("carousel", 1),
        "single_video": ("video", 1),
    }
    assert record["record_id"] == record["app_run_id"]
    if not record["items"]:
        assert (
            record["status"] not in {"needs_review", "completed"}
            or record["compatibility"]["state"] == "legacy_unavailable"
        )
        return
    expected_kind, expected_count = expected[record["result_shape"]]
    assert {item["kind"] for item in record["items"]} == {expected_kind}
    if expected_count is not None:
        assert len(record["items"]) == expected_count


def test_schema_and_four_business_shapes_are_valid():
    fixtures = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")
    for record in fixtures["valid"].values():
        assert _errors(record) == []
        _assert_record_semantics(record)


def test_title_run_is_one_record_with_six_inline_candidates():
    record = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"]["viral_titles"]
    assert record["app_run_id"] == "run-title-001"
    assert len(record["items"]) == 6
    assert all(item["kind"] == "title" for item in record["items"])
    assert len({item["text"] for item in record["items"]}) == 6


def test_copy_run_is_one_record_with_every_candidate_inline():
    record = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"][
        "marketing_copy"
    ]
    assert len(record["items"]) == 3
    assert all(item["actions"] == ["copy", "edit"] for item in record["items"])


def test_carousel_is_one_product_even_when_it_has_multiple_pages():
    record = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"][
        "douyin_carousel"
    ]
    assert len(record["items"]) == 1
    assert record["items"][0]["page_count"] == 5
    assert record["items"][0]["actions"] == ["preview", "publish"]

    invalid = copy.deepcopy(record)
    invalid["items"].append(copy.deepcopy(invalid["items"][0]))
    assert _errors(invalid)


def test_digital_human_is_one_final_video_product():
    record = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"]["digital_human"]
    assert len(record["items"]) == 1
    item = record["items"][0]
    assert item["kind"] == "video"
    assert item["actions"] == ["play", "publish"]
    assert item["digital_human_name"] == "店长数字人"
    assert item["voice_name"] == "老板自然声"
    assert "script" not in item
    assert "cover_artifact" not in item
    assert item["details_available"] == [
        "cover",
        "publish_copy",
        "spoken_script",
        "download",
    ]


def test_schema_rejects_invalid_media_actions_and_absolute_paths():
    record = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"]["digital_human"]
    too_many = copy.deepcopy(record)
    too_many["items"][0]["actions"].append("publish")
    assert _errors(too_many)

    leaked_path = copy.deepcopy(record)
    leaked_path["items"][0]["playback_url"] = "C:\\Users\\demo\\video.mp4"
    assert _errors(leaked_path)

    traversal = copy.deepcopy(record)
    traversal["items"][0]["playback_url"] = "/api/../../sensitive"
    assert _errors(traversal)


def test_schema_rejects_unknown_technical_fields():
    record = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"]["viral_titles"]
    leaked = copy.deepcopy(record)
    leaked["items"][0]["provider"] = "example-provider"
    assert _errors(leaked)


def test_schema_locks_app_shape_and_item_kind_mapping():
    fixtures = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")
    record = copy.deepcopy(fixtures["valid"]["marketing_copy"])
    record["result_shape"] = "multi_title"
    assert _errors(record)

    wrong_kind = copy.deepcopy(record)
    wrong_kind["result_shape"] = "multi_copy"
    wrong_kind["items"][0]["kind"] = "title"
    assert _errors(wrong_kind)


def test_non_terminal_failed_and_legacy_records_have_explicit_empty_semantics():
    fixtures = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")
    for key in ("running", "failed", "legacy_unavailable"):
        record = fixtures["valid"][key]
        assert _errors(record) == []
        _assert_record_semantics(record)
        assert record["items"] == []
    assert fixtures["valid"]["legacy_unavailable"]["compatibility"] == {
        "state": "legacy_unavailable",
        "unavailable_reason": "这条旧记录暂时无法预览",
    }

    invalid_running = copy.deepcopy(fixtures["valid"]["running"])
    invalid_running["items"] = [copy.deepcopy(fixtures["valid"]["viral_titles"]["items"][0])]
    assert _errors(invalid_running)


def test_projection_never_silently_truncates_actual_text_candidates():
    record = copy.deepcopy(
        _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"]["viral_titles"]
    )
    template = record["items"][0]
    record["items"] = [
        {
            **template,
            "item_id": f"title-{index}",
            "text": f"候选标题 {index}",
        }
        for index in range(1, 26)
    ]
    assert _errors(record) == []
    assert len(record["items"]) == 25


_CURSOR_SECRET = b"entry-contract-only"


def _encode_cursor(
    *, project_id: str, scope: str, app_id: str | None, sort_at: str, app_run_id: str
) -> str:
    payload = json.dumps(
        {
            "project_id": project_id,
            "scope": scope,
            "app_id": app_id,
            "sort_at": sort_at,
            "app_run_id": app_run_id,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(_CURSOR_SECRET, encoded.encode(), hashlib.sha256).hexdigest()[:24]
    return f"{encoded}_{signature}"


def _decode_cursor(
    cursor: str, *, project_id: str, scope: str, app_id: str | None
) -> dict[str, Any]:
    try:
        encoded, signature = cursor.rsplit("_", 1)
        expected = hmac.new(_CURSOR_SECRET, encoded.encode(), hashlib.sha256).hexdigest()[:24]
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature")
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding))
    except Exception as exc:
        raise ValueError("APP_RESULT_CURSOR_INVALID") from exc
    if (
        payload.get("project_id") != project_id
        or payload.get("scope") != scope
        or payload.get("app_id") != app_id
    ):
        raise ValueError("APP_RESULT_CURSOR_INVALID")
    return payload


def _project_page(
    records: list[dict[str, Any]],
    *,
    project_id: str,
    scope: str,
    app_id: str | None,
    cursor: str | None = None,
    limit: int = 2,
) -> dict[str, Any]:
    if scope == "current_app" and not app_id:
        raise ValueError("APP_RESULT_APP_REQUIRED")
    if scope == "all_results" and app_id is not None:
        raise ValueError("APP_RESULT_APP_NOT_ALLOWED")
    filtered = [
        record
        for record in records
        if record["project_id"] == project_id
        and (scope == "all_results" or record["app_id"] == app_id)
    ]
    if any(record["record_id"] != record["app_run_id"] for record in filtered):
        raise ValueError("APP_RESULT_RECORD_ID_INVALID")
    if len({record["app_run_id"] for record in filtered}) != len(filtered):
        raise ValueError("APP_RESULT_DUPLICATE_RUN")
    ordered = sorted(
        filtered,
        key=lambda record: (
            record["result_available_at"] or record["created_at"],
            record["app_run_id"],
        ),
        reverse=True,
    )
    if cursor:
        marker = _decode_cursor(
            cursor,
            project_id=project_id,
            scope=scope,
            app_id=app_id,
        )
        marker_key = (marker["sort_at"], marker["app_run_id"])
        ordered = [
            record
            for record in ordered
            if (
                record["result_available_at"] or record["created_at"],
                record["app_run_id"],
            )
            < marker_key
        ]
    page_records = ordered[:limit]
    next_cursor = None
    if len(ordered) > limit:
        last = page_records[-1]
        next_cursor = _encode_cursor(
            project_id=project_id,
            scope=scope,
            app_id=app_id,
            sort_at=last["result_available_at"] or last["created_at"],
            app_run_id=last["app_run_id"],
        )
    return {
        "schema_version": 1,
        "project_id": project_id,
        "scope": scope,
        "app_id": app_id,
        "records": page_records,
        "next_cursor": next_cursor,
    }


def test_query_contract_defaults_to_current_app_and_keeps_project_isolation():
    fixtures = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")
    cases = {case["id"]: case for case in fixtures["query_cases"]}
    assert cases["current-app-default"]["scope"] == "current_app"
    assert cases["current-app-default"]["expected_record_ids"] == ["run-title-001"]
    assert cases["all-project-results"]["scope"] == "all_results"
    assert cases["all-project-results"]["project_id"] == "project-cafe-001"
    assert len(cases["all-project-results"]["expected_record_ids"]) == 4


def test_page_contract_enforces_scope_cursor_stability_and_no_duplicates():
    fixtures = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")
    records = [
        fixtures["valid"][key]
        for key in (
            "marketing_copy",
            "viral_titles",
            "douyin_carousel",
            "digital_human",
        )
    ]
    first = _project_page(
        records,
        project_id="project-cafe-001",
        scope="all_results",
        app_id=None,
        limit=2,
    )
    assert _errors(first, "generation-record-page-v1.schema.json") == []
    assert len(first["records"]) == 2
    assert first["next_cursor"]
    second = _project_page(
        records,
        project_id="project-cafe-001",
        scope="all_results",
        app_id=None,
        cursor=first["next_cursor"],
        limit=2,
    )
    assert _errors(second, "generation-record-page-v1.schema.json") == []
    ids = [record["app_run_id"] for record in first["records"] + second["records"]]
    assert len(ids) == 4
    assert len(set(ids)) == 4

    with pytest.raises(ValueError, match="APP_RESULT_CURSOR_INVALID"):
        _project_page(
            records,
            project_id="project-other-001",
            scope="all_results",
            app_id=None,
            cursor=first["next_cursor"],
            limit=2,
        )

    tampered = f"{first['next_cursor'][:-1]}{'0' if first['next_cursor'][-1] != '0' else '1'}"
    with pytest.raises(ValueError, match="APP_RESULT_CURSOR_INVALID"):
        _project_page(
            records,
            project_id="project-cafe-001",
            scope="all_results",
            app_id=None,
            cursor=tampered,
            limit=2,
        )

    with pytest.raises(ValueError, match="APP_RESULT_APP_REQUIRED"):
        _project_page(
            records,
            project_id="project-cafe-001",
            scope="current_app",
            app_id=None,
        )


def test_page_contract_rejects_duplicate_app_run_blocks():
    fixtures = _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")
    record = fixtures["valid"]["viral_titles"]
    duplicate = copy.deepcopy(record)
    with pytest.raises(ValueError, match="APP_RESULT_DUPLICATE_RUN"):
        _project_page(
            [record, duplicate],
            project_id="project-cafe-001",
            scope="current_app",
            app_id="builtin.viral-titles",
            limit=1,
        )


def test_record_id_must_equal_app_run_id_before_pagination():
    record = copy.deepcopy(
        _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"]["viral_titles"]
    )
    record["record_id"] = "different-record-id"
    with pytest.raises(ValueError, match="APP_RESULT_RECORD_ID_INVALID"):
        _project_page(
            [record],
            project_id="project-cafe-001",
            scope="current_app",
            app_id="builtin.viral-titles",
            limit=1,
        )


def test_equal_timestamps_use_app_run_id_desc_as_stable_tie_break():
    base = copy.deepcopy(
        _load(FIXTURE_DIR / "app-result-history-entry-fixtures.json")["valid"]["viral_titles"]
    )
    left = copy.deepcopy(base)
    left["record_id"] = left["app_run_id"] = "run-title-a"
    right = copy.deepcopy(base)
    right["record_id"] = right["app_run_id"] = "run-title-z"
    first = _project_page(
        [left, right],
        project_id="project-cafe-001",
        scope="current_app",
        app_id="builtin.viral-titles",
        limit=1,
    )
    assert [record["app_run_id"] for record in first["records"]] == ["run-title-z"]
    second = _project_page(
        [left, right],
        project_id="project-cafe-001",
        scope="current_app",
        app_id="builtin.viral-titles",
        cursor=first["next_cursor"],
        limit=1,
    )
    assert [record["app_run_id"] for record in second["records"]] == ["run-title-a"]
    assert second["next_cursor"] is None


def test_entry_contract_freezes_read_only_projection_and_rollback():
    contract = _load(CONTRACT_DIR / "app-result-history-entry.contract.json")
    assert contract["record_boundary"]["one_app_run_one_record_block"] is True
    assert contract["record_boundary"]["record_id_equals_app_run_id"] is True
    assert contract["record_boundary"]["default_scope"] == "current_app"
    assert contract["record_boundary"]["project_isolation_required"] is True
    assert contract["read_projection"]["second_result_fact_table"] is False
    assert contract["read_projection"]["list_and_preview_are_read_only"] is True
    assert contract["read_projection"]["read_backfill"] is False
    assert contract["read_projection"]["legacy_unknown_source_list_behavior"].startswith("HTTP 200")
    assert contract["rollback"]["old_data_rewritten"] is False
    assert contract["rollback"]["media_deleted"] is False


def test_media_display_budget_and_hidden_technical_fields_are_frozen():
    contract = _load(CONTRACT_DIR / "app-result-history-entry.contract.json")
    display = contract["ordinary_user_display"]
    assert display["media_card_primary_action_limit"] == 2
    assert display["carousel_card"] == [
        "real cover",
        "title",
        "page count",
        "preview",
        "publish",
    ]
    assert display["digital_human_card"] == [
        "real poster or first frame",
        "title",
        "duration",
        "digital human name",
        "voice name",
        "play",
        "download",
        "publish",
    ]
    hidden = set(display["hidden_from_primary_list"])
    assert {"provider", "model", "workflow step", "absolute file path"} <= hidden
    assert "script and cover as separate result rows" in hidden


def test_entry_flag_is_registered_default_off_without_runtime_wiring():
    contract = _load(CONTRACT_DIR / "app-result-history-entry.contract.json")
    flag = contract["feature_flag"]
    assert flag == {
        "name": "appResultHistoryV1",
        "backend_env": "PIXELLE_APP_RESULT_HISTORY_V1",
        "frontend_env": "VITE_APP_RESULT_HISTORY_V1",
        "default": False,
        "unknown_or_conflicting": False,
        "entry_runtime_wiring": False,
    }

    matrix = _load(CONTRACT_DIR / "feature-flag-matrix.json")
    registered = next(item for item in matrix["flags"] if item["name"] == "appResultHistoryV1")
    assert registered["default"] is False
    assert registered["owner_stage"] == "APP-RESULT-HISTORY-3"


def test_entry_has_zero_business_and_external_actions():
    entry = _load(CONTRACT_DIR / "app-result-history-entry.contract.json")["entry_boundaries"]
    zero_fields = {
        key
        for key in entry
        if key
        not in {
            "paused_checkpoint",
        }
    }
    assert zero_fields
    assert all(entry[key] == 0 for key in zero_fields)
    assert entry["paused_checkpoint"].startswith("PROGRAM-ROLLOUT/PG-L")


def test_fixture_contains_no_secrets_or_absolute_user_paths():
    raw = (FIXTURE_DIR / "app-result-history-entry-fixtures.json").read_text(encoding="utf-8")
    forbidden = [
        "sk-",
        "ark-",
        "/Users/",
        "C:\\\\Program Files",
        "Authorization",
        "api_key",
    ]
    assert all(token not in raw for token in forbidden)


def test_ledger_records_result_history_closure_and_restores_program_rollout():
    ledger = (
        ROOT / "docs/reviews/2026-07-18-application-center-publishing-program-progress.md"
    ).read_text(encoding="utf-8")
    assert "current_stage: PROGRAM-ROLLOUT" in ledger
    assert "current_substage: PG-L-WINDOWS-AND-PRODUCT-ACCEPTANCE" in ledger
    assert "completed_subplan_gate: PG-ARH-E_passed" in ledger
    assert "CR-APP-RESULT-HISTORY-001" in ledger
    assert "PG-ARH-A" in ledger
    assert "PG-ARH-E=passed" in ledger
    assert "APP-RESULT-HISTORY-4-final-review-2026-07-30.md" in ledger
