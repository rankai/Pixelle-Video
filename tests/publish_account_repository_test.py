import pytest

from pixelle_video.services.publish.account_models import (
    AccountLoginState,
    AccountVerificationState,
    PublishPlatform,
)
from pixelle_video.services.publish.account_repository import (
    PublishAccountConflict,
    PublishAccountRepository,
)


def test_publish_account_migration_is_idempotent_and_defaults_are_per_platform(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    repository.migrate()
    first = repository.create_account(PublishPlatform.DOUYIN, "抖音 A", "profile_a", make_default=True)
    second = repository.create_account(PublishPlatform.DOUYIN, "抖音 B", "profile_b", make_default=True)
    assert repository.get_account(first.account_id).is_default is False
    assert repository.get_account(second.account_id).is_default is True
    assert len(repository.list_accounts()) == 2
    repository.migrate()
    assert len(repository.list_accounts()) == 2


def test_archive_and_clear_profile_preserve_account_record(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    account = repository.create_account(PublishPlatform.DOUYIN, "可回滚账号", "profile_keep", make_default=True)
    cleared = repository.mark_profile_cleared(account.account_id)
    assert cleared.account_id == account.account_id
    assert cleared.login_state == "not_connected"
    archived = repository.archive(account.account_id)
    assert archived.enabled is False
    assert archived.archived_at
    assert repository.list_accounts() == []
    assert repository.get_account(account.account_id).profile_ref == "profile_keep"


def test_default_cannot_be_assigned_to_archived_account(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    account = repository.create_account(PublishPlatform.DOUYIN, "归档账号", "profile_archived")
    repository.archive(account.account_id)
    try:
        repository.set_default(account.account_id)
    except PublishAccountConflict:
        pass
    else:
        raise AssertionError("archived account unexpectedly became default")


def test_login_state_machine_rejects_direct_authentication(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    account = repository.create_account(PublishPlatform.DOUYIN, "状态账号", "profile_state")
    with pytest.raises(PublishAccountConflict):
        repository.record_probe(
            account.account_id,
            login_state=AccountLoginState.AUTHENTICATED,
            verification_state=AccountVerificationState.VERIFIED,
            profile_exists=True,
            login_subject_hint="不应直达",
            identity_fingerprint="internal-only",
        )
    connecting = repository.record_probe(
        account.account_id,
        login_state=AccountLoginState.CONNECTING,
        verification_state=AccountVerificationState.UNVERIFIED,
        profile_exists=True,
    )
    assert connecting.login_state == AccountLoginState.CONNECTING


def test_open_contexts_are_marked_stale_on_recovery(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    account = repository.create_account(PublishPlatform.DOUYIN, "上下文账号", "profile_context")
    context = repository.register_context(account.account_id, window_ref="window-1")
    assert repository.list_contexts(account.account_id)[0]["status"] == "open"
    assert repository.mark_open_contexts_stale() == 1
    assert repository.list_contexts(account.account_id) == []
    repository.close_context(context["context_id"], stale=False)


def test_platform_release_gate_is_persisted_fail_closed_and_requires_evidence_ref(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    assert repository.get_platform_release_state(PublishPlatform.KUAISHOU) == "unverified"
    assert repository.get_platform_release_state(PublishPlatform.DOUYIN) == "pilot"
    with pytest.raises(PublishAccountConflict, match="RELEASE_EVIDENCE_REF_INVALID"):
        repository.promote_platform_release(PublishPlatform.KUAISHOU, evidence_ref="/tmp/live.json")
    with pytest.raises(PublishAccountConflict, match="RELEASE_EVIDENCE_REF_INVALID"):
        repository.promote_platform_release(PublishPlatform.KUAISHOU, evidence_ref="live-cookie-evidence")
    assert repository.promote_platform_release(
        PublishPlatform.KUAISHOU,
        evidence_ref="docs/reviews/application-publishing-program/PG-M-kuaishou.md",
    ) == "pilot"
    assert repository.get_platform_release_state(PublishPlatform.KUAISHOU) == "pilot"
    account = repository.create_account(PublishPlatform.KUAISHOU, "快手试点账号", "profile_kuaishou_gate")
    assert account.platform_release_state == "pilot"
    with pytest.raises(PublishAccountConflict, match="RELEASE_STATE_ALREADY_PROMOTED"):
        repository.promote_platform_release(PublishPlatform.KUAISHOU, evidence_ref="second-review.md")
    assert repository.revoke_platform_release(PublishPlatform.KUAISHOU, reason_ref="rollback:live-gate") == "unverified"
    assert repository.get_platform_release_state(PublishPlatform.KUAISHOU) == "unverified"
