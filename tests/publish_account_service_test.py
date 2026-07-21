import asyncio
import sqlite3

import pytest

from pixelle_video.services.publish.account_models import PublishPlatform
from pixelle_video.services.publish.account_repository import (
    PublishAccountConflict,
    PublishAccountRepository,
)
from pixelle_video.services.publish.account_service import PublishAccountService
from pixelle_video.services.publish.profile_manager import BrowserProfileManager, ProfileLockError


class _ProbeContext:
    def __init__(self, logged_in: bool):
        self.logged_in = logged_in

    async def open_creator_page(self):
        return None

    async def is_logged_in(self):
        return self.logged_in

    async def login_subject_hint(self):
        return "测试账号" if self.logged_in else None


class _ProbeRuntime:
    def __init__(self, profile_path: str, logged_in: bool):
        self.profile_path = profile_path
        self.logged_in = logged_in

    async def launch_persistent_context(self, platform: str, *, profile_path=None, account_id=None):
        assert profile_path == self.profile_path
        assert platform == "douyin"
        assert account_id
        return _ProbeContext(self.logged_in)

    async def close(self):
        return None


class _SubjectRuntime(_ProbeRuntime):
    def __init__(self, profile_path: str, subject: str | None):
        super().__init__(profile_path, logged_in=subject is not None)
        self.subject = subject

    async def launch_persistent_context(self, platform: str, *, profile_path=None, account_id=None):
        return _ProbeContextWithSubject(self.logged_in, self.subject)


class _ProbeContextWithSubject(_ProbeContext):
    def __init__(self, logged_in: bool, subject: str | None):
        super().__init__(logged_in)
        self.subject = subject

    async def login_subject_hint(self):
        return self.subject


def test_probe_transitions_to_authenticated_without_persisting_credentials(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    manager = BrowserProfileManager(tmp_path / "accounts", legacy_profile_root=tmp_path / "legacy", repository=repository)
    holder = {}

    def factory(profile_path):
        holder["path"] = profile_path
        return _ProbeRuntime(profile_path, logged_in=True)

    service = PublishAccountService(repository, manager, runtime_factory=factory)
    account = service.create_account(PublishPlatform.DOUYIN, "探测账号")
    result = asyncio.run(service.probe_account(account.account_id))
    assert result.login_state == "authenticated"
    assert result.verification_state == "verified"
    assert result.login_subject_hint == "测试账号"
    assert "cookie" not in result.model_dump_json().lower()
    assert "token" not in result.model_dump_json().lower()
    raw_db = sqlite3.connect(repository.db_path).execute(
        "SELECT group_concat(COALESCE(login_subject_hint, ''), '|') FROM publish_account_state"
    ).fetchone()[0]
    assert "cookie" not in raw_db.lower()
    assert "token" not in raw_db.lower()
    assert "qr" not in raw_db.lower()
    assert manager.context_registry(result) == []


def test_probe_records_login_required_without_marking_verified(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    manager = BrowserProfileManager(tmp_path / "accounts", legacy_profile_root=tmp_path / "legacy", repository=repository)

    def factory(profile_path):
        return _ProbeRuntime(profile_path, logged_in=False)

    service = PublishAccountService(repository, manager, runtime_factory=factory)
    account = service.create_account(PublishPlatform.DOUYIN, "待登录账号")
    result = asyncio.run(service.probe_account(account.account_id))
    assert result.login_state == "login_required"
    assert result.verification_state == "unverified"
    assert result.last_error_code == "LOGIN_REQUIRED"


def test_repeated_probe_reuses_one_profile_and_detects_expiry(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    manager = BrowserProfileManager(
        tmp_path / "accounts", legacy_profile_root=tmp_path / "legacy", repository=repository
    )
    calls = {"logged_in": True}

    def factory(profile_path):
        return _SubjectRuntime(profile_path, "账号 A" if calls["logged_in"] else None)

    service = PublishAccountService(repository, manager, runtime_factory=factory)
    account = service.create_account(PublishPlatform.DOUYIN, "可复用账号")
    first_path = manager.profile_path(account)
    for _ in range(10):
        assert asyncio.run(service.probe_account(account.account_id)).login_state == "authenticated"
    calls["logged_in"] = False
    expired = asyncio.run(service.probe_account(account.account_id))
    assert expired.login_state == "expired"
    assert expired.last_error_code == "LOGIN_EXPIRED"
    assert manager.profile_path(expired) == first_path
    assert len(list(first_path.parent.iterdir())) == 2  # profile + owned lock
    active = service._active_connections[account.account_id]
    asyncio.run(service._close_connection(account.account_id, active))
    assert len(list(first_path.parent.iterdir())) == 1


def test_archive_rejects_active_login_window_until_it_is_closed(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    manager = BrowserProfileManager(
        tmp_path / "accounts", legacy_profile_root=tmp_path / "legacy", repository=repository
    )

    def factory(profile_path):
        return _ProbeRuntime(profile_path, logged_in=False)

    service = PublishAccountService(repository, manager, runtime_factory=factory)
    account = service.create_account(PublishPlatform.DOUYIN, "活动窗口账号")
    result = asyncio.run(service.probe_account(account.account_id))
    assert result.login_state == "login_required"
    profile_path = manager.profile_path(account)
    lock_rows = repository.list_profile_locks(account.account_id)
    context_rows = repository.list_contexts(account.account_id)
    assert lock_rows and context_rows
    with pytest.raises(PublishAccountConflict):
        service.archive(account.account_id)
    assert repository.get_account(account.account_id).archived_at is None
    assert profile_path.exists()
    active = service._active_connections[account.account_id]
    asyncio.run(service._close_connection(account.account_id, active))
    archived = service.archive(account.account_id)
    assert archived.archived_at


def test_clear_profile_rejects_retained_login_window_without_deleting_profile(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    manager = BrowserProfileManager(
        tmp_path / "accounts", legacy_profile_root=tmp_path / "legacy", repository=repository
    )

    def factory(profile_path):
        return _ProbeRuntime(profile_path, logged_in=False)

    service = PublishAccountService(repository, manager, runtime_factory=factory)
    account = service.create_account(PublishPlatform.DOUYIN, "清理保护账号")
    asyncio.run(service.probe_account(account.account_id))
    marker = manager.profile_path(account) / "opaque-browser-state"
    marker.write_text("keep until explicit close", encoding="utf-8")
    with pytest.raises(ProfileLockError):
        service.clear_profile(account.account_id)
    assert marker.exists()
    assert repository.list_profile_locks(account.account_id)
    assert repository.list_contexts(account.account_id)
    active = service._active_connections[account.account_id]
    asyncio.run(service._close_connection(account.account_id, active))
    service.clear_profile(account.account_id)
    assert not marker.exists()


def test_identity_change_is_degraded_and_does_not_replace_fingerprint(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    manager = BrowserProfileManager(
        tmp_path / "accounts", legacy_profile_root=tmp_path / "legacy", repository=repository
    )
    subject = {"value": "账号 A"}

    def factory(profile_path):
        return _SubjectRuntime(profile_path, subject["value"])

    service = PublishAccountService(repository, manager, runtime_factory=factory)
    account = service.create_account(PublishPlatform.DOUYIN, "身份隔离账号")
    assert asyncio.run(service.probe_account(account.account_id)).login_state == "authenticated"
    first_fingerprint = repository.get_identity_fingerprint(account.account_id)
    subject["value"] = "账号 B"
    changed = asyncio.run(service.probe_account(account.account_id))
    assert changed.login_state == "identity_changed"
    assert changed.verification_state == "degraded"
    assert changed.last_error_code == "IDENTITY_CHANGED"
    assert repository.get_identity_fingerprint(account.account_id) == first_fingerprint
