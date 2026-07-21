"""Application-center domain models.

The models intentionally contain only business facts. Generic task rows and
provider credentials are kept out of these objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ContentProject:
    project_id: str
    schema_version: int
    name: str
    status: str
    primary_goal: str
    brand_id: str | None
    current_context_snapshot_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ContextSnapshot:
    context_snapshot_id: str
    project_id: str
    schema_version: int
    payload: dict[str, Any]
    source_brand_id: str | None
    source_brand_revision_id: str | None
    fingerprint: str
    created_at: str


@dataclass(frozen=True)
class AppRun:
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
    output_artifact_ids: list[str] = field(default_factory=list)
    error_code: str | None = None
    completed_at: str | None = None
    archived_at: str | None = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


@dataclass(frozen=True)
class RunAttempt:
    attempt_id: str
    app_run_id: str
    attempt_number: int
    task_id: str | None
    state: str
    context_snapshot_id: str | None
    error_code: str | None
    error_message: str | None
    diagnostic: dict[str, Any] | None
    model_ref: str | None
    provider_class: str | None
    input_units: int | None
    output_units: int | None
    estimated_cost_micros: int | None
    started_at: str | None
    completed_at: str | None
    duration_ms: int | None
    created_at: str


@dataclass(frozen=True)
class Artifact:
    artifact_id: str
    project_id: str
    source_app_run_id: str | None
    artifact_type: str
    name: str
    status: str
    current_version_id: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class ArtifactVersion:
    artifact_version_id: str
    artifact_id: str
    project_id: str
    version_number: int
    schema_version: int
    content: dict[str, Any] | None
    file_refs: list[dict[str, Any]]
    source: str
    content_fingerprint: str
    created_at: str


@dataclass(frozen=True)
class ArtifactHandoff:
    handoff_id: str
    project_id: str
    source_app_run_id: str | None
    source_artifact_id: str
    source_artifact_version_id: str
    target_app_id: str
    target_app_version: str
    target_run_id: str | None
    artifact_version_ids: list[str]
    mapping_version: int
    created_at: str
