"""Publish-account domain models and safe state vocabulary."""

from enum import StrEnum

from pydantic import BaseModel, Field


class PublishPlatform(StrEnum):
    DOUYIN = "douyin"
    VIDEO_CHANNEL = "video_channel"
    KUAISHOU = "kuaishou"
    XIAOHONGSHU = "xiaohongshu"


class AccountVerificationState(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    DEGRADED = "degraded"
    REVOKED = "revoked"


class AccountLoginState(StrEnum):
    NOT_CONNECTED = "not_connected"
    CONNECTING = "connecting"
    LOGIN_REQUIRED = "login_required"
    AUTHENTICATED = "authenticated"
    EXPIRED = "expired"
    IDENTITY_CHANGED = "identity_changed"
    DEGRADED = "degraded"
    LOCKED = "locked"
    REVOKED = "revoked"


# The UI/API use the explicit PUB-1 vocabulary below.  Keeping the transition
# table next to the enum prevents a probe or future caller from silently
# jumping from a terminal/identity-sensitive state to ``authenticated``.
ACCOUNT_LOGIN_TRANSITIONS: dict[AccountLoginState, frozenset[AccountLoginState]] = {
    AccountLoginState.NOT_CONNECTED: frozenset(
        {AccountLoginState.CONNECTING, AccountLoginState.REVOKED}
    ),
    AccountLoginState.CONNECTING: frozenset(
        {
            AccountLoginState.AUTHENTICATED,
            AccountLoginState.LOGIN_REQUIRED,
            AccountLoginState.EXPIRED,
            AccountLoginState.IDENTITY_CHANGED,
            AccountLoginState.DEGRADED,
            AccountLoginState.LOCKED,
            AccountLoginState.REVOKED,
        }
    ),
    AccountLoginState.LOGIN_REQUIRED: frozenset(
        {AccountLoginState.CONNECTING, AccountLoginState.REVOKED}
    ),
    AccountLoginState.AUTHENTICATED: frozenset(
        {
            AccountLoginState.CONNECTING,
            AccountLoginState.EXPIRED,
            AccountLoginState.IDENTITY_CHANGED,
            AccountLoginState.DEGRADED,
            AccountLoginState.REVOKED,
        }
    ),
    AccountLoginState.EXPIRED: frozenset(
        {AccountLoginState.CONNECTING, AccountLoginState.REVOKED}
    ),
    AccountLoginState.IDENTITY_CHANGED: frozenset(
        {AccountLoginState.CONNECTING, AccountLoginState.REVOKED}
    ),
    AccountLoginState.DEGRADED: frozenset(
        {
            AccountLoginState.CONNECTING,
            AccountLoginState.LOGIN_REQUIRED,
            AccountLoginState.AUTHENTICATED,
            AccountLoginState.REVOKED,
        }
    ),
    AccountLoginState.LOCKED: frozenset(
        {AccountLoginState.CONNECTING, AccountLoginState.DEGRADED, AccountLoginState.REVOKED}
    ),
    AccountLoginState.REVOKED: frozenset(),
}


class PublishAccount(BaseModel):
    """Safe account projection; credentials and profile paths never appear."""

    schema_version: int = 1
    account_id: str
    platform: PublishPlatform
    display_name: str
    profile_ref: str
    verification_state: AccountVerificationState
    login_state: AccountLoginState
    enabled: bool
    is_default: bool = False
    profile_exists: bool = False
    platform_release_state: str = "unverified"
    created_at: str
    updated_at: str
    last_verified_at: str | None = None
    last_error_code: str | None = None
    login_subject_hint: str | None = None
    archived_at: str | None = None


class PublishAccountCreate(BaseModel):
    platform: PublishPlatform
    display_name: str = Field(min_length=1, max_length=80)
    make_default: bool = False


class PublishPlatformCapability(BaseModel):
    platform: PublishPlatform
    display_name: str
    release_state: str
    account_count: int = 0
    default_account_id: str | None = None
