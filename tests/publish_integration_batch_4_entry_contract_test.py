import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/publishing/pub-4-batch-4-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/publishing/fixtures/pub-4-batch-4-entry-fixtures.json")


def test_pub4_batch4_entry_freezes_remaining_local_runtime_scope():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "pub-4-batch-4-entry"
    assert contract["runtime"] == {
        "refresh_package_handoff_preserved": True,
        "leave_return_package_handoff_preserved": True,
        "restart_package_handoff_preserved": True,
        "adapter_failure_copy_download_fallback": True,
        "resolver_unique_runtime_200": True,
        "resolver_ambiguous_runtime_409": True,
        "resolver_stale_runtime_409": True,
        "cross_process_cas_not_claimed": True,
    }
    assert contract["external_actions"] == {
        "browser": 0,
        "authorization": 0,
        "upload": 0,
        "publish_run_create": 0,
        "final_publish": 0,
    }
    assert contract["exit_gate"] == {
        "requires_independent_six_dimension_review": True,
        "p0_p1_must_be_zero": True,
        "does_not_close_pg_j_alone": True,
    }


def test_pub4_batch4_entry_fixtures_cover_recovery_fallback_and_resolver_runtime():
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    by_id = {fixture["id"]: fixture for fixture in fixtures}
    assert set(by_id) == {
        "refresh-preserves-package-handoff",
        "leave-return-preserves-package-handoff",
        "restart-preserves-package-handoff",
        "adapter-failure-safe-copy-download",
        "resolver-unique-runtime",
        "resolver-ambiguous-runtime",
        "resolver-stale-runtime",
        "external-action-forbidden",
    }
    assert all(by_id[item]["valid"] for item in (
        "refresh-preserves-package-handoff",
        "leave-return-preserves-package-handoff",
        "restart-preserves-package-handoff",
        "adapter-failure-safe-copy-download",
        "resolver-unique-runtime",
    ))
    assert all(not by_id[item]["valid"] for item in (
        "resolver-ambiguous-runtime",
        "resolver-stale-runtime",
        "external-action-forbidden",
    ))
    assert by_id["resolver-unique-runtime"]["status_code"] == 200
    assert by_id["resolver-ambiguous-runtime"]["status_code"] == 409
    assert by_id["resolver-stale-runtime"]["status_code"] == 409
