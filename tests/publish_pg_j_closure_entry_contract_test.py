import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/publishing/pub-4-pg-j-closure-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/publishing/fixtures/pub-4-pg-j-closure-entry-fixtures.json")


def test_pg_j_closure_entry_freezes_local_evidence_and_external_boundary():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "pub-4-pg-j-closure-entry"
    assert all(contract["required_evidence"].values())
    assert all(contract["forbidden"].values())
    assert contract["exit_gate"] == {
        "requires_independent_six_dimension_review": True,
        "p0_p1_must_be_zero": True,
        "only_then_may_close_pg_j": True,
    }


def test_pg_j_closure_entry_fixture_matrix_is_explicit():
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    by_id = {fixture["id"]: fixture for fixture in fixtures}
    assert set(by_id) == {
        "tauri-sidecar-restart-preserves-handoff",
        "leave-return-same-package",
        "legacy-copy-download-fallback",
        "resolver-runtime-three-state",
        "published-state-never-claimed",
        "external-actions-zero",
        "cross-process-cas-not-claimed",
    }
    assert all(by_id[item]["valid"] for item in set(by_id) - {"cross-process-cas-not-claimed"})
    assert by_id["cross-process-cas-not-claimed"]["error"] == "DEFERRED_CAPABILITY"
