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
    AppRun,
    Artifact,
    ArtifactHandoff,
    ArtifactVersion,
    ContentProject,
    ContextSnapshot,
    RunAttempt,
)
from .registry import BUILTIN_MANIFESTS
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
    | {artifact_type for manifest in BUILTIN_MANIFESTS for artifact_type in manifest.get("accepted_artifact_types", [])}
    | {artifact_type for manifest in BUILTIN_MANIFESTS for artifact_type in manifest.get("produced_artifact_types", [])}
    | {"publish_package_ref"}
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
    def __init__(self, db_path: str | Path | None = None):
        self.db_path = migrate_app_center(db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def create_project(self, name: str, primary_goal: str, brand_id: str | None = None) -> ContentProject:
        project_id = _id("project")
        now = _now()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO content_projects(project_id, schema_version, name, status, primary_goal, brand_id, created_at, updated_at) VALUES (?, 1, ?, 'active', ?, ?, ?, ?)",
                (project_id, name, primary_goal, brand_id, now, now),
            )
        return self.get_project(project_id)

    def get_project(self, project_id: str) -> ContentProject:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM content_projects WHERE project_id = ?", (project_id,)).fetchone()
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

    def update_project(self, project_id: str, *, name: str | None = None, primary_goal: str | None = None) -> ContentProject:
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
        source_brand_id: str | None = None,
        source_brand_revision_id: str | None = None,
    ) -> ContextSnapshot:
        self.get_project(project_id)
        validate_business_payload(payload, label="context snapshot")
        snapshot_id = _id("context")
        now = _now()
        fingerprint = _fingerprint(payload)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO context_snapshots(context_snapshot_id, project_id, schema_version, payload_json, source_brand_id, source_brand_revision_id, fingerprint, created_at) VALUES (?, ?, 1, ?, ?, ?, ?, ?)",
                (snapshot_id, project_id, _dump(payload), source_brand_id, source_brand_revision_id, fingerprint, now),
            )
            conn.execute(
                "UPDATE content_projects SET current_context_snapshot_id = ?, updated_at = ? WHERE project_id = ?",
                (snapshot_id, now, project_id),
            )
        return self.get_context_snapshot(snapshot_id)

    def get_context_snapshot(self, snapshot_id: str) -> ContextSnapshot:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM context_snapshots WHERE context_snapshot_id = ?", (snapshot_id,)).fetchone()
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

    def create_app_run(
        self,
        project_id: str,
        app_id: str,
        app_version: str,
        input_payload: dict[str, Any],
        *,
        idempotency_key: str,
        context_snapshot_id: str | None = None,
        prompt_version: str | None = None,
        session_id: str | None = None,
    ) -> AppRun:
        self.get_project(project_id)
        validate_business_payload(input_payload, label="AppRun input")
        if context_snapshot_id:
            snapshot = self.get_context_snapshot(context_snapshot_id)
            if snapshot.project_id != project_id:
                raise AppCenterRepositoryError("context snapshot belongs to another project")
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
                    ) VALUES (?, ?, ?, ?, 'draft', 1, ?, 1, ?, ?, ?, ?, ?, ?)
                    """,
                    (run_id, app_id, project_id, app_version, idempotency_key, _dump(input_payload), context_snapshot_id, prompt_version, session_id, now, now),
                )
        except sqlite3.IntegrityError as exc:
            with self._connect() as conn:
                existing = conn.execute("SELECT * FROM app_runs WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                same_request = all(
                    existing[key] == value
                    for key, value in {
                        "project_id": project_id,
                        "app_id": app_id,
                        "app_version": app_version,
                        "context_snapshot_id": context_snapshot_id,
                        "prompt_version": prompt_version,
                        "session_id": session_id,
                    }.items()
                ) and _load(existing["input_json"], {}) == input_payload
                if not same_request:
                    raise IdempotencyConflict(f"idempotency key already used: {idempotency_key}") from exc
                return self._app_run_from_row(existing)
            raise AppCenterRepositoryError(str(exc)) from exc
        return self.get_app_run(run_id)

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
                (_dump(next_input), context_snapshot_id, prompt_version, session_id, _now(), app_run_id),
            )
        return self.get_app_run(app_run_id)

    def get_app_run(self, app_run_id: str) -> AppRun:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM app_runs WHERE app_run_id = ?", (app_run_id,)).fetchone()
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

    def transition_app_run(self, app_run_id: str, target_state: str, *, expected_state_version: int | None = None) -> AppRun:
        current = self.get_app_run(app_run_id)
        validate_transition(current.state, target_state)
        now = _now()
        completed_at = now if target_state in {"completed", "failed", "cancelled"} else None
        error_code = current.error_code if target_state == "failed" else None
        query = "UPDATE app_runs SET state = ?, state_version = state_version + 1, error_code = ?, completed_at = ?, updated_at = ? WHERE app_run_id = ? AND state = ? AND state_version = ?"
        expected = current.state_version if expected_state_version is None else expected_state_version
        with self._connect() as conn:
            updated = conn.execute(query, (target_state, error_code, completed_at, now, app_run_id, current.state, expected)).rowcount
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
            conn.execute("UPDATE app_runs SET archived_at = ?, updated_at = ? WHERE app_run_id = ?", (now, now, app_run_id))
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
            attempt_number = conn.execute("SELECT COALESCE(MAX(attempt_number), 0) + 1 FROM run_attempts WHERE app_run_id = ?", (app_run_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO run_attempts(attempt_id, app_run_id, attempt_number, task_id, state, context_snapshot_id, created_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                (attempt_id, app_run_id, attempt_number, task_id, run.context_snapshot_id, now),
            )
        return self.get_attempt(attempt_id)

    def ensure_review_attempt(self, app_run_id: str, *, fingerprint: str) -> tuple[RunAttempt, bool]:
        """Atomically create or reuse the imported-output review attempt."""

        attempt_id: str | None = None
        created = False
        now = _now()
        diagnostic = _dump({"legacy_output_fingerprint": fingerprint})
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            run = conn.execute("SELECT * FROM app_runs WHERE app_run_id = ?", (app_run_id,)).fetchone()
            if run is None:
                raise NotFound(f"AppRun not found: {app_run_id}")
            latest = conn.execute(
                "SELECT * FROM run_attempts WHERE app_run_id = ? ORDER BY attempt_number DESC LIMIT 1",
                (app_run_id,),
            ).fetchone()
            if latest is not None:
                latest_diagnostic = _load(latest["diagnostic_json"], {})
                if latest["state"] != "needs_review" or latest_diagnostic.get("legacy_output_fingerprint") != fingerprint:
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
                    (attempt_id, app_run_id, next_number, run["context_snapshot_id"], diagnostic, now, now),
                )
                created = True
        return self.get_attempt(attempt_id), created

    def delete_attempt(self, attempt_id: str) -> None:
        """Delete an attempt created by a failed pre-output compensation path."""

        with self._connect() as conn:
            conn.execute("DELETE FROM run_attempts WHERE attempt_id = ?", (attempt_id,))

    def get_attempt(self, attempt_id: str) -> RunAttempt:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM run_attempts WHERE attempt_id = ?", (attempt_id,)).fetchone()
        if not row:
            raise NotFound(f"attempt not found: {attempt_id}")
        return self._attempt_from_row(row)

    def list_attempts(self, app_run_id: str) -> list[RunAttempt]:
        self.get_app_run(app_run_id)
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM run_attempts WHERE app_run_id = ? ORDER BY attempt_number", (app_run_id,)).fetchall()
        return [self._attempt_from_row(row) for row in rows]

    def update_attempt(self, attempt_id: str, **values: Any) -> RunAttempt:
        allowed = {"state", "task_id", "error_code", "error_message", "diagnostic_json", "model_ref", "provider_class", "input_units", "output_units", "estimated_cost_micros", "started_at", "completed_at", "duration_ms"}
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

    def create_artifact(self, project_id: str, artifact_type: str, name: str, *, source_app_run_id: str | None = None) -> Artifact:
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
            row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?", (artifact_id,)).fetchone()
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
            conn.execute("UPDATE artifacts SET status = 'archived', updated_at = ? WHERE artifact_id = ?", (_now(), artifact_id))
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
        if content is not None:
            validate_business_payload(content, label="ArtifactVersion content")
        for file_ref in file_refs or []:
            forbidden = find_forbidden_business_field(file_ref)
            if forbidden:
                raise ValueError(f"ArtifactVersion file reference contains forbidden field: {forbidden}")
        inherited_validation_facts: dict[str, Any] | None = None
        if artifact.artifact_type in {"copywriting", "title_set"} and source == "edited":
            if not artifact.current_version_id:
                raise ValueError(f"{artifact.artifact_type} edited version requires existing structured content")
            current_version = self.get_artifact_version(artifact.current_version_id)
            if not isinstance(current_version.content, dict):
                raise ValueError(f"{artifact.artifact_type} edited version requires existing structured content")
            current_facts = current_version.content.get("validation_facts")
            if isinstance(current_facts, dict):
                inherited_validation_facts = deepcopy(current_facts)
            if content is None:
                content = current_version.content
        if artifact.artifact_type in {"copywriting", "title_set"} and (source == "edited" or (isinstance(content, dict) and ("artifact_type" in content or "variants" in content or "candidates" in content))):
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
            number = conn.execute("SELECT COALESCE(MAX(version_number), 0) + 1 FROM artifact_versions WHERE artifact_id = ?", (artifact_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO artifact_versions(artifact_version_id, artifact_id, project_id, version_number, schema_version, content_json, file_refs_json, source, content_fingerprint, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (version_id, artifact_id, artifact.project_id, number, schema_version, _dump(content) if content is not None else None, _dump(file_refs or []), source, content_fingerprint, now),
            )
            conn.execute("UPDATE artifacts SET current_version_id = ?, status = 'ready', updated_at = ? WHERE artifact_id = ?", (version_id, now, artifact_id))
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
            conn.execute("DELETE FROM artifact_versions WHERE artifact_version_id = ?", (artifact_version_id,))
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
        if not isinstance(content, dict) or content.get("schema_version") != schema_version or content.get("artifact_type") != artifact_type:
            raise ValueError(f"{artifact_type} ArtifactVersion requires matching schema_version and artifact_type")
        payload = deepcopy(content)
        payload.pop("schema_version", None)
        payload.pop("artifact_type", None)
        requested_validation_facts = payload.pop("validation_facts", {})
        validation_facts = deepcopy(fixed_validation_facts) if fixed_validation_facts is not None else requested_validation_facts
        fact_input = validation_facts.get("input", {}) if isinstance(validation_facts, dict) else {}
        fact_context = validation_facts.get("context", {}) if isinstance(validation_facts, dict) else {}
        if artifact_type == "copywriting":
            from .structured_apps import MarketingCopyOutput, validate_marketing_output

            for variant in payload.get("variants", []):
                if isinstance(variant, dict) and isinstance(variant.get("full_text"), str):
                    variant["word_count"] = len(variant["full_text"])
                    variant["estimated_seconds"] = (variant["word_count"] + 3) // 4
            model = MarketingCopyOutput.model_validate(payload)
            validate_marketing_output(model, fact_input if isinstance(fact_input, dict) else {"facts": {}}, fact_context if isinstance(fact_context, dict) else {})
        else:
            from .structured_apps import ViralTitlesOutput, validate_titles_output

            for candidate in payload.get("candidates", []):
                if isinstance(candidate, dict) and isinstance(candidate.get("title"), str):
                    candidate["length"] = len(candidate["title"])
            model = ViralTitlesOutput.model_validate(payload)
            objective = model.candidates[0].objective if model.candidates else "click"
            title_input = fact_input if isinstance(fact_input, dict) else {}
            title_input = {**title_input, "count": len(model.candidates), "objective": title_input.get("objective", objective)}
            validate_titles_output(model, title_input, fact_context if isinstance(fact_context, dict) else {})
        result = {"schema_version": schema_version, "artifact_type": artifact_type, **model.model_dump()}
        if validation_facts:
            result["validation_facts"] = validation_facts
        return result

    def get_artifact_version(self, version_id: str) -> ArtifactVersion:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM artifact_versions WHERE artifact_version_id = ?", (version_id,)).fetchone()
        if not row:
            raise NotFound(f"artifact version not found: {version_id}")
        return self._artifact_version_from_row(row)

    def list_artifact_versions(self, artifact_id: str) -> list[ArtifactVersion]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM artifact_versions WHERE artifact_id = ? ORDER BY version_number", (artifact_id,)).fetchall()
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
            raise AppCenterRepositoryError("source artifact belongs to another project")
        source_version = self.get_artifact_version(source_artifact_version_id)
        if source_version.project_id != project_id or source_version.artifact_id != source_artifact_id:
            raise AppCenterRepositoryError("source artifact version does not belong to source artifact/project")
        if source_app_run_id:
            source_run = self.get_app_run(source_app_run_id)
            if source_run.project_id != project_id:
                raise AppCenterRepositoryError("source AppRun belongs to another project")
            if source_artifact.source_app_run_id and source_artifact.source_app_run_id != source_app_run_id:
                raise AppCenterRepositoryError("source AppRun does not match artifact provenance")
        elif source_artifact.source_app_run_id:
            source_run = self.get_app_run(source_artifact.source_app_run_id)
        else:
            source_run = None
        if source_run and source_run.app_id == target_app_id and source_run.app_version == target_app_version:
            raise AppCenterRepositoryError("handoff target must differ from source application")
        if not artifact_version_ids:
            raise AppCenterRepositoryError("handoff artifact versions cannot be empty")
        if len(set(artifact_version_ids)) != len(artifact_version_ids):
            raise AppCenterRepositoryError("handoff artifact versions must be unique")
        if target_run_id:
            target_run = self.get_app_run(target_run_id)
            if target_run.project_id != project_id or target_run.app_id != target_app_id or target_run.app_version != target_app_version:
                raise AppCenterRepositoryError("target AppRun does not match handoff target")
        manifest = next(
            (item for item in BUILTIN_MANIFESTS if item["app_id"] == target_app_id and item["version"] == target_app_version),
            None,
        )
        if manifest is None:
            raise AppCenterRepositoryError("target application version is not registered")
        if source_run:
            source_manifest = next(
                (item for item in BUILTIN_MANIFESTS if item["app_id"] == source_run.app_id and item["version"] == source_run.app_version),
                None,
            )
            if source_manifest and target_app_id not in source_manifest.get("handoff_targets", []):
                raise AppCenterRepositoryError("source application does not allow this handoff target")
        if source_artifact.artifact_type not in manifest.get("accepted_artifact_types", []):
            raise AppCenterRepositoryError("target application does not accept source artifact type")
        if target_app_id == "builtin.viral-titles" and source_artifact.artifact_type == "copywriting":
            if source_version.schema_version != 1:
                raise AppCenterRepositoryError("copywriting source version must use schema v1")
            try:
                self._normalize_structured_artifact_content("copywriting", source_version.content, schema_version=1)
            except (AppLLMPortError, ValueError) as exc:
                raise AppCenterRepositoryError("copywriting source version does not satisfy structured schema") from exc
        if source_artifact_version_id not in artifact_version_ids:
            raise AppCenterRepositoryError("handoff must include source artifact version")
        for version_id in artifact_version_ids:
            version = self.get_artifact_version(version_id)
            artifact = self.get_artifact(version.artifact_id)
            if version.project_id != project_id or artifact.project_id != project_id:
                raise AppCenterRepositoryError("handoff artifact version belongs to another project")
            if artifact.artifact_type not in manifest.get("accepted_artifact_types", []):
                raise AppCenterRepositoryError("target application does not accept handoff artifact type")
        handoff_id = _id("handoff")
        now = _now()
        effective_source_app_run_id = source_app_run_id or source_artifact.source_app_run_id
        with self._connect() as conn:
            duplicate = conn.execute(
                "SELECT handoff_id FROM artifact_handoffs WHERE source_artifact_version_id = ? AND target_app_id = ? AND target_app_version = ? AND COALESCE(target_run_id, '') = COALESCE(?, '')",
                (source_artifact_version_id, target_app_id, target_app_version, target_run_id),
            ).fetchone()
            if duplicate:
                raise AppCenterRepositoryError("handoff already exists for source version and target")
            conn.execute(
                "INSERT INTO artifact_handoffs(handoff_id, project_id, source_app_run_id, source_artifact_id, source_artifact_version_id, target_app_id, target_app_version, target_run_id, artifact_version_ids_json, mapping_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (handoff_id, project_id, effective_source_app_run_id, source_artifact_id, source_artifact_version_id, target_app_id, target_app_version, target_run_id, _dump(artifact_version_ids), mapping_version, now),
            )
        return self.get_handoff(handoff_id)

    def get_handoff(self, handoff_id: str) -> ArtifactHandoff:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM artifact_handoffs WHERE handoff_id = ?", (handoff_id,)).fetchone()
        if not row:
            raise NotFound(f"handoff not found: {handoff_id}")
        data = dict(row)
        return ArtifactHandoff(
            handoff_id=data["handoff_id"], project_id=data["project_id"], source_app_run_id=data["source_app_run_id"],
            source_artifact_id=data["source_artifact_id"], source_artifact_version_id=data["source_artifact_version_id"],
            target_app_id=data["target_app_id"], target_app_version=data["target_app_version"], target_run_id=data["target_run_id"],
            artifact_version_ids=_load(data["artifact_version_ids_json"], []), mapping_version=data["mapping_version"], created_at=data["created_at"],
        )

    def list_handoffs(self, source_artifact_id: str) -> list[ArtifactHandoff]:
        self.get_artifact(source_artifact_id)
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM artifact_handoffs WHERE source_artifact_id = ? ORDER BY created_at", (source_artifact_id,)).fetchall()
        return [self._handoff_from_row(row) for row in rows]

    @staticmethod
    def _handoff_from_row(row: sqlite3.Row) -> ArtifactHandoff:
        data = dict(row)
        return ArtifactHandoff(
            handoff_id=data["handoff_id"], project_id=data["project_id"], source_app_run_id=data["source_app_run_id"],
            source_artifact_id=data["source_artifact_id"], source_artifact_version_id=data["source_artifact_version_id"],
            target_app_id=data["target_app_id"], target_app_version=data["target_app_version"], target_run_id=data["target_run_id"],
            artifact_version_ids=_load(data["artifact_version_ids_json"], []), mapping_version=data["mapping_version"], created_at=data["created_at"],
        )

    @staticmethod
    def _app_run_from_row(row: sqlite3.Row) -> AppRun:
        data = dict(row)
        return AppRun(
            app_run_id=data["app_run_id"], project_id=data["project_id"], app_id=data["app_id"], app_version=data["app_version"],
            state=data["state"], state_version=data["state_version"], idempotency_key=data["idempotency_key"], input_schema_version=data["input_schema_version"],
            input_payload=_load(data["input_json"], {}), context_snapshot_id=data["context_snapshot_id"], prompt_version=data["prompt_version"], session_id=data["session_id"],
            output_artifact_ids=_load(data["output_artifact_ids_json"], []), error_code=data["error_code"], completed_at=data["completed_at"], archived_at=data["archived_at"],
            created_at=data["created_at"], updated_at=data["updated_at"],
        )

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row) -> RunAttempt:
        data = dict(row)
        return RunAttempt(
            attempt_id=data["attempt_id"], app_run_id=data["app_run_id"], attempt_number=data["attempt_number"], task_id=data["task_id"], state=data["state"],
            context_snapshot_id=data["context_snapshot_id"], error_code=data["error_code"], error_message=data["error_message"], diagnostic=_load(data["diagnostic_json"], None),
            model_ref=data["model_ref"], provider_class=data["provider_class"], input_units=data["input_units"], output_units=data["output_units"], estimated_cost_micros=data["estimated_cost_micros"],
            started_at=data["started_at"], completed_at=data["completed_at"], duration_ms=data["duration_ms"], created_at=data["created_at"],
        )

    @staticmethod
    def _artifact_version_from_row(row: sqlite3.Row) -> ArtifactVersion:
        data = dict(row)
        return ArtifactVersion(
            artifact_version_id=data["artifact_version_id"], artifact_id=data["artifact_id"], project_id=data["project_id"], version_number=data["version_number"], schema_version=data["schema_version"],
            content=_load(data["content_json"], None), file_refs=_load(data["file_refs_json"], []), source=data["source"], content_fingerprint=data["content_fingerprint"], created_at=data["created_at"],
        )
