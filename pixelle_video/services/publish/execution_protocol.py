"""Stateful publishing execution facts shared by adapters and runtimes.

This module intentionally contains no browser calls.  It defines the small,
serializable contract that lets a runtime resume an existing draft without
turning a file injection or a partial UI mutation into a successful run.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class PublishStage(StrEnum):
    INSPECT = "inspect"
    UPLOAD = "upload"
    WAIT = "wait"
    MUTATE = "mutate"
    VERIFY = "verify"


class UploadMode(StrEnum):
    ALREADY_READY = "already_ready"
    RESUME_EXISTING = "resume_existing"
    INJECTED = "injected"


class PublishBlockerCode(StrEnum):
    AUTH_REQUIRED = "AUTH_REQUIRED"
    CHALLENGE_REQUIRED = "CHALLENGE_REQUIRED"
    USER_CONTROL = "USER_CONTROL"
    FOREIGN_DRAFT = "FOREIGN_DRAFT"
    UPLOAD_NOT_STARTED = "UPLOAD_NOT_STARTED"
    UPLOAD_STALLED = "UPLOAD_STALLED"
    INPUT_CHANNEL_BROKEN = "INPUT_CHANNEL_BROKEN"
    PLATFORM_REJECTED_ASSET = "PLATFORM_REJECTED_ASSET"
    TOPIC_READBACK_MISMATCH = "TOPIC_READBACK_MISMATCH"
    COVER_READBACK_MISMATCH = "COVER_READBACK_MISMATCH"
    FINAL_ACTION_GUARD_FAILED = "FINAL_ACTION_GUARD_FAILED"
    SELECTOR_DRIFT = "SELECTOR_DRIFT"
    STATE_AMBIGUOUS = "STATE_AMBIGUOUS"
    ACTION_FAILED = "ACTION_FAILED"


class DraftIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_kind: str = Field(min_length=1, max_length=40)
    profile_ref: str = Field(pattern=r"^profile_[A-Za-z0-9_-]+$")
    task_space_id: int | None = Field(default=None, gt=0)
    task_space_name: str | None = Field(default=None, min_length=1, max_length=200)
    page_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    media_identity: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    remote_media_identity: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def require_task_space_pair(self) -> "DraftIdentity":
        if (self.task_space_id is None) != (self.task_space_name is None):
            raise ValueError("TASK_SPACE_ID_NAME_MUST_BE_PAIRED")
        return self


class TopicEntityEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=80)
    normalized_label: str = Field(min_length=1, max_length=80)
    mention_type: str = Field(pattern=r"^(#|activity)$")
    entity_id: str = Field(min_length=1, max_length=160)


class CoverReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str = Field(pattern=r"^(single|portrait|landscape)$")
    ratio: str = Field(pattern=r"^[0-9]+:[0-9]+$")
    asset_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    asset_path_token: str = Field(pattern=r"^asset_[A-Za-z0-9_-]+$")
    before_urls: list[str] = Field(default_factory=list, max_length=8)
    accepted_url: str = Field(min_length=1, max_length=500)
    task_space_id: int | None = Field(default=None, gt=0)
    reused_existing: bool = False

    @field_validator("ratio")
    @classmethod
    def validate_positive_ratio(cls, value: str) -> str:
        width, height = (int(item) for item in value.split(":", 1))
        if width <= 0 or height <= 0:
            raise ValueError("COVER_RATIO_MUST_BE_POSITIVE")
        return value

    @field_validator("before_urls", mode="before")
    @classmethod
    def canonicalize_before_urls(cls, value: Any) -> list[str]:
        return [_canonical_public_url(item) for item in (value or [])]

    @field_validator("accepted_url", mode="before")
    @classmethod
    def canonicalize_accepted_url(cls, value: Any) -> str:
        return _canonical_public_url(value)

    @model_validator(mode="after")
    def validate_slot_and_url(self) -> "CoverReceipt":
        if self.accepted_url in set(self.before_urls) and not self.reused_existing:
            raise ValueError("COVER_ACCEPTED_URL_MUST_CHANGE")
        return self


class PublishExecutionCheckpoint(BaseModel):
    """Fingerprint-bound, secret-free progress for one PublishRun attempt."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2] = 2
    package_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    account_id: str = Field(min_length=1, max_length=160)
    platform: str = Field(min_length=1, max_length=40)
    attempt: int = Field(gt=0)
    runtime_kind: str = Field(min_length=1, max_length=40)
    draft_identity: DraftIdentity | None = None
    completed_stages: list[PublishStage] = Field(default_factory=list, max_length=5)
    last_stage: PublishStage | None = None
    blocked_stage: PublishStage | None = None
    upload_mode: UploadMode | None = None
    media_sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    topic_entities: list[TopicEntityEvidence] = Field(default_factory=list, max_length=5)
    cover_receipts: list[CoverReceipt] = Field(default_factory=list, max_length=2)
    platform_fallback_boundaries: list[str] = Field(default_factory=list, max_length=5)
    blocker_code: PublishBlockerCode | None = None
    final_publish_clicked: bool = False
    final_publish_click_count: int = Field(default=0, ge=0)
    final_action_guard_armed: bool = False

    @model_validator(mode="after")
    def enforce_safe_and_ordered_state(self) -> "PublishExecutionCheckpoint":
        if self.final_publish_clicked or self.final_publish_click_count != 0:
            raise ValueError("FINAL_PUBLISH_CLICK_FORBIDDEN")
        stage_order = list(PublishStage)
        expected_prefix = stage_order[: len(self.completed_stages)]
        if self.completed_stages != expected_prefix:
            raise ValueError("COMPLETED_STAGES_MUST_BE_CONTIGUOUS_PREFIX")
        expected_last = self.completed_stages[-1] if self.completed_stages else None
        if self.last_stage != expected_last:
            raise ValueError("LAST_STAGE_MUST_MATCH_COMPLETED_PREFIX")
        if self.draft_identity is not None and self.draft_identity.runtime_kind != self.runtime_kind:
            raise ValueError("DRAFT_IDENTITY_RUNTIME_MISMATCH")
        if PublishStage.INSPECT in self.completed_stages and self.draft_identity is None:
            raise ValueError("INSPECT_REQUIRES_DRAFT_IDENTITY")
        if self.upload_mode is not None and PublishStage.UPLOAD not in self.completed_stages:
            raise ValueError("UPLOAD_MODE_REQUIRES_UPLOAD_STAGE")
        if PublishStage.UPLOAD in self.completed_stages and (self.upload_mode is None or self.media_sha256 is None):
            raise ValueError("UPLOAD_STAGE_REQUIRES_MODE_AND_MEDIA_DIGEST")
        if PublishStage.UPLOAD in self.completed_stages and self.draft_identity and self.draft_identity.media_identity is None:
            raise ValueError("UPLOAD_STAGE_REQUIRES_MEDIA_IDENTITY")
        if self.topic_entities and PublishStage.MUTATE not in self.completed_stages:
            raise ValueError("TOPIC_EVIDENCE_REQUIRES_MUTATE_STAGE")
        if self.cover_receipts and PublishStage.MUTATE not in self.completed_stages:
            raise ValueError("COVER_RECEIPT_REQUIRES_MUTATE_STAGE")
        if self.blocker_code is None:
            if self.blocked_stage is not None:
                raise ValueError("BLOCKED_STAGE_REQUIRES_BLOCKER")
        else:
            if self.blocked_stage is None:
                raise ValueError("BLOCKER_REQUIRES_BLOCKED_STAGE")
            if BLOCKER_REGISTRY[self.blocker_code].stage != self.blocked_stage:
                raise ValueError("BLOCKER_STAGE_MISMATCH")
            next_stage = stage_order[len(self.completed_stages)] if len(self.completed_stages) < len(stage_order) else None
            if self.blocked_stage != next_stage:
                raise ValueError("BLOCKED_STAGE_MUST_BE_NEXT")
        if PublishStage.VERIFY in self.completed_stages and not self.final_action_guard_armed:
            raise ValueError("VERIFY_REQUIRES_FINAL_GUARD")
        return self

    def as_checkpoint(self) -> dict[str, Any]:
        """Return only JSON-safe fields suitable for ``PublishRun.checkpoint``."""

        return self.model_dump(mode="json")


def parse_checkpoint(value: dict[str, Any] | None) -> PublishExecutionCheckpoint | None:
    """Parse persisted checkpoint data, failing closed on corrupt state."""

    if not value:
        return None
    return PublishExecutionCheckpoint.model_validate(value)


class BlockerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: PublishStage
    run_state: str = Field(pattern=r"^(waiting_for_login|waiting_for_human|needs_attention)$")
    retryable: bool
    recovery_action: str = Field(min_length=1, max_length=80)


BLOCKER_REGISTRY: dict[PublishBlockerCode, BlockerSpec] = {
    PublishBlockerCode.AUTH_REQUIRED: BlockerSpec(stage=PublishStage.INSPECT, run_state="waiting_for_login", retryable=True, recovery_action="reauthenticate_then_resume"),
    PublishBlockerCode.CHALLENGE_REQUIRED: BlockerSpec(stage=PublishStage.INSPECT, run_state="waiting_for_human", retryable=True, recovery_action="human_resolve_challenge_then_resume"),
    PublishBlockerCode.USER_CONTROL: BlockerSpec(stage=PublishStage.INSPECT, run_state="waiting_for_human", retryable=False, recovery_action="human_release_task_space"),
    PublishBlockerCode.FOREIGN_DRAFT: BlockerSpec(stage=PublishStage.INSPECT, run_state="needs_attention", retryable=False, recovery_action="inspect_or_quarantine_foreign_draft"),
    PublishBlockerCode.UPLOAD_NOT_STARTED: BlockerSpec(stage=PublishStage.UPLOAD, run_state="needs_attention", retryable=True, recovery_action="bounded_single_injection"),
    PublishBlockerCode.UPLOAD_STALLED: BlockerSpec(stage=PublishStage.UPLOAD, run_state="needs_attention", retryable=True, recovery_action="wait_or_bounded_reinject_once"),
    PublishBlockerCode.INPUT_CHANNEL_BROKEN: BlockerSpec(stage=PublishStage.UPLOAD, run_state="needs_attention", retryable=True, recovery_action="restart_runtime_then_resume_same_run"),
    PublishBlockerCode.PLATFORM_REJECTED_ASSET: BlockerSpec(stage=PublishStage.UPLOAD, run_state="needs_attention", retryable=False, recovery_action="replace_media_package"),
    PublishBlockerCode.TOPIC_READBACK_MISMATCH: BlockerSpec(stage=PublishStage.MUTATE, run_state="needs_attention", retryable=True, recovery_action="repair_missing_topic_entity"),
    PublishBlockerCode.COVER_READBACK_MISMATCH: BlockerSpec(stage=PublishStage.MUTATE, run_state="needs_attention", retryable=True, recovery_action="repair_cover_receipt"),
    PublishBlockerCode.FINAL_ACTION_GUARD_FAILED: BlockerSpec(stage=PublishStage.VERIFY, run_state="needs_attention", retryable=False, recovery_action="restore_final_action_guard"),
    PublishBlockerCode.SELECTOR_DRIFT: BlockerSpec(stage=PublishStage.MUTATE, run_state="needs_attention", retryable=False, recovery_action="adapter_diagnosis_required"),
    PublishBlockerCode.STATE_AMBIGUOUS: BlockerSpec(stage=PublishStage.INSPECT, run_state="needs_attention", retryable=False, recovery_action="human_resolve_draft_identity"),
    PublishBlockerCode.ACTION_FAILED: BlockerSpec(stage=PublishStage.MUTATE, run_state="needs_attention", retryable=True, recovery_action="retry_current_mutation_once"),
}


def _canonical_public_url(value: Any) -> str:
    raw = str(value or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("PUBLIC_HTTPS_URL_REQUIRED")
    if parsed.path.startswith("/") is False:
        raise ValueError("PUBLIC_URL_PATH_REQUIRED")
    return urlunsplit(("https", parsed.netloc, parsed.path or "/", "", ""))
