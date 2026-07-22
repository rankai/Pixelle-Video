"""UX-0 contracts for the SMB asset-center gate.

These contracts are deliberately kept separate from the already shipped V2
media/domain models.  UX-0 defines the boundaries that the next UI may rely
on; it does not enable that UI or silently widen an existing endpoint.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from api.schemas.asset_library_v2 import ContractModel, ResourceStatus
from pixelle_video.services.font_registry import validate_registered_font

SHA256 = str


class AssetViewKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    DIGITAL_HUMAN = "digital_human"
    TEMPLATE = "template"
    BRAND = "brand"


class AssetViewModelContract(ContractModel):
    """Stable fields shared by the seven typed UI projections."""

    resource_id: str = Field(min_length=1)
    kind: AssetViewKind
    name: str = Field(min_length=1)
    description: str = ""
    status: ResourceStatus
    cover_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False
    last_used_at: str | None = None
    display: dict[str, Any] = Field(default_factory=dict)
    capabilities: list[str] = Field(default_factory=list)


class PickerContextContract(ContractModel):
    session_id: str = Field(min_length=1)
    step: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)
    allowed_kinds: list[AssetViewKind] = Field(min_length=1)
    aspect_ratio: float | None = Field(default=None, gt=0)
    max_duration_ms: int | None = Field(default=None, ge=0)
    required_capabilities: list[str] = Field(default_factory=list)
    selection_mode: Literal["single", "multiple"] = "single"


class TemplateFontIdentity(ContractModel):
    token: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9_]*$")
    font_id: str = Field(min_length=1)
    family: str = Field(min_length=1)
    weight: int = Field(ge=100, le=900)
    style: Literal["normal", "italic"] = "normal"
    font_sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class TemplateCanvas(ContractModel):
    width: int = Field(ge=1)
    height: int = Field(ge=1)


class TemplateSafeArea(ContractModel):
    top: int = Field(ge=0)
    right: int = Field(ge=0)
    bottom: int = Field(ge=0)
    left: int = Field(ge=0)


class TemplateTextBox(ContractModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    font_token: str = Field(min_length=1)
    font_size: int = Field(gt=0)
    line_height: float = Field(gt=0)
    max_lines: int = Field(ge=1, le=20)
    align: Literal["left", "center", "right"] = "left"
    vertical_align: Literal["top", "middle", "bottom"] = "top"
    overflow: Literal["shrink", "clip", "reject"] = "shrink"


class TemplateCoverContract(ContractModel):
    title: TemplateTextBox
    subtitle: TemplateTextBox
    safe_area: TemplateSafeArea


class TemplateVideoSubtitleContract(ContractModel):
    font_token: str = Field(min_length=1)
    font_size: int = Field(gt=0)
    alignment: int = Field(ge=1, le=9)
    margin_l: int = Field(ge=0)
    margin_r: int = Field(ge=0)
    margin_v: int = Field(ge=0)
    outline: int = Field(ge=0)
    shadow: int = Field(ge=0)
    max_lines: int = Field(ge=1, le=20)
    safe_area: TemplateSafeArea


class TemplateLayoutContract(ContractModel):
    schema_version: Literal[2]
    canvas: TemplateCanvas
    base_template_id: str = Field(min_length=1)
    fonts: list[TemplateFontIdentity] = Field(min_length=1)
    cover: TemplateCoverContract
    video_subtitle: TemplateVideoSubtitleContract

    @model_validator(mode="after")
    def validate_layout(self) -> "TemplateLayoutContract":
        for font in self.fonts:
            validate_registered_font(font.font_id, font.family, font.weight, font.style, font.font_sha256)
        font_tokens = {font.token for font in self.fonts}
        referenced_tokens = {
            self.cover.title.font_token,
            self.cover.subtitle.font_token,
            self.video_subtitle.font_token,
        }
        missing = sorted(referenced_tokens - font_tokens)
        if missing:
            raise ValueError(f"font_token_not_registered:{','.join(missing)}")

        boxes = (self.cover.title, self.cover.subtitle)
        for box in boxes:
            if box.x + box.width > self.canvas.width or box.y + box.height > self.canvas.height:
                raise ValueError("layout_box_outside_canvas")
        safe_areas = (self.cover.safe_area, self.video_subtitle.safe_area)
        for safe_area in safe_areas:
            if safe_area.left + safe_area.right >= self.canvas.width:
                raise ValueError("safe_area_horizontal_empty")
            if safe_area.top + safe_area.bottom >= self.canvas.height:
                raise ValueError("safe_area_vertical_empty")
        return self


class VoiceProfileStatus(StrEnum):
    READY = "ready"
    PROCESSING = "processing"
    ARCHIVED = "archived"


class VoiceProfile(ContractModel):
    """A domain voice that points at an immutable audio revision."""

    voice_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    audio_asset_id: str = Field(min_length=1)
    audio_revision_id: str = Field(min_length=1)
    legacy_reference_id: str | None = Field(default=None, min_length=1)
    language: str = ""
    style: str = ""
    authorization_status: Literal["unknown", "authorized", "restricted"] = "unknown"
    status: VoiceProfileStatus = VoiceProfileStatus.READY
    created_at: str
    updated_at: str


class VoiceProfileCreateRequest(ContractModel):
    voice_id: str | None = Field(default=None, min_length=1)
    name: str = Field(min_length=1)
    audio_asset_id: str = Field(min_length=1)
    audio_revision_id: str = Field(min_length=1)
    legacy_reference_id: str | None = Field(default=None, min_length=1)
    language: str = ""
    style: str = ""
    authorization_status: Literal["unknown", "authorized", "restricted"] = "unknown"


class DuplicatePolicy(StrEnum):
    REUSE_EXISTING = "reuse_existing"
    ATTACH_REVISION = "attach_revision"
    CREATE_SEPARATE = "create_separate"


class DeferredUploadStatus(StrEnum):
    CREATED = "created"
    UPLOADING = "uploading"
    ANALYZING = "analyzing"
    UPLOADED = "uploaded"
    AWAITING_DUPLICATE_DECISION = "awaiting_duplicate_decision"
    FINALIZED = "finalized"
    EXPIRED = "expired"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DeferredUploadCreateRequest(ContractModel):
    filename: str = Field(min_length=1)
    declared_bytes: int = Field(ge=0)
    target_kind: Literal["image", "video", "audio"]
    name: str | None = None
    description: str = ""
    decision_mode: Literal["deferred"] = "deferred"
    idempotency_key: str = Field(min_length=1)


class FinalizeUploadRequest(ContractModel):
    duplicate_policy: DuplicatePolicy | None = None
    target_asset_id: str | None = None

    @model_validator(mode="after")
    def validate_policy_target(self) -> "FinalizeUploadRequest":
        if self.duplicate_policy is DuplicatePolicy.ATTACH_REVISION and not self.target_asset_id:
            raise ValueError("target_asset_id_required_for_attach_revision")
        if self.duplicate_policy is not DuplicatePolicy.ATTACH_REVISION and self.target_asset_id:
            raise ValueError("target_asset_id_only_allowed_for_attach_revision")
        return self


class DeferredUploadResponse(ContractModel):
    upload_id: str = Field(min_length=1)
    status: DeferredUploadStatus
    filename: str = Field(min_length=1)
    declared_bytes: int = Field(ge=0)
    received_bytes: int = Field(ge=0)
    sha256: SHA256 | None = Field(default=None, min_length=64, max_length=64)
    duplicate_asset_id: str | None = None
    asset_id: str | None = None
    revision_id: str | None = None
    expires_at: str | None = None
    result_key: str | None = None


class CursorSort(StrEnum):
    RECENT = "recent"
    UPDATED = "updated"
    NAME = "name"


class CursorEnvelope(ContractModel):
    version: Literal[1] = 1
    sort: CursorSort
    filter_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    index_generation: int = Field(ge=1)
    last_tuple: list[str | int | float | None] = Field(min_length=1, max_length=8)
    signature: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")


class LibraryQueryFacets(ContractModel):
    generation: int = Field(ge=1)
    kinds: dict[str, int] = Field(default_factory=dict)
    statuses: dict[str, int] = Field(default_factory=dict)
    tags: dict[str, int] = Field(default_factory=dict)


class LibraryPageContract(ContractModel):
    items: list[AssetViewModelContract] = Field(default_factory=list)
    total: int = Field(ge=0)
    next_cursor: str | None = None
    index_generation: int = Field(ge=1)
    filter_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    facets: LibraryQueryFacets


class CursorErrorResponse(ContractModel):
    error_code: Literal["cursor_stale", "cursor_filter_mismatch", "cursor_invalid"]
    message: str = Field(min_length=1)


__all__ = [
    "AssetViewKind",
    "AssetViewModelContract",
    "PickerContextContract",
    "TemplateFontIdentity",
    "TemplateLayoutContract",
    "VoiceProfile",
    "VoiceProfileCreateRequest",
    "VoiceProfileStatus",
    "DuplicatePolicy",
    "DeferredUploadStatus",
    "DeferredUploadCreateRequest",
    "FinalizeUploadRequest",
    "DeferredUploadResponse",
    "CursorSort",
    "CursorEnvelope",
    "LibraryQueryFacets",
    "LibraryPageContract",
    "CursorErrorResponse",
]
