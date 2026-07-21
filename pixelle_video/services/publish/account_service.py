"""Application service for safe local publish-account operations."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Callable

from pixelle_video.services.publish.account_models import (
    AccountLoginState,
    AccountVerificationState,
    PublishAccount,
    PublishPlatform,
    PublishPlatformCapability,
)
from pixelle_video.services.publish.account_repository import (
    PLATFORM_LABELS,
    PublishAccountConflict,
    PublishAccountRepository,
)
from pixelle_video.services.publish.browser_runtime import PlaywrightBrowserRuntime
from pixelle_video.services.publish.profile_manager import (
    BrowserProfileManager,
    ProfileLock,
    ProfileLockError,
)


@dataclass
class _ActiveConnection:
    runtime: Any
    context: Any
    context_id: str
    lock: ProfileLock


class PublishAccountService:
    """Coordinates repository, profile paths and explicit login probes."""

    def __init__(
        self,
        repository: PublishAccountRepository | None = None,
        profile_manager: BrowserProfileManager | None = None,
        runtime_factory: Callable[[str], Any] | None = None,
    ):
        self.repository = repository or PublishAccountRepository()
        self.profile_manager = profile_manager or BrowserProfileManager(repository=self.repository)
        self.repository.mark_open_contexts_stale()
        self.runtime_factory = runtime_factory or (lambda profile_path: PlaywrightBrowserRuntime(profile_path))
        self._active_connections: dict[str, _ActiveConnection] = {}
        self.migrate_legacy_profiles()

    def migrate_legacy_profiles(self) -> list[PublishAccount]:
        """Register existing V1 profiles without opening, copying, or reading them."""
        migrated: list[PublishAccount] = []
        for platform in PublishPlatform:
            legacy_path = self.profile_manager.legacy_profile_root / platform.value
            if not legacy_path.exists() or not legacy_path.is_dir():
                continue
            profile_ref = f"profile_{platform.value}_legacy"
            existing = self.repository.find_by_profile_ref(profile_ref)
            if existing:
                continue
            account = self.repository.create_account(
                platform,
                f"{PLATFORM_LABELS[platform.value]}现有本机账号",
                profile_ref,
                make_default=True,
            )
            migrated.append(
                self.repository.record_probe(
                    account.account_id,
                    login_state=AccountLoginState.NOT_CONNECTED,
                    verification_state=AccountVerificationState.UNVERIFIED,
                    profile_exists=True,
                )
            )
        return migrated

    def list_accounts(self, *, include_archived: bool = False) -> list[PublishAccount]:
        return self.repository.list_accounts(include_archived=include_archived)

    def list_platforms(self) -> list[PublishPlatformCapability]:
        accounts = self.repository.list_accounts()
        by_platform: dict[str, list[PublishAccount]] = {}
        for account in accounts:
            by_platform.setdefault(account.platform.value, []).append(account)
        result = []
        for platform in PublishPlatform:
            platform_accounts = by_platform.get(platform.value, [])
            default = next((account for account in platform_accounts if account.is_default), None)
            result.append(
                PublishPlatformCapability(
                    platform=platform,
                    display_name=PLATFORM_LABELS[platform.value],
                    release_state="pilot" if platform == PublishPlatform.DOUYIN else "unverified",
                    account_count=len(platform_accounts),
                    default_account_id=default.account_id if default else None,
                )
            )
        return result

    def create_account(
        self,
        platform: PublishPlatform,
        display_name: str,
        *,
        make_default: bool = False,
    ) -> PublishAccount:
        normalized_name = re.sub(r"\s+", " ", display_name).strip()
        if not normalized_name:
            raise ValueError("账号名称不能为空")
        account_id = self._new_account_id()
        profile_ref = self._profile_ref(account_id)
        account = self.repository.create_account(
            platform,
            normalized_name,
            profile_ref,
            make_default=make_default,
            account_id=account_id,
        )
        self.profile_manager.ensure_profile(account)
        return self.repository.record_probe(
            account.account_id,
            login_state=AccountLoginState.NOT_CONNECTED,
            verification_state=AccountVerificationState.UNVERIFIED,
            profile_exists=True,
        )

    def set_default(self, account_id: str) -> PublishAccount:
        return self.repository.set_default(account_id)

    def archive(self, account_id: str) -> PublishAccount:
        if account_id in self._active_connections:
            raise PublishAccountConflict("账号仍有活动浏览器上下文，请关闭登录窗口后再归档")
        return self.repository.archive(account_id)

    def clear_profile(self, account_id: str) -> PublishAccount:
        account = self.repository.get_account(account_id, include_archived=False)
        self.profile_manager.clear_profile(account)
        return self.repository.get_account(account_id)

    async def probe_account(self, account_id: str) -> PublishAccount:
        account = self.repository.get_account(account_id, include_archived=False)
        profile_path = self.profile_manager.ensure_profile(account)
        previous_fingerprint = self.repository.get_identity_fingerprint(account_id)
        # Persist the in-flight state before trying to acquire the cross-process
        # lock, so a collision is represented as connecting -> locked rather
        # than an invalid not_connected -> locked jump.
        self.repository.record_probe(
            account_id,
            login_state=AccountLoginState.CONNECTING,
            verification_state=AccountVerificationState.UNVERIFIED,
            profile_exists=True,
            login_subject_hint=account.login_subject_hint,
            identity_fingerprint=previous_fingerprint,
        )
        connection = self._active_connections.get(account_id)
        lock: ProfileLock | None = connection.lock if connection else None
        runtime: Any | None = None
        retain_connection = False
        try:
            if connection is None:
                try:
                    lock = self.profile_manager.acquire_lock(account)
                except ProfileLockError:
                    return self.repository.record_probe(
                        account_id,
                        login_state=AccountLoginState.LOCKED,
                        verification_state=AccountVerificationState.DEGRADED,
                        profile_exists=profile_path.exists(),
                        error_code="PROFILE_LOCKED",
                    )
                runtime = self.runtime_factory(str(profile_path))
                context = await runtime.launch_persistent_context(
                    account.platform.value,
                    profile_path=str(profile_path),
                    account_id=account.account_id,
                )
                context_record = self.profile_manager.register_context(account)
                connection = _ActiveConnection(
                    runtime=runtime,
                    context=context,
                    context_id=context_record["context_id"],
                    lock=lock,
                )
            else:
                context = connection.context
            await _call(context, "open_creator_page")
            logged_in = bool(await _call(context, "is_logged_in", default=False))
            subject_hint = _safe_subject_hint(await _call(context, "login_subject_hint", default=None))
            fingerprint = _fingerprint(subject_hint) if subject_hint else None
            if logged_in:
                if previous_fingerprint and fingerprint and previous_fingerprint != fingerprint:
                    return self.repository.record_probe(
                        account_id,
                        login_state=AccountLoginState.IDENTITY_CHANGED,
                    verification_state=AccountVerificationState.DEGRADED,
                        profile_exists=True,
                        login_subject_hint=subject_hint,
                        identity_fingerprint=previous_fingerprint,
                        error_code="IDENTITY_CHANGED",
                    )
                result = self.repository.record_probe(
                    account_id,
                    login_state=AccountLoginState.AUTHENTICATED,
                    verification_state=AccountVerificationState.VERIFIED,
                    profile_exists=True,
                    login_subject_hint=subject_hint,
                    identity_fingerprint=fingerprint,
                )
            else:
                result = self.repository.record_probe(
                    account_id,
                    login_state=(
                        AccountLoginState.EXPIRED
                        if previous_fingerprint
                        else AccountLoginState.LOGIN_REQUIRED
                    ),
                    verification_state=AccountVerificationState.UNVERIFIED,
                    profile_exists=True,
                    error_code=("LOGIN_EXPIRED" if previous_fingerprint else "LOGIN_REQUIRED"),
                )
                # Keep the visible browser and profile lock for the explicit
                # user login step. A subsequent probe reuses this context.
                self._active_connections[account_id] = connection
                retain_connection = True
            return result
        except Exception:
            return self.repository.record_probe(
                account_id,
                login_state=AccountLoginState.DEGRADED,
                verification_state=AccountVerificationState.DEGRADED,
                profile_exists=profile_path.exists(),
                error_code="LOGIN_PROBE_FAILED",
            )
        finally:
            if not retain_connection:
                if connection is not None:
                    await self._close_connection(account_id, connection)
                else:
                    if runtime is not None:
                        try:
                            await runtime.close()
                        except Exception:
                            pass
                    if lock is not None:
                        lock.release()

    async def _close_connection(self, account_id: str, connection: _ActiveConnection) -> None:
        if self._active_connections.get(account_id) is connection:
            self._active_connections.pop(account_id, None)
        self.profile_manager.close_context(connection.context_id)
        try:
            await connection.runtime.close()
        except Exception:
            # Browser shutdown must never leave a profile lock behind.
            pass
        finally:
            connection.lock.release()

    @staticmethod
    def _new_account_id() -> str:
        import uuid

        return f"acct_{uuid.uuid4().hex[:16]}"

    @staticmethod
    def _profile_ref(account_id: str) -> str:
        return f"profile_{account_id.removeprefix('acct_')}"


async def _call(target: Any, method_name: str, *args: Any, default: Any = None) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        return default
    value = method(*args)
    if hasattr(value, "__await__"):
        return await value
    return value


def _safe_subject_hint(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = re.sub(r"[^\w\u4e00-\u9fff ._-]", "", value).strip()
    return value[:80] or None


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]
