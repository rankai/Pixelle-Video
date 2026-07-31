"""SQLite repository for ContentProject, AppRun and creative artifacts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .llm_port import AppLLMPortError
from .migration import migrate_app_center
from .models import (
    AppEvent,
    AppRun,
    Artifact,
    ArtifactHandoff,
    ArtifactVersion,
    ContentProject,
    ContextSnapshot,
    RunAttempt,
)
from .project_context import ProjectContextError, validate_context_snapshot
from .registry import BUILTIN_MANIFESTS, get_app
from .state_machine import validate_transition
from .validation import find_forbidden_business_field, validate_business_payload


class AppCenterRepositoryError(RuntimeError):
    """Base repository error."""


class IdempotencyConflict(AppCenterRepositoryError):
    pass


class NotFound(AppCenterRepositoryError):
    pass


class ConcurrentWrite(AppCenterRepositoryError):
    pass


KNOWN_ARTIFACT_TYPES = frozenset(
    {"brief"}
    | {
        artifact_type
        for manifest in BUILTIN_MANIFESTS
        for artifact_type in manifest.get("accepted_artifact_types", [])
    }
    | {
        artifact_type
        for manifest in BUILTIN_MANIFESTS
        for artifact_type in manifest.get("produced_artifact_types", [])
    }
    | {"publish_package_ref"}
)

WORKBENCH_EVENT_TYPES = frozenset(
    {
        "result.copied",
        "result.edited",
        "result.selected",
        "result.liked",
        "result.disliked",
        "handoff.started",
        "handoff.completed",
    }
)
WORKBENCH_EVENT_PAYLOAD_KEYS = frozenset(
    {
        "artifact_id",
        "artifact_version_id",
        "item_index",
        "target_app_id",
        "summary",
    }
)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any):
    if not value:
        return default
    return json.loads(value)


def _fingerprint(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_dump(value).encode("utf-8")).hexdigest()


class AppCenterRepository:
    def __init__(self, db_path: str | Path | None = None, *, asset_repository: Any | None = None):
        self.db_path = migrate_app_center(db_path)
        self._asset_repository = asset_repository

    def set_asset_repository(self, asset_repository: Any) -> None:
        self._asset_repository = asset_repository

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_project(
        self, name: str, primary_goal: str, brand_id: str | None = None
    ) -> ContentProject:
        project_id = _id("project")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO content_projects(project_id, schema_version, name, status, primary_goal, brand_id, created_at, updated_at) VALUES (?, 1, ?, 'active', ?, ?, ?, ?)",
                (project_id, name, primary_goal, brand_id, now, now),
            )
        return self.get_project(project_id)

    def create_project_with_context(
        self,
        name: str,
        primary_goal: str,
        *,
        brand_id: str,
        payload: dict[str, Any],
        source_brand_revision_id: str,
    ) -> tuple[ContentProject, ContextSnapshot]:
        """Create a brand-bound project and its first v3 snapshot atomically."""

        project_id = _id("project")
        self.validate_server_context_snapshot(project_id, payload)
        snapshot_id = _id("context")
        now = _now()
        fingerprint = _fingerprint(
            {
                "schema_version": 3,
                "payload": payload,
                "source_brand_id": brand_id,
                "source_brand_revision_id": source_brand_revision_id,
            }
        )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO content_projects(
                    project_id, schema_version, name, status, primary_goal,
                    brand_id, created_at, updated_at
                ) VALUES (?, 1, ?, 'active', ?, ?, ?, ?)
                """,
                (
                    project_id,
                    name,
                    primary_goal,
                    brand_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """
                INSERT INTO context_snapshots(
                    context_snapshot_id, project_id, schema_version, payload_json,
                    source_brand_id, source_brand_revision_id, fingerprint, created_at
                ) VALUES (?, ?, 3, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    project_id,
                    _dump(payload),
                    brand_id,
                    source_brand_revision_id,
                    fingerprint,
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE content_projects
                SET current_context_snapshot_id = ?
                WHERE project_id = ?
                """,
                (snapshot_id, project_id),
            )
        return self.get_project(project_id), self.get_context_snapshot(snapshot_id)

    def replace_project_brand_binding(
        self,
        project_id: str,
        *,
        brand_id: str | None,
        payload: dict[str, Any],
        source_brand_revision_id: str | None,
        expected_context_snapshot_id: str | None,
        primary_goal: str | None = None,
    ) -> tuple[ContentProject, ContextSnapshot]:
        """Explicitly bind, change, or remove a project's brand.

        The old snapshot remains immutable. The project pointer, brand binding,
        and replacement snapshot move together in one SQLite transaction.
        """

        self.validate_server_context_snapshot(project_id, payload)
        snapshot_id = _id("context")
        now = _now()
        fingerprint = _fingerprint(
            {
                "schema_version": 3,
                "payload": payload,
                "source_brand_id": brand_id,
                "source_brand_revision_id": source_brand_revision_id,
            }
        )
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status, current_context_snapshot_id FROM content_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if row is None:
                raise NotFound(f"project not found: {project_id}")
            if row["status"] == "archived":
                raise ProjectContextError(
                    "PROJECT_ARCHIVED",
                    "archived projects cannot change brand binding",
                )
            if row["current_context_snapshot_id"] != expected_context_snapshot_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CONFLICT",
                    "project context changed; reload before replacing brand binding",
                )
            conn.execute(
                """
                INSERT INTO context_snapshots(
                    context_snapshot_id, project_id, schema_version, payload_json,
                    source_brand_id, source_brand_revision_id, fingerprint, created_at
                ) VALUES (?, ?, 3, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    project_id,
                    _dump(payload),
                    brand_id,
                    source_brand_revision_id,
                    fingerprint,
                    now,
                ),
            )
            updated = conn.execute(
                """
                UPDATE content_projects
                SET brand_id = ?, current_context_snapshot_id = ?,
                    primary_goal = COALESCE(?, primary_goal), updated_at = ?
                WHERE project_id = ?
                """,
                (brand_id, snapshot_id, primary_goal, now, project_id),
            ).rowcount
            if updated != 1:  # pragma: no cover - protected by the transaction
                raise ConcurrentWrite(f"project update failed: {project_id}")
        return self.get_project(project_id), self.get_context_snapshot(snapshot_id)

    def get_brand_sync_result(
        self,
        project_id: str,
        idempotency_key: str,
        *,
        request_fingerprint: str,
    ) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT request_fingerprint, response_json
                FROM brand_sync_requests
                WHERE project_id = ? AND idempotency_key = ?
                """,
                (project_id, idempotency_key),
            ).fetchone()
        if row is None:
            return None
        if row["request_fingerprint"] != request_fingerprint:
            raise IdempotencyConflict(f"brand sync idempotency key already used: {idempotency_key}")
        response = _load(row["response_json"], {})
        if not isinstance(response, dict):
            raise AppCenterRepositoryError("brand sync response is invalid")
        return response

    def commit_brand_sync(
        self,
        project_id: str,
        *,
        brand_id: str,
        expected_context_snapshot_id: str | None,
        payload: dict[str, Any],
        source_brand_revision_id: str,
        idempotency_key: str,
        request_fingerprint: str,
        changes: list[dict[str, Any]],
        has_changes: bool,
    ) -> dict[str, Any]:
        """Persist one explicit sync in a single AppDB transaction."""

        self.validate_server_context_snapshot(project_id, payload)
        snapshot_id = _id("context") if has_changes else None
        now = _now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                """
                SELECT request_fingerprint, response_json
                FROM brand_sync_requests
                WHERE project_id = ? AND idempotency_key = ?
                """,
                (project_id, idempotency_key),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != request_fingerprint:
                    raise IdempotencyConflict(
                        f"brand sync idempotency key already used: {idempotency_key}"
                    )
                response = _load(existing["response_json"], {})
                if not isinstance(response, dict):
                    raise AppCenterRepositoryError("brand sync response is invalid")
                return response
            row = conn.execute(
                """
                SELECT status, brand_id, current_context_snapshot_id
                FROM content_projects
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
            if row is None:
                raise NotFound(f"project not found: {project_id}")
            if row["status"] == "archived":
                raise ProjectContextError(
                    "PROJECT_ARCHIVED",
                    "archived projects cannot sync brand context",
                )
            if row["brand_id"] != brand_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CONFLICT",
                    "project brand binding changed; reload before syncing",
                )
            if row["current_context_snapshot_id"] != expected_context_snapshot_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CONFLICT",
                    "project context changed; reload before syncing",
                )
            result_code = (
                "PROJECT_BRAND_SYNC_APPLIED" if has_changes else "PROJECT_BRAND_SYNC_NO_CHANGE"
            )
            if snapshot_id is not None:
                fingerprint = _fingerprint(
                    {
                        "schema_version": 3,
                        "payload": payload,
                        "source_brand_id": brand_id,
                        "source_brand_revision_id": source_brand_revision_id,
                    }
                )
                conn.execute(
                    """
                    INSERT INTO context_snapshots(
                        context_snapshot_id, project_id, schema_version, payload_json,
                        source_brand_id, source_brand_revision_id, fingerprint, created_at
                    ) VALUES (?, ?, 3, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        project_id,
                        _dump(payload),
                        brand_id,
                        source_brand_revision_id,
                        fingerprint,
                        now,
                    ),
                )
                updated = conn.execute(
                    """
                    UPDATE content_projects
                    SET current_context_snapshot_id = ?, updated_at = ?
                    WHERE project_id = ?
                    """,
                    (snapshot_id, now, project_id),
                ).rowcount
                if updated != 1:  # pragma: no cover - protected by transaction
                    raise ConcurrentWrite(f"project update failed: {project_id}")
            response = {
                "project_id": project_id,
                "result_code": result_code,
                "changes_committed": has_changes,
                "context_snapshot_id": snapshot_id or expected_context_snapshot_id,
                "changes": deepcopy(changes),
            }
            conn.execute(
                """
                INSERT INTO brand_sync_requests(
                    project_id, idempotency_key, request_fingerprint,
                    result_code, changes_committed, context_snapshot_id,
                    response_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    idempotency_key,
                    request_fingerprint,
                    result_code,
                    int(has_changes),
                    snapshot_id,
                    _dump(response),
                    now,
                ),
            )
        return response

    def validate_server_context_snapshot(self, project_id: str, payload: dict[str, Any]) -> None:
        self.validate_context_snapshot_payload(project_id, payload, schema_version=3)

    def validate_context_snapshot_payload(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        schema_version: int,
    ) -> None:
        validate_context_snapshot(
            payload,
            schema_version=schema_version,
            project_id=project_id,
            artifact_version_resolver=self._resolve_artifact_version,
            asset_revision_resolver=self._resolve_asset_revision,
        )

    def get_project(self, project_id: str) -> ContentProject:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM content_projects WHERE project_id = ?", (project_id,)
            ).fetchone()
        if not row:
            raise NotFound(f"project not found: {project_id}")
        return ContentProject(**dict(row))

    def list_projects(self, include_archived: bool = False) -> list[ContentProject]:
        query = "SELECT * FROM content_projects"
        params: tuple[Any, ...] = ()
        if not include_archived:
            query += " WHERE status = 'active'"
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [ContentProject(**dict(row)) for row in rows]

    def archive_project(self, project_id: str) -> ContentProject:
        now = _now()
        with self._connect() as conn:
            updated = conn.execute(
                "UPDATE content_projects SET status = 'archived', updated_at = ? WHERE project_id = ? AND status <> 'archived'",
                (now, project_id),
            ).rowcount
        if not updated:
            self.get_project(project_id)
        return self.get_project(project_id)

    def update_project(
        self, project_id: str, *, name: str | None = None, primary_goal: str | None = None
    ) -> ContentProject:
        current = self.get_project(project_id)
        next_name = current.name if name is None else name
        next_goal = current.primary_goal if primary_goal is None else primary_goal
        if not next_name.strip() or not next_goal.strip():
            raise ValueError("project name and primary goal cannot be empty")
        with self._connect() as conn:
            conn.execute(
                "UPDATE content_projects SET name = ?, primary_goal = ?, updated_at = ? WHERE project_id = ?",
                (next_name, next_goal, _now(), project_id),
            )
        return self.get_project(project_id)

    def save_context_snapshot(
        self,
        project_id: str,
        payload: dict[str, Any],
        *,
        schema_version: int = 1,
        source_brand_id: str | None = None,
        source_brand_revision_id: str | None = None,
    ) -> ContextSnapshot:
        project = self.get_project(project_id)
        self._validate_legacy_source_brand(
            project,
            payload,
            schema_version=schema_version,
            source_brand_id=source_brand_id,
            source_brand_revision_id=source_brand_revision_id,
        )
        validate_context_snapshot(
            payload,
            schema_version=schema_version,
            project_id=project_id,
            artifact_version_resolver=self._resolve_artifact_version,
            asset_revision_resolver=self._resolve_asset_revision,
        )
        snapshot_id = _id("context")
        now = _now()
        fingerprint = _fingerprint(
            {
                "schema_version": schema_version,
                "payload": payload,
                "source_brand_id": source_brand_id,
                "source_brand_revision_id": source_brand_revision_id,
            }
        )
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO context_snapshots(context_snapshot_id, project_id, schema_version, payload_json, source_brand_id, source_brand_revision_id, fingerprint, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    project_id,
                    schema_version,
                    _dump(payload),
                    source_brand_id,
                    source_brand_revision_id,
                    fingerprint,
                    now,
                ),
            )
            conn.execute(
                "UPDATE content_projects SET current_context_snapshot_id = ?, updated_at = ? WHERE project_id = ?",
                (snapshot_id, now, project_id),
            )
        return self.get_context_snapshot(snapshot_id)

    def _validate_legacy_source_brand(
        self,
        project: ContentProject,
        payload: dict[str, Any],
        *,
        schema_version: int,
        source_brand_id: str | None,
        source_brand_revision_id: str | None,
    ) -> None:
        """Preserve trusted v1/v2 source columns while rejecting forgery."""

        from .brand_project import validate_brand_domain_revision

        source_pair = (source_brand_id, source_brand_revision_id)
        if (source_brand_id is None) != (source_brand_revision_id is None):
            raise ProjectContextError(
                "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                "legacy brand source fields must be provided together",
            )
        brand_revision_ref = payload.get("brand_revision_ref") if schema_version == 2 else None
        if source_pair == (None, None):
            if brand_revision_ref is not None:
                raise ProjectContextError(
                    "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                    "brand revision reference requires trusted source fields",
                )
            return
        if schema_version not in {1, 2} or not isinstance(source_brand_id, str):
            raise ProjectContextError(
                "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                "client source fields are supported only for legacy v1/v2 snapshots",
            )
        if project.brand_id != source_brand_id:
            raise ProjectContextError(
                "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                "legacy brand source does not match the project binding",
            )
        if (
            not isinstance(source_brand_revision_id, str)
            or not source_brand_revision_id.isdecimal()
            or source_brand_revision_id.startswith("0")
        ):
            raise ProjectContextError(
                "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                "legacy brand source revision is invalid",
            )
        revision = int(source_brand_revision_id)
        repository = self._asset_repository
        if repository is None:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "brand revision repository is unavailable",
            )
        try:
            historical = repository.get_domain_revision("brand", source_brand_id, revision)
        except (TypeError, ValueError) as exc:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "brand revision is unavailable",
            ) from exc
        if historical is None:
            raise ProjectContextError(
                "PROJECT_BRAND_REVISION_NOT_FOUND",
                "brand revision is unavailable",
            )
        validate_brand_domain_revision(
            historical,
            expected_brand_id=source_brand_id,
            expected_revision=revision,
        )
        if (
            schema_version == 2
            and brand_revision_ref is not None
            and brand_revision_ref != f"brand:{source_brand_id}@{revision}"
        ):
            raise ProjectContextError(
                "PROJECT_BRAND_CONTEXT_UNTRUSTED",
                "legacy brand revision reference does not match trusted source fields",
            )

    def _resolve_artifact_version(self, version_id: str) -> ArtifactVersion | None:
        try:
            return self.get_artifact_version(version_id)
        except NotFound:
            return None

    def _resolve_asset_revision(self, asset_id: str, revision_id: str) -> dict[str, Any] | None:
        repository = self._asset_repository
        if repository is None:
            from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

            repository = AssetLibraryRepository()
            self._asset_repository = repository
        return repository.get_asset_revision(asset_id, revision_id)

    def get_context_snapshot(self, snapshot_id: str) -> ContextSnapshot:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM context_snapshots WHERE context_snapshot_id = ?", (snapshot_id,)
            ).fetchone()
        if not row:
            raise NotFound(f"context snapshot not found: {snapshot_id}")
        data = dict(row)
        return ContextSnapshot(
            context_snapshot_id=data["context_snapshot_id"],
            project_id=data["project_id"],
            schema_version=data["schema_version"],
            payload=_load(data["payload_json"], {}),
            source_brand_id=data["source_brand_id"],
            source_brand_revision_id=data["source_brand_revision_id"],
            fingerprint=data["fingerprint"],
            created_at=data["created_at"],
        )

    def verify_context_snapshot_integrity(self, snapshot: ContextSnapshot) -> None:
        envelope_fingerprint = _fingerprint(
            {
                "schema_version": snapshot.schema_version,
                "payload": snapshot.payload,
                "source_brand_id": snapshot.source_brand_id,
                "source_brand_revision_id": snapshot.source_brand_revision_id,
            }
        )
        accepted = {envelope_fingerprint}
        if snapshot.schema_version in {1, 2}:
            # Deployed v1/v2 rows used a payload-only fingerprint. Accept both
            # historical and later envelope forms without rewriting either.
            accepted.add(_fingerprint(snapshot.payload))
        if snapshot.fingerprint not in accepted:
            code = (
                "PROJECT_BRAND_CONTEXT_UNTRUSTED"
                if snapshot.schema_version == 3
                else "PROJECT_CONTEXT_INTEGRITY_FAILED"
            )
            raise ProjectContextError(code, "context snapshot fingerprint mismatch")

    @staticmethod
    def _source_artifact_version_ids(input_payload: dict[str, Any]) -> list[str]:
        """Extract only typed handoff references from an application input."""

        values: list[str] = []
        plural = input_payload.get("source_artifact_version_ids")
        if isinstance(plural, list):
            values.extend(str(item).strip() for item in plural if str(item).strip())
        singular = input_payload.get("source_artifact_version_id")
        if isinstance(singular, str) and singular.strip():
            values.append(singular.strip())
        content_source = input_payload.get("content_source")
        if isinstance(content_source, dict):
            for key in ("source_artifact_version_id", "title_artifact_version_id"):
                value = content_source.get(key)
                if isinstance(value, str) and value.strip():
                    values.append(value.strip())
        return list(dict.fromkeys(values))

    def resolve_run_context_snapshot(
        self,
        project_id: str,
        input_payload: dict[str, Any],
        *,
        expected_context_snapshot_id: str | None,
    ) -> str:
        """Resolve a run snapshot from server state or immutable handoff lineage.

        For ordinary runs the client value is only an expected-pointer CAS
        against ``ContentProject.current_context_snapshot_id``. Typed handoffs
        instead inherit the selected ArtifactVersion snapshot so a brand sync
        cannot silently mix an old source artifact with the new project
        context.
        """

        project = self.get_project(project_id)
        source_ids = self._source_artifact_version_ids(input_payload)
        if source_ids:
            versions = [self.get_artifact_version(version_id) for version_id in source_ids]
            if any(version.project_id != project_id for version in versions):
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                    "source artifact version belongs to another project",
                )
            snapshot_ids = {version.context_snapshot_id for version in versions}
            if None in snapshot_ids:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED",
                    "source artifact version has no fixed context snapshot",
                )
            if len(snapshot_ids) != 1:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_HANDOFF_MIXED",
                    "source artifact versions do not share one fixed context snapshot",
                )
            resolved = next(iter(snapshot_ids))
            assert resolved is not None
            if expected_context_snapshot_id not in {
                None,
                project.current_context_snapshot_id,
                resolved,
            }:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CONFLICT",
                    "expected context snapshot does not match project or source provenance",
                )
        else:
            resolved = project.current_context_snapshot_id
            if expected_context_snapshot_id not in {None, resolved}:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CONFLICT",
                    "expected context snapshot does not match current project context",
                )
        if not resolved:
            raise ProjectContextError("PROJECT_CONTEXT_MISSING", "project has no context snapshot")
        snapshot = self.get_context_snapshot(resolved)
        if snapshot.project_id != project_id:
            raise ProjectContextError(
                "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                "context snapshot belongs to another project",
            )
        self.verify_context_snapshot_integrity(snapshot)
        return resolved

    @staticmethod
    def canonicalize_run_input(
        input_payload: dict[str, Any],
        *,
        project_id: str,
        app_id: str,
        context_snapshot_id: str,
    ) -> dict[str, Any]:
        """Overwrite client-owned binding fields with trusted server values."""

        payload = deepcopy(input_payload)
        payload["project_id"] = project_id
        if payload.get("schema_version") == 2:
            payload["app_id"] = app_id
            payload["context_snapshot_id"] = context_snapshot_id
        return payload

    def create_app_run(
        self,
        project_id: str,
        app_id: str,
        app_version: str,
        input_payload: dict[str, Any],
        *,
        idempotency_key: str,
        input_schema_version: int | None = None,
        context_snapshot_id: str | None = None,
        prompt_version: str | None = None,
        session_id: str | None = None,
    ) -> AppRun:
        validate_business_payload(input_payload, label="AppRun input")
        resolved_input_schema_version = input_schema_version or int(
            input_payload.get("schema_version") or 1
        )
        if resolved_input_schema_version not in {1, 2}:
            raise AppCenterRepositoryError("unsupported input schema version")
        existing = self.get_app_run_by_idempotency_key(idempotency_key)
        if existing is not None:
            replay_input = (
                self.canonicalize_run_input(
                    input_payload,
                    project_id=project_id,
                    app_id=app_id,
                    context_snapshot_id=existing.context_snapshot_id,
                )
                if existing.context_snapshot_id is not None
                else input_payload
            )
            same_request = (
                existing.project_id == project_id
                and existing.app_id == app_id
                and existing.app_version == app_version
                and existing.input_schema_version == resolved_input_schema_version
                and existing.prompt_version == prompt_version
                and existing.session_id == session_id
                and (
                    existing.input_payload == replay_input
                    or existing.input_payload == input_payload
                )
            )
            if not same_request:
                raise IdempotencyConflict(f"idempotency key already used: {idempotency_key}")
            return existing

        project = self.get_project(project_id)
        source_ids = self._source_artifact_version_ids(input_payload)
        source_versions: list[ArtifactVersion] = []
        for version_id in source_ids:
            try:
                source_versions.append(self.get_artifact_version(version_id))
            except NotFound:
                if project.current_context_snapshot_id is None and context_snapshot_id is None:
                    source_versions = []
                    break
                raise
        typed_source_requires_context = any(
            version.project_id != project_id or version.context_snapshot_id is not None
            for version in source_versions
        )
        if (
            project.current_context_snapshot_id is not None
            or context_snapshot_id is not None
            or typed_source_requires_context
        ):
            context_snapshot_id = self.resolve_run_context_snapshot(
                project_id,
                input_payload,
                expected_context_snapshot_id=context_snapshot_id,
            )
            input_payload = self.canonicalize_run_input(
                input_payload,
                project_id=project_id,
                app_id=app_id,
                context_snapshot_id=context_snapshot_id,
            )
        run_id = _id("run")
        now = _now()
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO app_runs(
                        app_run_id, app_id, project_id, app_version, state, state_version,
                        idempotency_key, input_schema_version, input_json, context_snapshot_id,
                        prompt_version, session_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'draft', 1, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        app_id,
                        project_id,
                        app_version,
                        idempotency_key,
                        resolved_input_schema_version,
                        _dump(input_payload),
                        context_snapshot_id,
                        prompt_version,
                        session_id,
                        now,
                        now,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT * FROM app_runs WHERE idempotency_key = ?", (idempotency_key,)
                ).fetchone()
            if existing:
                same_request = (
                    all(
                        existing[key] == value
                        for key, value in {
                            "project_id": project_id,
                            "app_id": app_id,
                            "app_version": app_version,
                            "context_snapshot_id": context_snapshot_id,
                            "prompt_version": prompt_version,
                            "session_id": session_id,
                        }.items()
                    )
                    and _load(existing["input_json"], {}) == input_payload
                )
                if not same_request:
                    raise IdempotencyConflict(
                        f"idempotency key already used: {idempotency_key}"
                    ) from exc
                return self._app_run_from_row(existing)
            raise AppCenterRepositoryError(str(exc)) from exc
        return self.get_app_run(run_id)

    def get_app_run_by_idempotency_key(self, idempotency_key: str) -> AppRun | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM app_runs WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
        return self._app_run_from_row(row) if row else None

    def update_app_run_draft(
        self,
        app_run_id: str,
        *,
        input_payload: dict[str, Any] | None = None,
        context_snapshot_id: str | None = None,
        prompt_version: str | None = None,
        session_id: str | None = None,
    ) -> AppRun:
        current = self.get_app_run(app_run_id)
        if current.state != "draft":
            raise AppCenterRepositoryError("only draft AppRuns can be edited")
        next_input = current.input_payload if input_payload is None else input_payload
        validate_business_payload(next_input, label="AppRun input")
        if context_snapshot_id:
            snapshot = self.get_context_snapshot(context_snapshot_id)
            if snapshot.project_id != current.project_id:
                raise AppCenterRepositoryError("context snapshot belongs to another project")
        with self._connect() as conn:
            conn.execute(
                "UPDATE app_runs SET input_json = ?, context_snapshot_id = ?, prompt_version = ?, session_id = ?, updated_at = ? WHERE app_run_id = ? AND state = 'draft'",
                (
                    _dump(next_input),
                    context_snapshot_id,
                    prompt_version,
                    session_id,
                    _now(),
                    app_run_id,
                ),
            )
        return self.get_app_run(app_run_id)

    def get_app_run(self, app_run_id: str) -> AppRun:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM app_runs WHERE app_run_id = ?", (app_run_id,)
            ).fetchone()
        if not row:
            raise NotFound(f"AppRun not found: {app_run_id}")
        return self._app_run_from_row(row)

    def list_app_runs(self, project_id: str | None = None) -> list[AppRun]:
        query = "SELECT * FROM app_runs"
        params: tuple[Any, ...] = ()
        if project_id:
            query += " WHERE project_id = ?"
            params = (project_id,)
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._app_run_from_row(row) for row in rows]

    def list_result_history_runs(
        self,
        project_id: str,
        *,
        app_ids: tuple[str, ...],
        app_id: str | None,
        statuses: tuple[str, ...] | None,
        before_sort_at: str | None,
        before_app_run_id: str | None,
        limit: int,
    ) -> tuple[list[tuple[AppRun, str]], str]:
        """Read one stable page of generation runs without mutating old rows.

        Result history is a projection over the existing AppRun facts. Drafts
        and archived runs are not generation records. The returned revision
        lets the service reject a stale cursor instead of silently duplicating
        or omitting a row when mutable run state changes between requests.
        """

        if limit < 1:
            raise ValueError("result history limit must be positive")
        if not app_ids:
            return [], "none"
        placeholders = ",".join("?" for _ in app_ids)
        filters = [
            "project_id = ?",
            "archived_at IS NULL",
            "state <> 'draft'",
            f"app_id IN ({placeholders})",
        ]
        params: list[Any] = [project_id, *app_ids]
        if app_id is not None:
            filters.append("app_id = ?")
            params.append(app_id)
        if statuses:
            status_placeholders = ",".join("?" for _ in statuses)
            filters.append(f"state IN ({status_placeholders})")
            params.extend(statuses)
        revision_query = f"""
            SELECT app_run_id,
                   state,
                   state_version,
                   created_at,
                   updated_at,
                   completed_at,
                   archived_at
            FROM app_runs
            WHERE {" AND ".join(filters)}
            ORDER BY app_run_id
        """
        revision_params = tuple(params)
        if before_sort_at is not None or before_app_run_id is not None:
            if not before_sort_at or not before_app_run_id:
                raise ValueError("result history cursor position is incomplete")
            sort_expression = "COALESCE(completed_at, updated_at, created_at)"
            filters.append(f"({sort_expression} < ? OR ({sort_expression} = ? AND app_run_id < ?))")
            params.extend([before_sort_at, before_sort_at, before_app_run_id])
        params.append(limit)
        query = f"""
            SELECT app_runs.*,
                   COALESCE(completed_at, updated_at, created_at) AS result_sort_at
            FROM app_runs
            WHERE {" AND ".join(filters)}
            ORDER BY result_sort_at DESC, app_run_id DESC
            LIMIT ?
        """
        with self._connect() as conn:
            conn.execute("BEGIN")
            project = conn.execute(
                "SELECT 1 FROM content_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            if project is None:
                raise NotFound(f"project not found: {project_id}")
            revision_rows = conn.execute(revision_query, revision_params).fetchall()
            revision = hashlib.sha256(
                json.dumps(
                    [dict(row) for row in revision_rows],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            rows = conn.execute(query, params).fetchall()
        return (
            [(self._app_run_from_row(row), str(row["result_sort_at"])) for row in rows],
            revision,
        )

    def list_result_history_artifacts(
        self,
        project_id: str,
        *,
        app_run_ids: list[str],
        output_artifact_ids: list[str],
    ) -> list[Artifact]:
        """Bulk-read current artifacts for a result page in one query."""

        run_ids = list(dict.fromkeys(item for item in app_run_ids if item))
        artifact_ids = list(dict.fromkeys(item for item in output_artifact_ids if item))
        if not run_ids and not artifact_ids:
            return []
        ownership_filters: list[str] = []
        params: list[Any] = [project_id]
        if run_ids:
            placeholders = ",".join("?" for _ in run_ids)
            ownership_filters.append(f"source_app_run_id IN ({placeholders})")
            params.extend(run_ids)
        if artifact_ids:
            placeholders = ",".join("?" for _ in artifact_ids)
            ownership_filters.append(f"artifact_id IN ({placeholders})")
            params.extend(artifact_ids)
        query = f"""
            SELECT *
            FROM artifacts
            WHERE project_id = ?
              AND status <> 'archived'
              AND ({" OR ".join(ownership_filters)})
            ORDER BY updated_at DESC, artifact_id DESC
        """
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Artifact(**dict(row)) for row in rows]

    def get_result_history_versions(
        self,
        project_id: str,
        version_ids: list[str],
    ) -> dict[str, ArtifactVersion]:
        """Bulk-read exact current versions for one result page."""

        ids = list(dict.fromkeys(item for item in version_ids if item))
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM artifact_versions
                WHERE project_id = ?
                  AND artifact_version_id IN ({placeholders})
                """,
                [project_id, *ids],
            ).fetchall()
        return {
            item.artifact_version_id: item
            for item in (self._artifact_version_from_row(row) for row in rows)
        }

    def transition_app_run(
        self, app_run_id: str, target_state: str, *, expected_state_version: int | None = None
    ) -> AppRun:
        current = self.get_app_run(app_run_id)
        validate_transition(current.state, target_state)
        now = _now()
        completed_at = now if target_state in {"completed", "failed", "cancelled"} else None
        error_code = current.error_code if target_state == "failed" else None
        query = "UPDATE app_runs SET state = ?, state_version = state_version + 1, error_code = ?, completed_at = ?, updated_at = ? WHERE app_run_id = ? AND state = ? AND state_version = ?"
        expected = (
            current.state_version if expected_state_version is None else expected_state_version
        )
        with self._connect() as conn:
            updated = conn.execute(
                query,
                (target_state, error_code, completed_at, now, app_run_id, current.state, expected),
            ).rowcount
        if not updated:
            raise ConcurrentWrite(f"AppRun changed concurrently: {app_run_id}")
        return self.get_app_run(app_run_id)

    def retry_app_run(self, app_run_id: str) -> AppRun:
        return self.transition_app_run(app_run_id, "queued")

    def cancel_app_run(self, app_run_id: str) -> AppRun:
        current = self.get_app_run(app_run_id)
        if current.state in {"completed", "failed", "cancelled"}:
            return current
        return self.transition_app_run(app_run_id, "cancelled")

    def archive_app_run(self, app_run_id: str) -> AppRun:
        self.get_app_run(app_run_id)
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE app_runs SET archived_at = ?, updated_at = ? WHERE app_run_id = ?",
                (now, now, app_run_id),
            )
        return self.get_app_run(app_run_id)

    def set_output_artifacts(self, app_run_id: str, artifact_ids: list[str]) -> AppRun:
        self.get_app_run(app_run_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE app_runs SET output_artifact_ids_json = ?, updated_at = ? WHERE app_run_id = ?",
                (_dump(artifact_ids), _now(), app_run_id),
            )
        return self.get_app_run(app_run_id)

    def set_app_run_error(self, app_run_id: str, error_code: str | None) -> AppRun:
        self.get_app_run(app_run_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE app_runs SET error_code = ?, updated_at = ? WHERE app_run_id = ?",
                (error_code, _now(), app_run_id),
            )
        return self.get_app_run(app_run_id)

    def create_attempt(self, app_run_id: str, *, task_id: str | None = None) -> RunAttempt:
        run = self.get_app_run(app_run_id)
        now = _now()
        attempt_id = _id("attempt")
        with self._connect() as conn:
            attempt_number = conn.execute(
                "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM run_attempts WHERE app_run_id = ?",
                (app_run_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO run_attempts(attempt_id, app_run_id, attempt_number, task_id, state, context_snapshot_id, created_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                (attempt_id, app_run_id, attempt_number, task_id, run.context_snapshot_id, now),
            )
        return self.get_attempt(attempt_id)

    def ensure_review_attempt(
        self, app_run_id: str, *, fingerprint: str
    ) -> tuple[RunAttempt, bool]:
        """Atomically create or reuse the imported-output review attempt."""

        attempt_id: str | None = None
        created = False
        now = _now()
        diagnostic = _dump({"legacy_output_fingerprint": fingerprint})
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute(
                "SELECT * FROM app_runs WHERE app_run_id = ?", (app_run_id,)
            ).fetchone()
            if run is None:
                raise NotFound(f"AppRun not found: {app_run_id}")
            latest = conn.execute(
                "SELECT * FROM run_attempts WHERE app_run_id = ? ORDER BY attempt_number DESC LIMIT 1",
                (app_run_id,),
            ).fetchone()
            if latest is not None:
                latest_diagnostic = _load(latest["diagnostic_json"], {})
                if (
                    latest["state"] != "needs_review"
                    or latest_diagnostic.get("legacy_output_fingerprint") != fingerprint
                ):
                    raise AppCenterRepositoryError("ARTIFACT_REVIEW_ATTEMPT_CONFLICT")
                attempt_id = str(latest["attempt_id"])
            else:
                attempt_id = _id("attempt")
                next_number = conn.execute(
                    "SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM run_attempts WHERE app_run_id = ?",
                    (app_run_id,),
                ).fetchone()[0]
                conn.execute(
                    "INSERT INTO run_attempts(attempt_id, app_run_id, attempt_number, task_id, state, context_snapshot_id, diagnostic_json, model_ref, provider_class, completed_at, created_at) VALUES (?, ?, ?, NULL, 'needs_review', ?, ?, 'legacy-session', 'legacy-session', ?, ?)",
                    (
                        attempt_id,
                        app_run_id,
                        next_number,
                        run["context_snapshot_id"],
                        diagnostic,
                        now,
                        now,
                    ),
                )
                created = True
        return self.get_attempt(attempt_id), created

    def delete_attempt(self, attempt_id: str) -> None:
        """Delete an attempt created by a failed pre-output compensation path."""

        with self._connect() as conn:
            conn.execute("DELETE FROM run_attempts WHERE attempt_id = ?", (attempt_id,))

    def get_attempt(self, attempt_id: str) -> RunAttempt:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM run_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
        if not row:
            raise NotFound(f"attempt not found: {attempt_id}")
        return self._attempt_from_row(row)

    def list_attempts(self, app_run_id: str) -> list[RunAttempt]:
        self.get_app_run(app_run_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM run_attempts WHERE app_run_id = ? ORDER BY attempt_number",
                (app_run_id,),
            ).fetchall()
        return [self._attempt_from_row(row) for row in rows]

    def update_attempt(self, attempt_id: str, **values: Any) -> RunAttempt:
        allowed = {
            "state",
            "task_id",
            "error_code",
            "error_message",
            "diagnostic_json",
            "model_ref",
            "provider_class",
            "input_units",
            "output_units",
            "estimated_cost_micros",
            "started_at",
            "completed_at",
            "duration_ms",
        }
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"unsupported attempt fields: {sorted(unknown)}")
        if "diagnostic_json" in values and isinstance(values["diagnostic_json"], dict):
            values["diagnostic_json"] = _dump(values["diagnostic_json"])
        if not values:
            return self.get_attempt(attempt_id)
        assignments = ", ".join(f"{key} = ?" for key in values)
        params = [values[key] for key in values] + [attempt_id]
        with self._connect() as conn:
            conn.execute(f"UPDATE run_attempts SET {assignments} WHERE attempt_id = ?", params)
        return self.get_attempt(attempt_id)

    def create_artifact(
        self,
        project_id: str,
        artifact_type: str,
        name: str,
        *,
        source_app_run_id: str | None = None,
    ) -> Artifact:
        self.get_project(project_id)
        if artifact_type not in KNOWN_ARTIFACT_TYPES:
            raise AppCenterRepositoryError(f"unknown artifact type: {artifact_type}")
        if source_app_run_id:
            source_run = self.get_app_run(source_app_run_id)
            if source_run.project_id != project_id:
                raise AppCenterRepositoryError("source AppRun belongs to another project")
        artifact_id = _id("artifact")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO artifacts(artifact_id, project_id, source_app_run_id, artifact_type, name, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'draft', ?, ?)",
                (artifact_id, project_id, source_app_run_id, artifact_type, name, now, now),
            )
        return self.get_artifact(artifact_id)

    def get_artifact(self, artifact_id: str) -> Artifact:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)
            ).fetchone()
        if not row:
            raise NotFound(f"artifact not found: {artifact_id}")
        return Artifact(**dict(row))

    def list_artifacts(self, project_id: str, *, include_archived: bool = False) -> list[Artifact]:
        self.get_project(project_id)
        query = "SELECT * FROM artifacts WHERE project_id = ?"
        params: list[Any] = [project_id]
        if not include_archived:
            query += " AND status <> 'archived'"
        query += " ORDER BY updated_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [Artifact(**dict(row)) for row in rows]

    def archive_artifact(self, artifact_id: str) -> Artifact:
        self.get_artifact(artifact_id)
        with self._connect() as conn:
            conn.execute(
                "UPDATE artifacts SET status = 'archived', updated_at = ? WHERE artifact_id = ?",
                (_now(), artifact_id),
            )
        return self.get_artifact(artifact_id)

    def purge_run_artifacts(self, app_run_id: str) -> None:
        """Rollback artifacts created by one failed AppRunner attempt.

        This is intentionally scoped to the source AppRun and used only by the
        runner's persistence compensation path; it prevents a failed related
        artifact batch from leaving draft/ready versions that can be mistaken
        for business output.
        """

        self.get_app_run(app_run_id)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM artifact_versions WHERE artifact_id IN (SELECT artifact_id FROM artifacts WHERE source_app_run_id = ?)",
                (app_run_id,),
            )
            conn.execute("DELETE FROM artifacts WHERE source_app_run_id = ?", (app_run_id,))
            conn.commit()

    def purge_artifacts_by_ids(self, artifact_ids: list[str]) -> None:
        """Compensate only the artifacts created by one import invocation.

        Unlike ``purge_run_artifacts``, this narrow primitive is safe when a
        run already owns unrelated historical artifacts or another worker is
        finishing a separate attempt.
        """

        ids = [str(item) for item in artifact_ids if str(item)]
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                f"DELETE FROM artifact_versions WHERE artifact_id IN ({placeholders})",
                ids,
            )
            conn.execute(
                f"DELETE FROM artifacts WHERE artifact_id IN ({placeholders})",
                ids,
            )
            conn.commit()

    def record_app_event(
        self,
        app_run_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> AppEvent:
        run = self.get_app_run(app_run_id)
        if event_type not in WORKBENCH_EVENT_TYPES:
            raise AppCenterRepositoryError("APP_EVENT_TYPE_UNSUPPORTED")
        if not isinstance(payload, dict) or not set(payload).issubset(WORKBENCH_EVENT_PAYLOAD_KEYS):
            raise AppCenterRepositoryError("APP_EVENT_PAYLOAD_INVALID")
        validate_business_payload(payload, label="AppEvent payload")
        if isinstance(payload.get("summary"), str) and len(payload["summary"]) > 120:
            raise AppCenterRepositoryError("APP_EVENT_SUMMARY_TOO_LONG")
        if "item_index" in payload and (
            isinstance(payload["item_index"], bool)
            or not isinstance(payload["item_index"], int)
            or payload["item_index"] < 0
        ):
            raise AppCenterRepositoryError("APP_EVENT_ITEM_INDEX_INVALID")
        artifact_id = payload.get("artifact_id")
        if artifact_id:
            artifact = self.get_artifact(str(artifact_id))
            if (
                artifact.project_id != run.project_id
                or artifact.source_app_run_id != run.app_run_id
            ):
                raise AppCenterRepositoryError("APP_EVENT_ARTIFACT_MISMATCH")
        version_id = payload.get("artifact_version_id")
        if version_id:
            version = self.get_artifact_version(str(version_id))
            if version.project_id != run.project_id or (
                artifact_id and version.artifact_id != artifact_id
            ):
                raise AppCenterRepositoryError("APP_EVENT_VERSION_MISMATCH")
        event_id = _id("event")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO app_events(event_id, app_run_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (event_id, app_run_id, event_type, _dump(payload), now),
            )
        return AppEvent(event_id, app_run_id, event_type, deepcopy(payload), now)

    def list_app_events(self, app_run_id: str) -> list[AppEvent]:
        self.get_app_run(app_run_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM app_events WHERE app_run_id = ? ORDER BY created_at, event_id",
                (app_run_id,),
            ).fetchall()
        return [
            AppEvent(
                event_id=row["event_id"],
                app_run_id=row["app_run_id"],
                event_type=row["event_type"],
                payload=_load(row["payload_json"], {}),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def append_artifact_version(
        self,
        artifact_id: str,
        *,
        content: dict[str, Any] | None = None,
        file_refs: list[dict[str, Any]] | None = None,
        source: str = "generated",
        schema_version: int = 1,
    ) -> ArtifactVersion:
        artifact = self.get_artifact(artifact_id)
        source_app_run_id = artifact.source_app_run_id
        context_snapshot_id: str | None = None
        if source_app_run_id:
            source_run = self.get_app_run(source_app_run_id)
            if source_run.project_id != artifact.project_id:
                raise AppCenterRepositoryError("artifact source AppRun belongs to another project")
            context_snapshot_id = source_run.context_snapshot_id
        if content is not None:
            validate_business_payload(content, label="ArtifactVersion content")
        for file_ref in file_refs or []:
            forbidden = find_forbidden_business_field(file_ref)
            if forbidden:
                raise ValueError(
                    f"ArtifactVersion file reference contains forbidden field: {forbidden}"
                )
        inherited_validation_facts: dict[str, Any] | None = None
        if artifact.artifact_type in {"copywriting", "title_set"} and source == "edited":
            if not artifact.current_version_id:
                raise ValueError(
                    f"{artifact.artifact_type} edited version requires existing structured content"
                )
            current_version = self.get_artifact_version(artifact.current_version_id)
            if not isinstance(current_version.content, dict):
                raise ValueError(
                    f"{artifact.artifact_type} edited version requires existing structured content"
                )
            current_facts = current_version.content.get("validation_facts")
            if isinstance(current_facts, dict):
                inherited_validation_facts = deepcopy(current_facts)
            if content is None:
                content = current_version.content
        if artifact.artifact_type in {"copywriting", "title_set"} and (
            source == "edited"
            or (
                isinstance(content, dict)
                and ("artifact_type" in content or "variants" in content or "candidates" in content)
            )
        ):
            content = self._normalize_structured_artifact_content(
                artifact.artifact_type,
                content,
                schema_version=schema_version,
                fixed_validation_facts=inherited_validation_facts,
            )
        content_fingerprint = _fingerprint({"content": content, "file_refs": file_refs or []})
        version_id = _id("artifact_version")
        now = _now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            number = conn.execute(
                "SELECT COALESCE(MAX(version_number), 0) + 1 FROM artifact_versions WHERE artifact_id = ?",
                (artifact_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO artifact_versions(artifact_version_id, artifact_id, project_id, source_app_run_id, context_snapshot_id, version_number, schema_version, content_json, file_refs_json, source, content_fingerprint, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    version_id,
                    artifact_id,
                    artifact.project_id,
                    source_app_run_id,
                    context_snapshot_id,
                    number,
                    schema_version,
                    _dump(content) if content is not None else None,
                    _dump(file_refs or []),
                    source,
                    content_fingerprint,
                    now,
                ),
            )
            conn.execute(
                "UPDATE artifacts SET current_version_id = ?, status = 'ready', updated_at = ? WHERE artifact_id = ?",
                (version_id, now, artifact_id),
            )
            conn.commit()
        return self.get_artifact_version(version_id)

    def rollback_artifact_version(self, artifact_version_id: str) -> ArtifactVersion:
        """Remove one latest compensating version and restore its prior snapshot."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT artifact_id, version_number FROM artifact_versions WHERE artifact_version_id = ?",
                (artifact_version_id,),
            ).fetchone()
            if row is None:
                raise NotFound(f"artifact version not found: {artifact_version_id}")
            artifact = conn.execute(
                "SELECT current_version_id FROM artifacts WHERE artifact_id = ?",
                (row["artifact_id"],),
            ).fetchone()
            if artifact is None or artifact["current_version_id"] != artifact_version_id:
                raise ConcurrentWrite("ARTIFACT_VERSION_NOT_CURRENT")
            previous = conn.execute(
                "SELECT artifact_version_id FROM artifact_versions WHERE artifact_id = ? AND version_number < ? ORDER BY version_number DESC LIMIT 1",
                (row["artifact_id"], row["version_number"]),
            ).fetchone()
            if previous is None:
                raise AppCenterRepositoryError("ARTIFACT_VERSION_ROLLBACK_REQUIRES_PREVIOUS")
            now = _now()
            conn.execute(
                "DELETE FROM artifact_versions WHERE artifact_version_id = ?",
                (artifact_version_id,),
            )
            conn.execute(
                "UPDATE artifacts SET current_version_id = ?, status = 'ready', updated_at = ? WHERE artifact_id = ?",
                (previous["artifact_version_id"], now, row["artifact_id"]),
            )
            conn.commit()
        return self.get_artifact_version(previous["artifact_version_id"])

    @staticmethod
    def _normalize_structured_artifact_content(
        artifact_type: str,
        content: dict[str, Any] | None,
        *,
        schema_version: int,
        fixed_validation_facts: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if (
            not isinstance(content, dict)
            or content.get("schema_version") != schema_version
            or content.get("artifact_type") != artifact_type
        ):
            raise ValueError(
                f"{artifact_type} ArtifactVersion requires matching schema_version and artifact_type"
            )
        payload = deepcopy(content)
        payload.pop("schema_version", None)
        payload.pop("artifact_type", None)
        requested_validation_facts = payload.pop("validation_facts", {})
        validation_facts = (
            deepcopy(fixed_validation_facts)
            if fixed_validation_facts is not None
            else requested_validation_facts
        )
        fact_input = validation_facts.get("input", {}) if isinstance(validation_facts, dict) else {}
        fact_context = (
            validation_facts.get("context", {}) if isinstance(validation_facts, dict) else {}
        )
        if artifact_type == "copywriting":
            from .structured_apps import MarketingCopyOutput, validate_marketing_output

            model = MarketingCopyOutput.model_validate(payload)
            validate_marketing_output(
                model,
                fact_input if isinstance(fact_input, dict) else {"facts": {}},
                fact_context if isinstance(fact_context, dict) else {},
            )
        else:
            from .structured_apps import ViralTitlesOutput, validate_titles_output

            model = ViralTitlesOutput.model_validate(payload)
            title_input = fact_input if isinstance(fact_input, dict) else {}
            title_input = {
                **title_input,
                "count": len(model.candidates),
                "objective": title_input.get("objective", "click"),
                "platform": title_input.get("platform", "douyin"),
            }
            validate_titles_output(
                model, title_input, fact_context if isinstance(fact_context, dict) else {}
            )
        result = {
            "schema_version": schema_version,
            "artifact_type": artifact_type,
            **model.model_dump(),
        }
        if validation_facts:
            result["validation_facts"] = validation_facts
        return result

    def get_artifact_version(self, version_id: str) -> ArtifactVersion:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM artifact_versions WHERE artifact_version_id = ?", (version_id,)
            ).fetchone()
        if not row:
            raise NotFound(f"artifact version not found: {version_id}")
        return self._artifact_version_from_row(row)

    def list_artifact_versions(self, artifact_id: str) -> list[ArtifactVersion]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifact_versions WHERE artifact_id = ? ORDER BY version_number",
                (artifact_id,),
            ).fetchall()
        return [self._artifact_version_from_row(row) for row in rows]

    def create_handoff(
        self,
        project_id: str,
        source_artifact_id: str,
        source_artifact_version_id: str,
        target_app_id: str,
        target_app_version: str,
        artifact_version_ids: list[str],
        *,
        source_app_run_id: str | None = None,
        target_run_id: str | None = None,
        mapping_version: int = 1,
    ) -> ArtifactHandoff:
        self.get_project(project_id)
        source_artifact = self.get_artifact(source_artifact_id)
        if source_artifact.project_id != project_id:
            raise ProjectContextError(
                "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                "source artifact belongs to another project",
            )
        source_version = self.get_artifact_version(source_artifact_version_id)
        if (
            source_version.project_id != project_id
            or source_version.artifact_id != source_artifact_id
        ):
            raise ProjectContextError(
                "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                "source artifact version does not belong to source artifact/project",
            )
        if source_version.context_snapshot_id is None:
            raise ProjectContextError(
                "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED",
                "source artifact version has no fixed context snapshot",
            )
        if source_app_run_id:
            source_run = self.get_app_run(source_app_run_id)
            if source_run.project_id != project_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                    "source AppRun belongs to another project",
                )
            if (
                source_artifact.source_app_run_id
                and source_artifact.source_app_run_id != source_app_run_id
            ):
                raise ProjectContextError(
                    "PROJECT_CONTEXT_HANDOFF_MIXED",
                    "source AppRun does not match artifact provenance",
                )
        elif source_artifact.source_app_run_id:
            source_run = self.get_app_run(source_artifact.source_app_run_id)
        else:
            source_run = None
        if (
            source_run
            and source_run.app_id == target_app_id
            and source_run.app_version == target_app_version
        ):
            raise AppCenterRepositoryError("handoff target must differ from source application")
        if not artifact_version_ids:
            raise AppCenterRepositoryError("handoff artifact versions cannot be empty")
        if len(set(artifact_version_ids)) != len(artifact_version_ids):
            raise AppCenterRepositoryError("handoff artifact versions must be unique")
        if target_run_id:
            target_run = self.get_app_run(target_run_id)
            if target_run.project_id != project_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                    "target AppRun belongs to another project",
                )
            if target_run.app_id != target_app_id or target_run.app_version != target_app_version:
                raise AppCenterRepositoryError("target AppRun does not match handoff target")
        manifest = get_app(target_app_id, version=target_app_version)
        if manifest is None:
            raise AppCenterRepositoryError("target application version is not registered")
        if source_run:
            source_manifest = get_app(source_run.app_id, version=source_run.app_version)
            if source_manifest and target_app_id not in source_manifest.get("handoff_targets", []):
                raise AppCenterRepositoryError(
                    "source application does not allow this handoff target"
                )
        if source_artifact.artifact_type not in manifest.get("accepted_artifact_types", []):
            raise AppCenterRepositoryError(
                "target application does not accept source artifact type"
            )
        if (
            target_app_id == "builtin.viral-titles"
            and source_artifact.artifact_type == "copywriting"
        ):
            if source_version.schema_version not in {1, 2}:
                raise AppCenterRepositoryError("copywriting source version schema is unsupported")
            try:
                self._normalize_structured_artifact_content(
                    "copywriting", source_version.content, schema_version=source_version.schema_version
                )
            except (AppLLMPortError, ValueError) as exc:
                raise AppCenterRepositoryError(
                    "copywriting source version does not satisfy structured schema"
                ) from exc
        if source_artifact_version_id not in artifact_version_ids:
            raise AppCenterRepositoryError("handoff must include source artifact version")
        for version_id in artifact_version_ids:
            version = self.get_artifact_version(version_id)
            artifact = self.get_artifact(version.artifact_id)
            if version.project_id != project_id or artifact.project_id != project_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_CROSS_PROJECT_REF",
                    "handoff artifact version belongs to another project",
                )
            if artifact.artifact_type not in manifest.get("accepted_artifact_types", []):
                raise AppCenterRepositoryError(
                    "target application does not accept handoff artifact type"
                )
        handoff_id = _id("handoff")
        now = _now()
        effective_source_app_run_id = source_app_run_id or source_artifact.source_app_run_id
        source_context_snapshot_id = source_version.context_snapshot_id
        if effective_source_app_run_id:
            effective_source_run = self.get_app_run(effective_source_app_run_id)
            if source_context_snapshot_id != effective_source_run.context_snapshot_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_HANDOFF_MIXED",
                    "source ArtifactVersion context does not match source AppRun",
                )
        for version_id in artifact_version_ids:
            version = self.get_artifact_version(version_id)
            if version.context_snapshot_id != source_context_snapshot_id:
                raise ProjectContextError(
                    "PROJECT_CONTEXT_HANDOFF_MIXED",
                    "handoff artifact versions mix context snapshots",
                )
        target_context_snapshot_id = (
            self.get_app_run(target_run_id).context_snapshot_id if target_run_id else None
        )
        if target_run_id and (
            target_context_snapshot_id is None
            or target_context_snapshot_id != source_context_snapshot_id
        ):
            raise ProjectContextError(
                "PROJECT_CONTEXT_HANDOFF_MIXED",
                "target AppRun context does not match source artifact context",
            )
        with self._connect() as conn:
            duplicate = conn.execute(
                "SELECT handoff_id FROM artifact_handoffs WHERE source_artifact_version_id = ? AND target_app_id = ? AND target_app_version = ? AND COALESCE(target_run_id, '') = COALESCE(?, '')",
                (source_artifact_version_id, target_app_id, target_app_version, target_run_id),
            ).fetchone()
            if duplicate:
                if mapping_version >= 2:
                    return self.get_handoff(duplicate["handoff_id"])
                raise AppCenterRepositoryError(
                    "handoff already exists for source version and target"
                )
            conn.execute(
                "INSERT INTO artifact_handoffs(handoff_id, project_id, source_app_run_id, source_context_snapshot_id, source_artifact_id, source_artifact_version_id, target_app_id, target_app_version, target_run_id, target_context_snapshot_id, artifact_version_ids_json, mapping_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    handoff_id,
                    project_id,
                    effective_source_app_run_id,
                    source_context_snapshot_id,
                    source_artifact_id,
                    source_artifact_version_id,
                    target_app_id,
                    target_app_version,
                    target_run_id,
                    target_context_snapshot_id,
                    _dump(artifact_version_ids),
                    mapping_version,
                    now,
                ),
            )
        return self.get_handoff(handoff_id)

    def get_handoff(self, handoff_id: str) -> ArtifactHandoff:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM artifact_handoffs WHERE handoff_id = ?", (handoff_id,)
            ).fetchone()
        if not row:
            raise NotFound(f"handoff not found: {handoff_id}")
        data = dict(row)
        return ArtifactHandoff(
            handoff_id=data["handoff_id"],
            project_id=data["project_id"],
            source_app_run_id=data["source_app_run_id"],
            source_context_snapshot_id=data["source_context_snapshot_id"],
            source_artifact_id=data["source_artifact_id"],
            source_artifact_version_id=data["source_artifact_version_id"],
            target_app_id=data["target_app_id"],
            target_app_version=data["target_app_version"],
            target_run_id=data["target_run_id"],
            target_context_snapshot_id=data["target_context_snapshot_id"],
            artifact_version_ids=_load(data["artifact_version_ids_json"], []),
            mapping_version=data["mapping_version"],
            created_at=data["created_at"],
        )

    def list_handoffs(self, source_artifact_id: str) -> list[ArtifactHandoff]:
        self.get_artifact(source_artifact_id)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM artifact_handoffs WHERE source_artifact_id = ? ORDER BY created_at",
                (source_artifact_id,),
            ).fetchall()
        return [self._handoff_from_row(row) for row in rows]

    @staticmethod
    def _handoff_from_row(row: sqlite3.Row) -> ArtifactHandoff:
        data = dict(row)
        return ArtifactHandoff(
            handoff_id=data["handoff_id"],
            project_id=data["project_id"],
            source_app_run_id=data["source_app_run_id"],
            source_context_snapshot_id=data["source_context_snapshot_id"],
            source_artifact_id=data["source_artifact_id"],
            source_artifact_version_id=data["source_artifact_version_id"],
            target_app_id=data["target_app_id"],
            target_app_version=data["target_app_version"],
            target_run_id=data["target_run_id"],
            target_context_snapshot_id=data["target_context_snapshot_id"],
            artifact_version_ids=_load(data["artifact_version_ids_json"], []),
            mapping_version=data["mapping_version"],
            created_at=data["created_at"],
        )

    @staticmethod
    def _app_run_from_row(row: sqlite3.Row) -> AppRun:
        data = dict(row)
        return AppRun(
            app_run_id=data["app_run_id"],
            project_id=data["project_id"],
            app_id=data["app_id"],
            app_version=data["app_version"],
            state=data["state"],
            state_version=data["state_version"],
            idempotency_key=data["idempotency_key"],
            input_schema_version=data["input_schema_version"],
            input_payload=_load(data["input_json"], {}),
            context_snapshot_id=data["context_snapshot_id"],
            prompt_version=data["prompt_version"],
            session_id=data["session_id"],
            output_artifact_ids=_load(data["output_artifact_ids_json"], []),
            error_code=data["error_code"],
            completed_at=data["completed_at"],
            archived_at=data["archived_at"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row) -> RunAttempt:
        data = dict(row)
        return RunAttempt(
            attempt_id=data["attempt_id"],
            app_run_id=data["app_run_id"],
            attempt_number=data["attempt_number"],
            task_id=data["task_id"],
            state=data["state"],
            context_snapshot_id=data["context_snapshot_id"],
            error_code=data["error_code"],
            error_message=data["error_message"],
            diagnostic=_load(data["diagnostic_json"], None),
            model_ref=data["model_ref"],
            provider_class=data["provider_class"],
            input_units=data["input_units"],
            output_units=data["output_units"],
            estimated_cost_micros=data["estimated_cost_micros"],
            started_at=data["started_at"],
            completed_at=data["completed_at"],
            duration_ms=data["duration_ms"],
            created_at=data["created_at"],
        )

    @staticmethod
    def _artifact_version_from_row(row: sqlite3.Row) -> ArtifactVersion:
        data = dict(row)
        return ArtifactVersion(
            artifact_version_id=data["artifact_version_id"],
            artifact_id=data["artifact_id"],
            project_id=data["project_id"],
            source_app_run_id=data["source_app_run_id"],
            context_snapshot_id=data["context_snapshot_id"],
            version_number=data["version_number"],
            schema_version=data["schema_version"],
            content=_load(data["content_json"], None),
            file_refs=_load(data["file_refs_json"], []),
            source=data["source"],
            content_fingerprint=data["content_fingerprint"],
            created_at=data["created_at"],
        )
