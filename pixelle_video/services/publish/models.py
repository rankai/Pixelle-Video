"""Data models for the desktop publishing assistant."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class PublishStatus(StrEnum):
    """Lifecycle states for browser-assisted publishing."""

    LOGIN_REQUIRED = "login_required"
    UPLOADING = "uploading"
    DRAFT_READY = "draft_ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PublishPackage(BaseModel):
    """A complete set of assets needed to prepare a platform draft."""

    session_id: str
    platform: Literal["douyin", "xiaohongshu", "shipinhao", "video_channel", "kuaishou"]
    video_path: str
    title: str
    description: str = ""
    hashtags: list[str] = Field(default_factory=list)
    cover_path: str = ""


class PublishResult(BaseModel):
    """Result returned by a platform publishing adapter."""

    status: PublishStatus
    platform: str
    message: str = ""
    task_id: str = ""
    draft_url: str = ""
    requires_human_confirmation: bool = True
    filled_fields: list[str] = Field(default_factory=list)
    # V1 keeps the historical ``status`` vocabulary.  The adapter_state
    # projection carries the PUB-3/PUB-4 state-machine meaning without
    # breaking old clients that only understand failed/login_required.
    adapter_state: str | None = None
    adapter_version: str | None = None
    readback_fields: list[str] = Field(default_factory=list)
    platform_fallback_boundaries: list[str] = Field(default_factory=list)
    media_readback: bool = False
    cover_readback: bool = False
    cover_receipt_present: bool = False
    final_publish_click_count: int = Field(default=0, ge=0)
