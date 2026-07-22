import json
from pathlib import Path

CONTRACT_PATH = Path("docs/contracts/publishing/pub-4-batch-3-entry.contract.json")
FIXTURE_PATH = Path("docs/contracts/publishing/fixtures/pub-4-batch-3-entry-fixtures.json")


def test_pub4_batch3_entry_freezes_legacy_step_and_resolver_boundaries():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["contract_id"] == "pub-4-batch-3-entry"
    assert contract["legacy_step"]["publish_workspace_prepare_calls"] == 0
    assert contract["legacy_step"]["secondary_package_or_run_creation"] == 0
    assert contract["legacy_step"]["legacy_page_remains_reachable"] is True
    assert contract["resolver"] == {
        "operation_id": "resolvePublishPackageV2",
        "input": "artifact_id",
        "missing_artifact_fail_closed": True,
        "invalidated_package_fail_closed": True,
        "ambiguous_candidates_fail_closed": True,
        "openapi_registered": True,
    }
    openapi = json.loads(Path("docs/contracts/publishing/publish-v2.openapi.json").read_text(encoding="utf-8"))
    resolve = openapi["paths"]["/packages/resolve"]["get"]
    assert resolve["operationId"] == "resolvePublishPackageV2"
    assert resolve["parameters"] == [{"name": "artifact_id", "in": "query", "required": True, "schema": {"type": "string", "minLength": 1}}]
    assert set(resolve["responses"]) == {"200", "404", "409"}


def test_pub4_batch3_entry_freezes_fallback_and_external_action_zero():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["fallback"]["trusted_artifact_refs_only"] is True
    assert contract["fallback"]["absolute_paths_exposed"] == 0
    assert contract["fallback"]["secrets_exposed"] == 0
    assert contract["external_actions"] == {
        "browser": 0,
        "authorization": 0,
        "upload": 0,
        "publish_run_create": 0,
        "final_publish": 0,
    }
    fixtures = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["fixtures"]
    assert len(fixtures) == 9
    assert all(not fixture["valid"] for fixture in fixtures)
    assert {fixture["id"] for fixture in fixtures} == {
        "legacy-step-prepare-forbidden",
        "legacy-secondary-run-forbidden",
        "resolver-missing-artifact",
        "resolver-stale-package",
        "resolver-ambiguous-candidates",
        "fallback-absolute-path-forbidden",
        "fallback-secret-forbidden",
        "flag-off-v2-request-forbidden",
        "keyboard-narrow-dead-end-forbidden",
    }
