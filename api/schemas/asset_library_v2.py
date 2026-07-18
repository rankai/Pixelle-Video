"""Stage-0 contracts for the enterprise asset library V2.

These models intentionally define the contract before any V2 endpoint is
enabled. Domain-specific resources (brand kits, templates and digital humans)
are indexed as LibraryItems but are not forced into a universal media table.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LibraryItemKind(StrEnum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    VOICE = "voice"
    DIGITAL_HUMAN = "digital_human"
    DIGITAL_HUMAN_SCENE = "digital_human_scene"
    TEMPLATE = "template"
    BRAND = "brand"


class MediaKind(StrEnum):
    VIDEO = "video"
    IMAGE = "image"
    AUDIO = "audio"
    FONT = "font"


class ResourceStatus(StrEnum):
    PROCESSING = "processing"
    READY = "ready"
    WARNING = "warning"
    FAILED = "failed"
    ARCHIVED = "archived"


class AssetVariantRole(StrEnum):
    POSTER = "poster"
    THUMBNAIL = "thumbnail"
    PREVIEW = "preview"
    PROXY = "proxy"
    WAVEFORM = "waveform"
    COVER_CROP = "cover_crop"


class UploadStatus(StrEnum):
    CREATED = "created"
    UPLOADING = "uploading"
    ANALYZING = "analyzing"
    READY = "ready"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LibraryItemContract(ContractModel):
    resource_id: str = Field(min_length=1)
    kind: LibraryItemKind
    name: str = Field(min_length=1)
    description: str = ""
    status: ResourceStatus
    cover_url: str | None = None
    tags: list[str] = Field(default_factory=list)
    favorite: bool = False
    created_at: str
    updated_at: str
    summary: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MediaAssetContract(ContractModel):
    asset_id: str = Field(min_length=1)
    legacy_id: str | None = None
    media_kind: MediaKind
    name: str = Field(min_length=1)
    description: str = ""
    source: str = Field(pattern="^(upload|recording|generated|system|imported)$")
    current_revision_id: str | None = None
    status: ResourceStatus
    created_at: str
    updated_at: str
    archived_at: str | None = None


class AssetRevisionContract(ContractModel):
    revision_id: str = Field(min_length=1)
    asset_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    parent_revision_id: str | None = None
    relative_path: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    bytes: int = Field(ge=0)
    sha256: str = Field(min_length=64, max_length=64)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    aspect_ratio: float | None = Field(default=None, gt=0)
    duration_ms: int | None = Field(default=None, ge=0)
    frame_rate: float | None = Field(default=None, gt=0)
    has_audio: bool | None = None
    has_transparency: bool | None = None
    created_at: str


class AssetVariantContract(ContractModel):
    variant_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    role: AssetVariantRole
    relative_path: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_ms: int | None = Field(default=None, ge=0)


class ResourceUsageContract(ContractModel):
    usage_id: str = Field(min_length=1)
    resource_kind: LibraryItemKind
    resource_id: str = Field(min_length=1)
    revision_id: str | None = None
    session_id: str = Field(min_length=1)
    step: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)
    created_at: str
    updated_at: str


class ResourceUsageCreateRequest(ContractModel):
    resource_kind: LibraryItemKind
    resource_id: str = Field(min_length=1)
    revision_id: str | None = None
    step: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)


class ResourceSnapshotContract(ContractModel):
    resource_kind: LibraryItemKind
    resource_id: str = Field(min_length=1)
    revision_id: str | None = None
    variant_id: str | None = None
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    resolved_relative_path: str | None = None
    template_revision: int | None = Field(default=None, ge=1)
    renderer_version: str | None = None


class UploadSessionContract(ContractModel):
    upload_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    declared_bytes: int = Field(ge=0)
    received_bytes: int = Field(ge=0)
    status: UploadStatus
    target_kind: LibraryItemKind
    error_code: str | None = None
    error_message: str | None = None


class UploadSessionCreateRequest(ContractModel):
    filename: str = Field(min_length=1)
    declared_bytes: int = Field(ge=0)
    target_kind: LibraryItemKind
    name: str | None = None
    description: str = ""
    deferred: bool = False
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=200)


class DeferredUploadFinalizeRequest(ContractModel):
    # A unique upload is finalized without asking the operator to choose a
    # duplicate policy.  The policy is required only when the server reports
    # an existing asset with the same SHA-256.
    duplicate_policy: str | None = Field(default=None, pattern="^(reuse_existing|attach_revision|create_separate)$")
    target_asset_id: str | None = Field(default=None, min_length=1)


class VoiceProfileCreateRequest(ContractModel):
    name: str = Field(min_length=1)
    audio_asset_id: str = Field(min_length=1)
    audio_revision_id: str | None = None
    language: str = ""
    style: str = ""
    authorization_status: str = "unknown"


class VoiceProfilePatchRequest(ContractModel):
    name: str | None = Field(default=None, min_length=1)
    audio_asset_id: str | None = None
    audio_revision_id: str | None = None
    language: str | None = None
    style: str | None = None
    authorization_status: str | None = None
    status: str | None = None


class MediaAssetPatchRequest(ContractModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None


class BrandKitV2Request(ContractModel):
    brand_id: str | None = None
    brand_name: str = "未命名品牌"
    logo_asset_id: str | None = None
    default_bgm_asset_id: str | None = None
    primary_color: str = "#1f6feb"
    secondary_color: str = "#0f766e"
    font_family: str = ""
    default_subtitle_style: str = ""
    ending_card_text: str = ""
    store_address: str = ""
    phone: str = ""
    coupon_phrase: str = ""


class DigitalHumanV2Request(ContractModel):
    profile_id: str | None = None
    name: str = "未命名数字人"
    provider: str = "custom"
    poster_asset_id: str | None = None
    gender: str | None = None
    style: str | None = None
    posture: str | None = None
    supported_workflows: list[str] = Field(default_factory=list)
    scene_name: str = "默认场景"
    source_asset_id: str | None = None
    source_revision_id: str | None = None
    shot_size: str = "medium"
    location: str = ""
    outfit: str = ""


class DigitalHumanPatchRequest(ContractModel):
    name: str | None = Field(default=None, min_length=1)
    provider: str | None = None
    poster_asset_id: str | None = None
    gender: str | None = None
    style: str | None = None
    posture: str | None = None
    supported_workflows: list[str] | None = None
    default_scene_id: str | None = None
    quality_state: str | None = None
    status: str | None = None


class DigitalHumanSceneV2Request(ContractModel):
    name: str = "默认场景"
    source_asset_id: str | None = None
    source_revision_id: str | None = None
    shot_size: str = "medium"
    location: str = ""
    outfit: str = ""
    posture: str = ""


class DigitalHumanScenePatchRequest(ContractModel):
    name: str | None = Field(default=None, min_length=1)
    source_asset_id: str | None = None
    source_revision_id: str | None = None
    shot_size: str | None = None
    location: str | None = None
    outfit: str | None = None
    posture: str | None = None
    status: str | None = Field(default=None, pattern="^(ready|archived)$")


class DigitalHumanSceneReorderRequest(ContractModel):
    scene_ids: list[str] = Field(min_length=1)


class TemplatePatchRequest(ContractModel):
    display_name: str | None = Field(default=None, min_length=1)
    short_description: str | None = None
    full_description: str | None = None
    preview_url: str | None = None
    schema_version: int | None = Field(default=None, ge=1)
    renderer_version: str | None = None
    cover_contract: dict[str, Any] | None = None
    subtitle_contract: dict[str, Any] | None = None
    layout_contract: dict[str, Any] | None = None
    status: str | None = None


class TemplateV2Request(ContractModel):
    template_id: str | None = None
    display_name: str = "未命名模板"
    short_description: str = ""
    full_description: str = ""
    preview_url: str | None = None
    schema_version: int = 1
    renderer_version: str = "ip-broadcast-composer-v2"
    cover_contract: dict[str, Any] = Field(default_factory=dict)
    subtitle_contract: dict[str, Any] = Field(default_factory=dict)
    layout_contract: dict[str, Any] | None = None


class TemplatePreviewRequest(ContractModel):
    draft_contract: dict[str, Any]
    sample: dict[str, Any] = Field(default_factory=dict)


class ResourceTagsRequest(ContractModel):
    tags: list[str] = Field(default_factory=list)


class FavoriteRequest(ContractModel):
    favorite: bool


class CollectionCreateRequest(ContractModel):
    name: str = Field(min_length=1)
    description: str = ""


class CollectionPatchRequest(ContractModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None


class RevisionActivateRequest(ContractModel):
    revision_id: str = Field(min_length=1)


class BulkResourceRef(ContractModel):
    kind: LibraryItemKind
    resource_id: str = Field(min_length=1)


class BulkActionRequest(ContractModel):
    action: str = Field(pattern="^(archive|restore|favorite|unfavorite|tag|untag)$")
    items: list[BulkResourceRef] = Field(min_length=1, max_length=500)
    tags: list[str] = Field(default_factory=list)


class ResourceReferenceInput(ContractModel):
    resource_kind: LibraryItemKind
    resource_id: str = Field(min_length=1)
    revision_id: str | None = None
    step: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)


class SessionReconcileRequest(ContractModel):
    references: list[ResourceReferenceInput] = Field(default_factory=list, max_length=500)


class MigrationManifestBaseline(ContractModel):
    resource_kind: str = Field(min_length=1)
    relative_path: str = Field(min_length=1)
    exists: bool
    sha256: str | None = Field(default=None, min_length=64, max_length=64)
    record_count: int = Field(ge=0)
    legacy_ids: list[str] = Field(default_factory=list)
    referenced_files: list[str] = Field(default_factory=list)
    error: str | None = None


class AssetMigrationReport(ContractModel):
    schema_version: str = Field(min_length=1)
    generated_at: str
    data_root_name: str
    manifests: list[MigrationManifestBaseline] = Field(default_factory=list)
    missing_files: list[str] = Field(default_factory=list)
    rollback: dict[str, Any] = Field(default_factory=dict)
