"""PUB-2 publishing package/run domain models.

These models are the publishing facts.  The application center may reference a
package, but must not edit its snapshot in place.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .account_models import PublishPlatform


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class PublishRunState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_LOGIN = "waiting_for_login"
    WAITING_FOR_HUMAN = "waiting_for_human"
    NEEDS_ATTENTION = "needs_attention"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


RUN_TRANSITIONS: dict[PublishRunState, frozenset[PublishRunState]] = {
    PublishRunState.QUEUED: frozenset({PublishRunState.QUEUED, PublishRunState.RUNNING, PublishRunState.CANCELLED, PublishRunState.NEEDS_ATTENTION}),
    PublishRunState.RUNNING: frozenset({PublishRunState.RUNNING, PublishRunState.WAITING_FOR_LOGIN, PublishRunState.WAITING_FOR_HUMAN, PublishRunState.NEEDS_ATTENTION, PublishRunState.FAILED, PublishRunState.CANCELLED}),
    PublishRunState.WAITING_FOR_LOGIN: frozenset({PublishRunState.WAITING_FOR_LOGIN, PublishRunState.RUNNING, PublishRunState.NEEDS_ATTENTION, PublishRunState.CANCELLED}),
    PublishRunState.WAITING_FOR_HUMAN: frozenset({PublishRunState.WAITING_FOR_HUMAN, PublishRunState.SUCCEEDED, PublishRunState.NEEDS_ATTENTION, PublishRunState.CANCELLED}),
    PublishRunState.NEEDS_ATTENTION: frozenset({PublishRunState.NEEDS_ATTENTION, PublishRunState.QUEUED, PublishRunState.WAITING_FOR_HUMAN, PublishRunState.FAILED, PublishRunState.CANCELLED}),
    PublishRunState.SUCCEEDED: frozenset({PublishRunState.SUCCEEDED}),
    PublishRunState.FAILED: frozenset({PublishRunState.FAILED}),
    PublishRunState.CANCELLED: frozenset({PublishRunState.CANCELLED}),
}


class PublishSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(pattern="^(artifact_versions|legacy_session)$")
    artifact_ids: list[str] = Field(default_factory=list)
    artifact_version_ids: list[str] = Field(default_factory=list)
    session_id: str | None = None
    source_revision: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exactly_one_source(self) -> "PublishSource":
        if self.kind == "artifact_versions":
            if self.session_id is not None:
                raise ValueError("SOURCE_SESSION_MUST_BE_NULL")
            if not self.artifact_version_ids:
                raise ValueError("SOURCE_ARTIFACT_VERSION_REQUIRED")
            if len(self.artifact_ids) != len(self.artifact_version_ids):
                raise ValueError("SOURCE_ARTIFACT_ID_MISMATCH")
        elif not self.session_id:
            raise ValueError("LEGACY_SESSION_REQUIRED")
        elif self.artifact_ids or self.artifact_version_ids:
            raise ValueError("LEGACY_ARTIFACT_VERSIONS_FORBIDDEN")
        return self


class ArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    artifact_version_id: str
    artifact_type: str = Field(pattern="^(video|cover|publish_copy|carousel_package|carousel_page)$")
    content_fingerprint: str = Field(pattern="^sha256:.+")


class MediaManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sha256: str = Field(pattern="^sha256:.+")
    size_bytes: int = Field(gt=0)
    mime_type: str = Field(pattern="^(video|image)/.+")
    path_token: str = Field(pattern="^asset_[A-Za-z0-9_-]+$")
    duration_ms: int | None = Field(default=None, gt=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)


class PlatformCopy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", max_length=100)
    description: str = Field(default="", max_length=5000)
    hashtags: list[str] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_hashtags(self) -> "PlatformCopy":
        if len(set(self.hashtags)) != len(self.hashtags):
            raise ValueError("HASHTAGS_MUST_BE_UNIQUE")
        if any(len(tag) > 50 for tag in self.hashtags):
            raise ValueError("HASHTAG_TOO_LONG")
        return self


class PublishPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    human_confirmation_required: bool = True
    allow_final_publish: bool = False
    adapter_version: str = "platform-neutral@1"

    @model_validator(mode="after")
    def enforce_human_stop(self) -> "PublishPolicy":
        if not self.human_confirmation_required or self.allow_final_publish:
            raise ValueError("FINAL_PUBLISH_ACTION_NOT_ALLOWED")
        return self


class PublishPackageV2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 2
    package_id: str = Field(pattern="^pkg_[A-Za-z0-9_-]+$")
    project_id: str = Field(min_length=1)
    source: PublishSource
    artifact_refs: list[ArtifactRef] = Field(min_length=1)
    # V2 keeps the legacy field name for backwards compatibility. It is
    # populated for video packages and null for image-carousel packages.
    video_manifest: MediaManifest | None = None
    carousel_manifests: list[MediaManifest] | None = None
    cover_manifest: MediaManifest | None = None
    platform_copy: PlatformCopy = Field(default_factory=PlatformCopy)
    policy: PublishPolicy = Field(default_factory=PublishPolicy)
    package_fingerprint: str = Field(pattern="^sha256:.+")
    invalidated_at: str | None = None
    invalidation_reason: str | None = None
    created_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_source_refs(self) -> "PublishPackageV2":
        if self.source.kind == "artifact_versions":
            source_ids = set(self.source.artifact_version_ids)
            if any(ref.artifact_version_id not in source_ids for ref in self.artifact_refs):
                raise ValueError("SOURCE_VERSION_NOT_REFERENCED")
        video_count = sum(ref.artifact_type == "video" for ref in self.artifact_refs)
        carousel_count = sum(ref.artifact_type == "carousel_package" for ref in self.artifact_refs)
        if video_count == 1 and carousel_count == 0:
            if self.video_manifest is None:
                raise ValueError("VIDEO_MANIFEST_REQUIRED")
            if self.carousel_manifests:
                raise ValueError("CAROUSEL_MANIFEST_FORBIDDEN_FOR_VIDEO")
        elif video_count == 0 and carousel_count == 1:
            if self.video_manifest is not None:
                raise ValueError("VIDEO_MANIFEST_FORBIDDEN_FOR_CAROUSEL")
            if not self.carousel_manifests:
                raise ValueError("CAROUSEL_MANIFEST_REQUIRED")
            if any(not manifest.mime_type.startswith("image/") for manifest in self.carousel_manifests):
                raise ValueError("CAROUSEL_MANIFEST_MIME_INVALID")
        else:
            raise ValueError("VIDEO_OR_CAROUSEL_ARTIFACT_REF_REQUIRED")
        cover_count = sum(ref.artifact_type == "cover" for ref in self.artifact_refs)
        if cover_count > 1:
            raise ValueError("MULTIPLE_COVER_ARTIFACTS")
        if (cover_count == 1) != (self.cover_manifest is not None):
            raise ValueError("COVER_ARTIFACT_REF_REQUIRED")
        if (self.invalidated_at is None) != (self.invalidation_reason is None):
            raise ValueError("PACKAGE_INVALIDATION_INVARIANT")
        if self.video_manifest is not None and not self.video_manifest.mime_type.startswith("video/"):
            raise ValueError("VIDEO_MANIFEST_MIME_INVALID")
        if self.cover_manifest is not None and not self.cover_manifest.mime_type.startswith("image/"):
            raise ValueError("COVER_MANIFEST_MIME_INVALID")
        return self


class HumanConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: Literal[True] = True
    confirmed: bool = False
    confirmed_at: str | None = None
    actor_ref: str | None = None


class PublishRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    run_id: str = Field(pattern="^run_[A-Za-z0-9_-]+$")
    package_id: str
    account_id: str
    platform: PublishPlatform
    state: PublishRunState
    state_version: int = Field(ge=1)
    attempt: int = Field(ge=1)
    current_step: str | None = None
    idempotency_key: str = Field(min_length=8)
    human_confirmation: HumanConfirmation = Field(default_factory=HumanConfirmation)
    task_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    checkpoint: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def enforce_confirmation(self) -> "PublishRun":
        if not self.human_confirmation.required:
            raise ValueError("HUMAN_CONFIRMATION_REQUIRED")
        if self.state == PublishRunState.SUCCEEDED and not self.human_confirmation.confirmed:
            raise ValueError("SUCCESS_REQUIRES_HUMAN_CONFIRMATION")
        if self.state == PublishRunState.WAITING_FOR_HUMAN and self.human_confirmation.confirmed:
            raise ValueError("WAITING_FOR_HUMAN_CANNOT_BE_CONFIRMED")
        return self

    @property
    def human_confirmation_required(self) -> bool:
        return self.human_confirmation.required

    @property
    def human_confirmed(self) -> bool:
        return self.human_confirmation.confirmed

    @property
    def confirmed_at(self) -> str | None:
        return self.human_confirmation.confirmed_at

    @property
    def actor_ref(self) -> str | None:
        return self.human_confirmation.actor_ref


class PublishEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    run_id: str
    event_seq: int = Field(gt=0)
    event_type: str
    state: PublishRunState | None = None
    state_version: int = Field(gt=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class PublishStepAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step_attempt_id: str
    run_id: str
    step: str
    attempt: int = Field(gt=0)
    state: PublishRunState
    evidence_kind: str = "none"
    evidence_ref: str | None = None
    error_code: str | None = None
    created_at: str = Field(default_factory=utc_now)
    updated_at: str = Field(default_factory=utc_now)
