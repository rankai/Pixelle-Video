from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ContentProjectCreateRequest(_StrictRequest):
    name: str = Field(min_length=1, max_length=200)
    primary_goal: str = Field(min_length=1, max_length=1000)
    brand_id: str | None = None
    expected_brand_domain_revision: int | None = Field(default=None, ge=1)
    project_overrides: dict[str, Any] = Field(default_factory=dict)
    project_brief: dict[str, Any] | None = None


class ContentProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    primary_goal: str | None = Field(default=None, min_length=1, max_length=1000)


class ContentProjectResponse(BaseModel):
    project_id: str
    schema_version: int
    name: str
    status: str
    primary_goal: str
    brand_id: str | None
    current_context_snapshot_id: str | None
    created_at: str
    updated_at: str


class ContextSnapshotCreateRequest(_StrictRequest):
    schema_version: int = Field(default=1, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_brand_id: str | None = None
    source_brand_revision_id: str | None = None


class ProjectBrandBindingRequest(_StrictRequest):
    brand_id: str | None
    expected_context_snapshot_id: str | None
    expected_domain_revision: int | None = Field(default=None, ge=1)
    project_overrides: dict[str, Any] = Field(default_factory=dict)


class ProjectBrandSyncRequest(_StrictRequest):
    expected_context_snapshot_id: str | None
    idempotency_key: str = Field(min_length=8, max_length=200)


class ProjectMaterialUpdateRequest(_StrictRequest):
    expected_context_snapshot_id: str
    project_brief: dict[str, Any]
    project_overrides: dict[str, Any] = Field(default_factory=dict)


class ArtifactVersionCreateRequest(BaseModel):
    content: dict[str, Any] | None = None
    file_refs: list[dict[str, Any]] = Field(default_factory=list)
    source: str = Field(default="generated", pattern="^(generated|edited|imported|rendered)$")
    schema_version: int = Field(default=1, ge=1)


class ArtifactCreateRequest(BaseModel):
    artifact_type: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    source_app_run_id: str | None = None


class CarouselPageRetryRequest(BaseModel):
    text: str = Field(min_length=1, max_length=480)
    asset_refs: list[str] = Field(min_length=1, max_length=20)
    font_id: str = Field(default="noto-sans-sc-bold", min_length=1, max_length=100)


class ArtifactHandoffCreateRequest(BaseModel):
    project_id: str
    source_artifact_id: str
    source_artifact_version_id: str
    target_app_id: str
    target_app_version: str
    artifact_version_ids: list[str] = Field(default_factory=list)
    source_app_run_id: str | None = None
    target_run_id: str | None = None
    mapping_version: int = Field(default=1, ge=1)


class AppRunCreateRequest(BaseModel):
    project_id: str
    app_id: str
    app_version: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=200)
    context_snapshot_id: str | None = None
    prompt_version: str | None = None
    session_id: str | None = None


class AppRunTransitionRequest(BaseModel):
    state: str
    expected_state_version: int | None = None


class AppRunDraftUpdateRequest(BaseModel):
    input_payload: dict[str, Any] | None = None
    context_snapshot_id: str | None = None
    prompt_version: str | None = None
    session_id: str | None = None


class AppEventCreateRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class AppRunExecutionAccepted(BaseModel):
    app_run_id: str
    task_id: str
    state: str


class AppRunResponse(BaseModel):
    app_run_id: str
    project_id: str
    app_id: str
    app_version: str
    state: str
    state_version: int
    idempotency_key: str
    input_schema_version: int
    input_payload: dict[str, Any]
    context_snapshot_id: str | None
    prompt_version: str | None
    session_id: str | None
    output_artifact_ids: list[str]
    error_code: str | None
    completed_at: str | None
    archived_at: str | None
    created_at: str
    updated_at: str


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResultCompatibilityResponse(_StrictResponse):
    state: Literal["normal", "legacy_unavailable"]
    unavailable_reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        exclude_if=lambda value: value is None,
    )


class CopyResultItemResponse(_StrictResponse):
    item_id: str
    kind: Literal["copy"]
    label: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
        exclude_if=lambda value: value is None,
    )
    text: str = Field(min_length=1, max_length=5000)
    actions: list[Literal["copy", "select", "edit"]] = Field(min_length=1, max_length=3)


class TitleResultItemResponse(_StrictResponse):
    item_id: str
    kind: Literal["title"]
    label: str | None = Field(
        default=None,
        min_length=1,
        max_length=30,
        exclude_if=lambda value: value is None,
    )
    text: str = Field(min_length=1, max_length=200)
    actions: list[Literal["copy", "select", "edit"]] = Field(min_length=1, max_length=3)
    selected: bool = False


class CarouselResultItemResponse(_StrictResponse):
    item_id: str
    kind: Literal["carousel"]
    title: str = Field(min_length=1, max_length=80)
    cover_url: str
    preview_url: str
    download_url: str
    page_count: int = Field(ge=1, le=100)
    missing_facts: list[str] = Field(default_factory=list, max_length=20)
    actions: list[Literal["preview", "publish"]] = Field(min_length=1, max_length=2)
    details_available: list[Literal["pages", "publish_copy"]] = Field(
        default_factory=list, max_length=4
    )
    artifact_version_ids: list[str] = Field(min_length=1, max_length=8)


class VideoResultItemResponse(_StrictResponse):
    item_id: str
    kind: Literal["video"]
    title: str = Field(min_length=1, max_length=80)
    poster_url: str
    playback_url: str
    preview_url: str
    download_url: str
    duration_seconds: float = Field(gt=0, le=3600)
    digital_human_name: str = Field(min_length=1, max_length=200)
    voice_name: str = Field(min_length=1, max_length=200)
    actions: list[Literal["play", "publish"]] = Field(min_length=1, max_length=2)
    details_available: list[Literal["cover", "publish_copy", "spoken_script", "download"]] = Field(
        default_factory=list, max_length=4
    )
    artifact_version_ids: list[str] = Field(min_length=2, max_length=8)


GenerationRecordItemResponse = (
    CopyResultItemResponse
    | TitleResultItemResponse
    | CarouselResultItemResponse
    | VideoResultItemResponse
)


class GenerationRecordBlockResponse(_StrictResponse):
    schema_version: Literal[1] = 1
    record_id: str
    app_run_id: str
    project_id: str
    app_id: Literal[
        "builtin.marketing-copy",
        "builtin.viral-titles",
        "builtin.douyin-carousel",
        "builtin.digital-human-video",
    ]
    app_name: str = Field(min_length=1, max_length=40)
    result_shape: Literal["multi_copy", "multi_title", "single_carousel", "single_video"]
    status: Literal["queued", "running", "needs_review", "completed", "failed", "cancelled"]
    created_at: str
    result_available_at: str | None
    summary: str = Field(min_length=1, max_length=120)
    compatibility: ResultCompatibilityResponse
    items: list[GenerationRecordItemResponse]


class GenerationRecordPageResponse(_StrictResponse):
    schema_version: Literal[1] = 1
    project_id: str
    scope: Literal["current_app", "all_results"]
    app_id: (
        Literal[
            "builtin.marketing-copy",
            "builtin.viral-titles",
            "builtin.douyin-carousel",
            "builtin.digital-human-video",
        ]
        | None
    )
    records: list[GenerationRecordBlockResponse] = Field(max_length=20)
    next_cursor: str | None


class GenerationPublishCopyResponse(_StrictResponse):
    title: str = Field(max_length=80)
    description: str = Field(max_length=2000)
    hashtags: list[str] = Field(default_factory=list, max_length=20)


class GenerationCarouselPageResponse(_StrictResponse):
    page_index: int = Field(ge=1, le=100)
    image_url: str
    download_url: str


class GenerationCarouselPreviewResponse(_StrictResponse):
    schema_version: Literal[1] = 1
    kind: Literal["carousel"]
    record_id: str
    title: str = Field(min_length=1, max_length=80)
    page_count: int = Field(ge=1, le=100)
    pages: list[GenerationCarouselPageResponse] = Field(min_length=1, max_length=100)
    publish_copy: GenerationPublishCopyResponse | None
    download_url: str


class GenerationVideoPreviewResponse(_StrictResponse):
    schema_version: Literal[1] = 1
    kind: Literal["video"]
    record_id: str
    title: str = Field(min_length=1, max_length=80)
    duration_seconds: float = Field(gt=0, le=3600)
    poster_url: str
    playback_url: str
    download_url: str
    publish_copy: GenerationPublishCopyResponse | None


GenerationMediaPreviewResponse = GenerationCarouselPreviewResponse | GenerationVideoPreviewResponse


class IpBroadcastAppRunCreateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=200)
    explicit_claim: bool = False
    context_snapshot_id: str | None = Field(default=None, min_length=1, max_length=200)


class IpBroadcastSpokenScriptPrepareRequest(_StrictRequest):
    project_id: str = Field(min_length=1, max_length=200)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    context_snapshot_id: str | None = Field(default=None, min_length=1, max_length=200)


class IpBroadcastSpokenScriptPrepareResponse(_StrictResponse):
    schema_version: Literal[1] = 1
    spoken_script: str = Field(min_length=1, max_length=2000)
    source_revision: str = Field(min_length=1, max_length=200)


class IpBroadcastProviderRetryPlanRequest(BaseModel):
    root_cause: str = Field(min_length=1, max_length=500)
    retry_reason: str = Field(min_length=1, max_length=500)


class IpBroadcastResultPresentation(_StrictResponse):
    digital_human_name: str = Field(min_length=1, max_length=200)
    voice_name: str = Field(min_length=1, max_length=200)


class IpBroadcastAppRunResponse(BaseModel):
    app_run_id: str
    project_id: str
    context_snapshot_id: str | None = None
    app_id: str
    app_version: str
    state: str
    state_version: int
    session_id: str
    output_artifact_ids: list[str] = Field(default_factory=list)
    error_code: str | None = None
    source_revision: str
    explicit_claim: bool
    projection: dict[str, Any]
    step_status: dict[int, str]
    notices: dict[int, dict[str, str]]
    artifact_keys: list[str]
    artifact_details: dict[str, Any] = Field(default_factory=dict)
    presentation: IpBroadcastResultPresentation
    created_at: str
    updated_at: str
