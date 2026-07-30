from __future__ import annotations

from typing import Any

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


class IpBroadcastAppRunCreateRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=200)
    input_payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str = Field(min_length=8, max_length=200)
    explicit_claim: bool = False
    context_snapshot_id: str | None = Field(default=None, min_length=1, max_length=200)


class IpBroadcastProviderRetryPlanRequest(BaseModel):
    root_cause: str = Field(min_length=1, max_length=500)
    retry_reason: str = Field(min_length=1, max_length=500)


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
    created_at: str
    updated_at: str
