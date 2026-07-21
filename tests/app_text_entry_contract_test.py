import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def test_ac3_entry_contract_keeps_two_apps_on_shared_llm_boundary():
    contract = load("docs/contracts/app-center/app-text-entry-contract.json")
    assert contract["status"] == "entry_contract"
    assert contract["shared_rules"]["model_source"] == "existing AppLLMPort/local-default"
    assert contract["marketing_copy"]["variant_count"] == {"min": 3, "max": 3}
    assert contract["viral_titles"]["candidate_count"] == {"min": 5, "max": 10}
    assert contract["viral_titles"]["deterministic_rules"]["max_characters"] == 30
    assert "Unicode NFKC" in contract["shared_rules"]["text_normalization_v1"]
    assert "全网第一" in contract["shared_rules"]["banned_terms_v1"]
    assert contract["shared_rules"]["repair_policy"] == {
        "max_attempts": 1,
        "trigger": ["invalid_json", "missing_required_fields", "schema_mismatch"],
        "on_failure": "emit_original_error_code",
        "preserve_input": True,
    }
    assert contract["viral_titles"]["deterministic_rules"]["dedup_ratio_denominator"] == "requested_count; unique_normalized_count/requested_count"
    assert "reject zero or multiple sources" in contract["viral_titles"]["source_exclusivity"]
    assert set(contract["marketing_copy"]["deterministic_rules"]["angle_enum"]) == {"利益", "好奇", "冲突", "数字", "场景", "身份"}
    assert contract["marketing_copy"]["deterministic_rules"]["recalculate_estimated_seconds_after_edit"] is True


def test_ac3_entry_fixture_covers_six_store_categories_and_negative_facts():
    fixture = load("docs/contracts/app-center/fixtures/app-text-entry.json")
    assert {item["store_type"] for item in fixture["categories"]} == {"火锅", "美容", "民宿", "洗衣店", "培训", "零售"}
    assert {item["id"] for item in fixture["invalid_cases"]} >= {"invented_price", "invented_address", "duplicate_titles", "banned_term"}


def test_ac3_entry_error_matrix_preserves_input_for_all_llm_failures():
    contract = load("docs/contracts/app-center/app-text-entry-contract.json")
    cases = {item["case"]: item for item in contract["error_matrix"]}
    assert {"missing_llm_configuration", "auth_failure", "rate_limited", "timeout", "invalid_json_or_missing_fields", "empty_provider_output", "provider_failure", "run_cancelled"} <= set(cases)
    assert all(item["preserve_input"] for item in cases.values())
