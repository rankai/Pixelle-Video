import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_contract(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text())


def test_migration_safety_entry_contract_covers_fail_closed_guards():
    contract = read_contract("docs/contracts/app-center/migration-safety-contract.json")

    guards = contract["required_guards"]
    assert guards["single_process_lock"]["on_contention"] == "fail_read_only"
    assert guards["pre_transaction_backup"]["required"] is True
    assert guards["migration_checksum"]["stored_in"] == "app_schema_migrations.checksum"
    assert guards["future_schema_version"]["action"] == "fail_read_only"
    assert guards["sqlite_corruption"]["action"] == "fail_read_only"
    assert contract["transaction_order"].index("create_backup") < contract["transaction_order"].index("apply_schema_migration")
    assert "auto_delete_database" in contract["forbidden_behaviors"]


def test_registry_seed_entry_contract_requires_transaction_before_fact_writes():
    contract = read_contract("docs/contracts/app-center/registry-seed-contract.json")

    ordering = contract["ordering"]
    assert ordering.index("begin_transaction") < ordering.index("upsert_builtin_manifests")
    assert ordering.index("commit") < ordering.index("allow_app_run_or_handoff_fk_writes")
    assert contract["seed_key"] == ["app_id", "version"]
    assert contract["transaction_required"] is True
    assert "seed_after_app_run_insert" in contract["forbidden"]


def test_app_llm_port_entry_contract_rejects_second_model_source():
    contract = read_contract("docs/contracts/coordination/app-llm-port.contract.json")

    assert "ConfigManager/PixelleVideoCore.llm/LLMService" in contract["ownership"]
    assert {"api_key", "base_url", "model", "provider", "model_profile_ref"} <= set(contract["forbidden_request_fields"])
    assert {"api_key", "authorization", "cookie", "raw_provider_response"} <= set(contract["forbidden_persisted_fields"])
    assert set(contract["error_mapping"].values()) >= {"LLM_CONFIGURATION_MISSING", "LLM_TIMEOUT", "RUN_CANCELLED"}


def test_app_llm_port_has_one_coordination_source_of_truth():
    coordination = read_contract("docs/contracts/coordination/app-llm-port.contract.json")
    error_codes = read_contract("docs/contracts/app-center/app-error-codes.json")["codes"]

    assert not (ROOT / "docs/contracts/app-center/app-llm-port-contract.json").exists()
    assert set(coordination["error_mapping"].values()) <= set(error_codes)


def test_task_projection_entry_failure_matrix_is_explicit_and_redacted():
    contract = read_contract("docs/contracts/coordination/task-projection-failure-matrix.json")
    cases = {case["id"]: case for case in contract["cases"]}

    assert cases["secret_request_rejected"]["expected"] == "reject_and_do_not_persist_secret"
    assert cases["task_cleanup_preserves_fact"]["expected"] == "delete_projection_only"
    assert cases["retry_reuses_projection_id"]["expected"] == "same_task_id_new_attempt_preserve_old_evidence"
    assert cases["unknown_source_rejected"]["expected"] == "reject_without_projection"
    assert {"api_key", "cookie", "authorization", "result"} <= set(contract["forbidden_projection_fields"])
