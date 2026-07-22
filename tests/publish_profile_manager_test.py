import json
import time

import pytest

from pixelle_video.services.publish.account_models import PublishPlatform
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.services.publish.profile_manager import BrowserProfileManager, ProfileLockError


def _account(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    account = repository.create_account(PublishPlatform.DOUYIN, "锁测试", "profile_lock")
    manager = BrowserProfileManager(tmp_path / "accounts", legacy_profile_root=tmp_path / "legacy", repository=repository)
    manager.ensure_profile(account)
    return repository, manager, account


def test_profile_lock_conflict_and_release(tmp_path):
    repository, manager, account = _account(tmp_path)
    with manager.acquire_lock(account, owner_ref="owner_a"):
        with pytest.raises(ProfileLockError):
            manager.acquire_lock(account, owner_ref="owner_b", stale_lock_seconds=999999)
        assert repository.list_profile_locks(account.account_id)[0]["owner_ref"] == "owner_a"
    with manager.acquire_lock(account, owner_ref="owner_b"):
        pass
    assert repository.list_profile_locks(account.account_id) == []


def test_stale_profile_lock_can_be_recovered_without_touching_profile(tmp_path):
    _repository, manager, account = _account(tmp_path)
    lock_path = manager._lock_path(account)
    lock_path.write_text(json.dumps({"owner_ref": "dead", "pid": 99999999, "acquired_at": time.time() - 999}), encoding="utf-8")
    marker = manager.profile_path(account) / "keep.txt"
    marker.write_text("profile data", encoding="utf-8")
    with manager.acquire_lock(account, owner_ref="new", stale_lock_seconds=1):
        assert marker.read_text(encoding="utf-8") == "profile data"
    assert not lock_path.exists()


def test_clear_profile_only_clears_contents_and_keeps_account(tmp_path):
    repository, manager, account = _account(tmp_path)
    marker = manager.profile_path(account) / "browser-state"
    marker.write_text("opaque local state", encoding="utf-8")
    cleared_path = manager.clear_profile(account)
    assert cleared_path.exists()
    assert not marker.exists()
    assert repository.get_account(account.account_id).login_state == "not_connected"


def test_profile_ref_cannot_escape_canonical_root(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    account = repository.create_account(PublishPlatform.DOUYIN, "路径测试", "profile_safe")
    account.profile_ref = "profile_../../escape"
    manager = BrowserProfileManager(tmp_path / "accounts", repository=repository)
    with pytest.raises(ValueError):
        manager.profile_path(account)


def test_accounts_on_same_platform_have_isolated_profile_directories(tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    manager = BrowserProfileManager(tmp_path / "accounts", repository=repository)
    account_a = repository.create_account(PublishPlatform.DOUYIN, "账号 A", "profile_a")
    account_b = repository.create_account(PublishPlatform.DOUYIN, "账号 B", "profile_b")
    path_a = manager.ensure_profile(account_a)
    path_b = manager.ensure_profile(account_b)
    assert path_a != path_b
    (path_a / "only-a").write_text("a", encoding="utf-8")
    assert not (path_b / "only-a").exists()
