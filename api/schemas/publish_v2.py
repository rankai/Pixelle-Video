"""FastAPI schemas for the platform-neutral PUB-2 publishing API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pixelle_video.services.publish.account_models import PublishPlatform
from pixelle_video.services.publish.core_models import PlatformCopy, PublishPackageV2, PublishRun


class PublishPackageCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    artifact_version_ids: list[str] = Field(min_length=1, max_length=20)
    platform_copy: PlatformCopy = Field(default_factory=PlatformCopy)
    package_id: str | None = Field(default=None, pattern=r"^pkg_[A-Za-z0-9_-]+$")
    supersedes_package_id: str | None = Field(default=None, pattern=r"^pkg_[A-Za-z0-9_-]+$")


class PublishPackageFromSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    platform_copy: PlatformCopy = Field(default_factory=PlatformCopy)
    package_id: str | None = Field(default=None, pattern=r"^pkg_[A-Za-z0-9_-]+$")


class PublishPackageResponse(BaseModel):
    package: PublishPackageV2


class PublishRunCreateRequest(BaseModel):
    package_id: str = Field(min_length=1)
    account_id: str = Field(min_length=1)
    platform: PublishPlatform
    idempotency_key: str = Field(min_length=8, max_length=200)


class PublishRunAcceptedResponse(BaseModel):
    run_id: str
    task_id: str | None
    state: str
    requires_human_confirmation: Literal[True] = True
    idempotent_replay: bool


class PublishRunResponse(BaseModel):
    run: PublishRun


class PublishRetryStepRequest(BaseModel):
    step: str = Field(min_length=1, max_length=80)
    actor_ref: str | None = Field(default=None, max_length=120)


class PublishCancelRequest(BaseModel):
    actor_ref: str | None = Field(default=None, max_length=120)


class PublishOutcomeRequest(BaseModel):
    outcome: Literal["published_by_user", "abandoned_by_user"]
    actor_ref: str = Field(min_length=1, max_length=120)


class PublishEventsResponse(BaseModel):
    items: list[dict]
    next_after: int
