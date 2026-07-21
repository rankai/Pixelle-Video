"""Canonical local browser-profile paths, locks, and context registry helpers."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pixelle_video.services.publish.account_models import PublishAccount
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.utils.os_util import get_data_path

PROFILE_REF_PATTERN = re.compile(r"^profile_[A-Za-z0-9_-]+$")


class ProfilePathError(ValueError):
    """A profile reference cannot be resolved inside the canonical root."""


class ProfileLockError(RuntimeError):
    """Another process owns a profile lock."""


@dataclass
class ProfileLock:
    path: Path
    owner_ref: str
    on_release: Callable[[], None] | None = None
    _released: bool = False

    def release(self) -> None:
        if self._released:
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            payload = {}
        if payload.get("owner_ref") not in {None, self.owner_ref}:
            return
        self.path.unlink(missing_ok=True)
        self._released = True
        if self.on_release:
            self.on_release()

    def __enter__(self) -> "ProfileLock":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.release()


class BrowserProfileManager:
    """Owns profile directories only; browser credentials stay in the profile."""

    def __init__(
        self,
        profile_root: str | Path | None = None,
        *,
        legacy_profile_root: str | Path | None = None,
        stale_lock_seconds: float = 300,
        repository: PublishAccountRepository | None = None,
    ):
        self.profile_root = Path(
            profile_root or get_data_path("publish_browser", "accounts")
        ).resolve()
        self.legacy_profile_root = Path(legacy_profile_root or get_data_path("publish_browser")).resolve()
        self.profile_root.mkdir(parents=True, exist_ok=True)
        self.stale_lock_seconds = stale_lock_seconds
        self.repository = repository

    def profile_path(self, account: PublishAccount) -> Path:
        if not PROFILE_REF_PATTERN.fullmatch(account.profile_ref):
            raise ProfilePathError("profile_ref 格式非法")
        is_legacy = account.profile_ref.endswith("_legacy")
        if is_legacy:
            path = (self.legacy_profile_root / account.platform.value).resolve()
            allowed_root = self.legacy_profile_root
        else:
            path = (self.profile_root / account.platform.value / account.profile_ref).resolve()
            allowed_root = self.profile_root
        try:
            path.relative_to(allowed_root)
        except ValueError as exc:
            raise ProfilePathError("profile_ref 不在 canonical app-data 根目录内") from exc
        return path

    def ensure_profile(self, account: PublishAccount) -> Path:
        path = self.profile_path(account)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _lock_path(self, account: PublishAccount) -> Path:
        path = self.profile_path(account)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.parent / f".{account.profile_ref}.lock"

    def acquire_lock(
        self,
        account: PublishAccount,
        *,
        owner_ref: str | None = None,
        stale_lock_seconds: float | None = None,
    ) -> ProfileLock:
        lock_path = self._lock_path(account)
        owner_ref = owner_ref or f"owner_{uuid.uuid4().hex[:16]}"
        payload = {
            "owner_ref": owner_ref,
            "pid": os.getpid(),
            "acquired_at": time.time(),
        }
        for attempt in range(2):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, separators=(",", ":"))
                if self.repository:
                    try:
                        self.repository.register_profile_lock(
                            account.account_id, owner_ref, os.getpid()
                        )
                    except Exception:
                        lock_path.unlink(missing_ok=True)
                        raise
                return ProfileLock(
                    lock_path,
                    owner_ref,
                    on_release=(
                        lambda: self.repository.clear_profile_lock(account.account_id, owner_ref)
                        if self.repository
                        else None
                    ),
                )
            except FileExistsError as exc:
                if attempt == 0 and self._is_stale_lock(
                    lock_path, stale_lock_seconds if stale_lock_seconds is not None else self.stale_lock_seconds
                ):
                    lock_path.unlink(missing_ok=True)
                    continue
                raise ProfileLockError("该发布账号的浏览器 profile 正被其他窗口使用") from exc
        raise ProfileLockError("无法获取浏览器 profile 锁")

    def release_lock(self, account: PublishAccount, owner_ref: str) -> None:
        """Release a lock owned by this run during restart/terminal recovery."""
        lock_path = self._lock_path(account)
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            payload = {}
        if payload.get("owner_ref") == owner_ref:
            lock_path.unlink(missing_ok=True)
            if self.repository:
                self.repository.clear_profile_lock(account.account_id, owner_ref)

    def _is_stale_lock(self, lock_path: Path, max_age: float) -> bool:
        try:
            payload = json.loads(lock_path.read_text(encoding="utf-8"))
            acquired_at = float(payload.get("acquired_at", 0))
            pid = int(payload.get("pid", 0))
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return True
        if time.time() - acquired_at <= max_age:
            return False
        if pid <= 0 or pid == os.getpid():
            return pid != os.getpid()
        try:
            os.kill(pid, 0)
        except OSError:
            return True
        return False

    def clear_profile(self, account: PublishAccount) -> Path:
        path = self.ensure_profile(account)
        with self.acquire_lock(account):
            for child in path.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)
        if self.repository:
            self.repository.mark_profile_cleared(account.account_id)
        return path

    def context_registry(self, account: PublishAccount) -> list[dict[str, Any]]:
        if not self.repository:
            return []
        return self.repository.list_contexts(account.account_id)

    def register_context(self, account: PublishAccount, *, window_ref: str | None = None) -> dict[str, Any]:
        if not self.repository:
            raise RuntimeError("BrowserProfileManager 需要 repository 才能登记 context")
        return self.repository.register_context(account.account_id, window_ref=window_ref)

    def close_context(self, context_id: str, *, stale: bool = False) -> None:
        if self.repository:
            self.repository.close_context(context_id, stale=stale)
