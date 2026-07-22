"""API schemas for local publishing accounts."""

from pydantic import BaseModel, Field

from pixelle_video.services.publish.account_models import (
    PublishAccount,
    PublishPlatform,
    PublishPlatformCapability,
)


class PublishAccountCreateRequest(BaseModel):
    platform: PublishPlatform
    display_name: str = Field(min_length=1, max_length=80)
    make_default: bool = False


class PublishAccountListResponse(BaseModel):
    items: list[PublishAccount]


class PublishPlatformListResponse(BaseModel):
    items: list[PublishPlatformCapability]
