import json
import sqlite3
from pathlib import Path

import pytest

from api.tasks.manager import TaskManager
from pixelle_video.services.publish.account_models import PublishPlatform
from pixelle_video.services.publish.account_repository import (
    PublishAccountConflict,
    PublishAccountRepository,
)
from pixelle_video.services.publish.core_repository import PublishCoreRepository, PublishRunConflict
from pixelle_video.services.publish.run_service import PublishRunService
from tests.publish_run_service_test import _package

ROOT = Path(__file__).resolve().parents[1]
PLATFORM_IDS = {
    "kuaishou": PublishPlatform.KUAISHOU,
    "shipinhao": PublishPlatform.VIDEO_CHANNEL,
    "xiaohongshu": PublishPlatform.XIAOHONGSHU,
}


def _contract() -> dict:
    return json.loads(
        (ROOT / "docs/contracts/publishing/platform-expansion-release-boundary.contract.json").read_text()
    )


def test_release_boundary_contract_freezes_platforms_and_no_publish_invariants():
    contract = _contract()
    assert contract["stage"] == "PLATFORM-EXPANSION"
    assert set(contract["platforms"]) == set(PLATFORM_IDS)
    assert all(item["release_state"] == "unverified" for item in contract["platforms"].values())
    assert contract["invariants"] == {
        "douyin_release_state_unchanged": "pilot",
        "unverified_create_run_error": "PLATFORM_RELEASE_NOT_READY",
        "unverified_browser_start_allowed": False,
        "copy_download_fallback_available": True,
        "allow_final_publish": False,
        "final_publish_click_count": 0,
        "external_actions": 0,
        "production_database_mutation": False,
    }
    assert contract["rollback_rehearsal"]["scope"] == "temporary_sqlite_only"


def test_unverified_platforms_are_blocked_before_run_creation_and_browser_start(tmp_path):
    db = tmp_path / "release-boundary.sqlite"
    accounts = PublishAccountRepository(db)
    core = PublishCoreRepository(db)
    package = core.create_package(_package())
    service = PublishRunService(core, accounts, manager=TaskManager())

    for platform_name, platform in PLATFORM_IDS.items():
        account = accounts.create_account(platform, platform_name, f"profile_{platform_name}")
        with pytest.raises(PublishRunConflict, match="PLATFORM_RELEASE_NOT_READY"):
            service.create_run(package.package_id, account.account_id, platform, f"boundary-{platform_name}")
        with sqlite3.connect(db) as connection:
            assert connection.execute("SELECT COUNT(*) FROM publish_runs_v2").fetchone()[0] == 0

    assert accounts.get_platform_release_state(PublishPlatform.DOUYIN) == "pilot"


def test_release_promotion_and_revoke_rehearsal_restores_unverified_without_account_mutation(tmp_path):
    db = tmp_path / "rollback-rehearsal.sqlite"
    accounts = PublishAccountRepository(db)
    before = {}
    for platform_name, platform in PLATFORM_IDS.items():
        account = accounts.create_account(platform, platform_name, f"profile_{platform_name}")
        before[platform_name] = (account.account_id, account.profile_ref, account.login_state, account.enabled)

    for platform_name, platform in PLATFORM_IDS.items():
        account_id, profile_ref, login_state, enabled = before[platform_name]
        assert accounts.promote_platform_release(
            platform, evidence_ref=f"qa/platform-expansion-{platform_name}-review"
        ) == "pilot"
        assert accounts.get_platform_release_state(platform) == "pilot"
        assert accounts.revoke_platform_release(platform, reason_ref=f"rollback/platform-expansion-{platform_name}") == "unverified"
        restored = accounts.get_account(account_id)
        assert restored.profile_ref == profile_ref
        assert restored.login_state == login_state
        assert restored.enabled is enabled
        assert accounts.get_platform_release_state(platform) == "unverified"

    assert accounts.get_platform_release_state(PublishPlatform.DOUYIN) == "pilot"


@pytest.mark.parametrize("platform", list(PLATFORM_IDS.values()))
def test_release_promotion_rejects_path_or_secret_like_evidence_without_state_change(tmp_path, platform):
    accounts = PublishAccountRepository(tmp_path / f"invalid-{platform.value}.sqlite")
    with pytest.raises(PublishAccountConflict, match="RELEASE_EVIDENCE_REF_INVALID"):
        accounts.promote_platform_release(platform, evidence_ref="/tmp/live.json")
    with pytest.raises(PublishAccountConflict, match="RELEASE_EVIDENCE_REF_INVALID"):
        accounts.promote_platform_release(platform, evidence_ref="cookie-evidence")
    assert accounts.get_platform_release_state(platform) == "unverified"


def test_existing_platform_evidence_is_explicitly_bounded_and_never_promoted():
    for filename, expected_platform, expected_result in (
        ("PG-M-kuaishou-live-gate-2026-07-22.json", "kuaishou", "passed_with_explicit_boundaries"),
        ("PG-M-shipinhao-live-gate-fix-2026-07-22.json", "shipinhao", "blocked_with_explicit_boundary"),
        ("PG-M-xiaohongshu-live-gate-2026-07-22.json", "xiaohongshu", "blocked_with_explicit_boundary"),
    ):
        evidence = json.loads(
            (ROOT / "docs/reviews/application-publishing-program/qa" / filename).read_text()
        )
        assert evidence["platform"] == expected_platform
        assert evidence["result"] == expected_result
        release_gate = evidence.get("release_gate") or {
            "release_state": "unverified",
            "release_state_promoted": evidence.get("final_action_guard", {}).get("release_state_promoted"),
        }
        assert release_gate["release_state"] == "unverified"
        assert release_gate["release_state_promoted"] is False
        assert evidence.get("final_action_guard", {}).get("final_publish_click_count", 0) == 0


def test_release_boundary_qa_evidence_is_consistent_with_current_gate():
    evidence = json.loads(
        (
            ROOT
            / "docs/reviews/application-publishing-program/qa/PLATFORM-EXPANSION-release-boundary-2026-07-23.json"
        ).read_text()
    )
    assert evidence["result"] == "passed_with_explicit_boundaries"
    assert evidence["scope"] == "temporary_sqlite_only"
    assert evidence["platform_release_states"] == {
        "douyin": "pilot",
        "kuaishou": "unverified",
        "shipinhao": "unverified",
        "xiaohongshu": "unverified",
    }
    assert all(value == "PLATFORM_RELEASE_NOT_READY" for value in evidence["unverified_platform_run_gate"].values())
    assert evidence["rollback_rehearsal"]["promoted_then_revoked"] is True
    assert evidence["rollback_rehearsal"]["final_state_all_unverified"] is True
    assert evidence["safety"]["final_publish_click_count"] == 0
