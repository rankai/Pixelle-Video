"""Publishing Package/Run/Step/Event repository for PUB-2."""

from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pixelle_video.utils.os_util import get_data_path

from .account_models import PublishPlatform
from .core_models import (
    RUN_TRANSITIONS,
    ArtifactRef,
    HumanConfirmation,
    MediaManifest,
    PlatformCopy,
    PublishEvent,
    PublishPackageV2,
    PublishPolicy,
    PublishRun,
    PublishRunState,
    PublishSource,
    PublishStepAttempt,
)
from .execution_protocol import PublishStage


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load(value: str | None, default: Any):
    return default if not value else json.loads(value)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class PublishCoreError(RuntimeError):
    """Base error for package/run operations."""


class PublishPackageNotFound(PublishCoreError):
    pass


class PublishRunNotFound(PublishCoreError):
    pass


class PublishPackageConflict(PublishCoreError):
    pass


class PublishRunConflict(PublishCoreError):
    pass


class PublishRunAlreadyActive(PublishRunConflict):
    pass


class PublishRunConcurrencyConflict(PublishRunConflict):
    pass


ALLOWED_EVENT_FIELDS = frozenset(
    {"step", "error_code", "duration_ms", "adapter_version", "evidence_kind", "retry_attempt", "human_outcome"}
)
FORBIDDEN_EVENT_FIELDS = frozenset(
    {"cookie", "qr_payload", "authorization", "api_key", "absolute_file_path", "request_params", "description", "title", "profile_path"}
)


class PublishCoreRepository:
    """Owns immutable packages and mutable run facts in publishing.sqlite3."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path or get_data_path("publishing", "publishing.sqlite3")).resolve()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def migrate(self) -> None:
        schema = Path(__file__).resolve().parents[3] / "docs/contracts/publishing/publishing-v2.sql"
        with self._connect() as conn:
            conn.executescript(schema.read_text(encoding="utf-8"))
            self._ensure_columns(conn)
            for trigger in (
                "publish_run_state_guard",
                "publish_run_state_update_guard",
                "publish_run_account_platform_update_guard",
                "publish_package_immutable_guard",
                "publish_package_invalidation_guard",
            ):
                conn.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            conn.execute("DROP INDEX IF EXISTS publish_active_run_by_account_platform")
            conn.execute("DROP INDEX IF EXISTS publish_active_run_by_package_account_platform")
            conn.execute("DROP INDEX IF EXISTS publish_events_run_cursor")
            conn.executescript(schema.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT OR IGNORE INTO publishing_schema_migrations(migration_id, schema_version, applied_at) VALUES ('publishing-v2-hardening', 2, CURRENT_TIMESTAMP)"
            )

    @staticmethod
    def _ensure_columns(conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(publish_runs_v2)")}
        additions = {
            "task_id": "TEXT",
            "error_code": "TEXT",
            "error_message": "TEXT",
            "checkpoint_json": "TEXT NOT NULL DEFAULT '{}'",
            "cancel_requested": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, declaration in additions.items():
            if name not in columns:
                conn.execute(f"ALTER TABLE publish_runs_v2 ADD COLUMN {name} {declaration}")
        package_columns = {row[1] for row in conn.execute("PRAGMA table_info(publish_packages_v2)")}
        if "carousel_manifests_json" not in package_columns:
            conn.execute("ALTER TABLE publish_packages_v2 ADD COLUMN carousel_manifests_json TEXT NOT NULL DEFAULT '[]'")

    def create_package(self, package: PublishPackageV2) -> PublishPackageV2:
        existing = self._find_package_by_fingerprint(package.package_fingerprint)
        if existing:
            if _package_identity_snapshot(existing) == _package_identity_snapshot(package):
                return existing
            raise PublishPackageConflict("PACKAGE_FINGERPRINT_CONFLICT")
        now = package.created_at or _now()
        try:
            with self._transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO publish_packages_v2(
                      package_id, schema_version, project_id, source_kind,
                      source_artifact_ids_json, source_artifact_version_ids_json,
                      source_session_id, source_revision, artifact_refs_json,
                      video_manifest_json, carousel_manifests_json, cover_manifest_json, platform_copy_json,
                      policy_json, package_fingerprint, created_at, invalidated_at, invalidation_reason
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        package.package_id,
                        package.schema_version,
                        package.project_id,
                        package.source.kind,
                        _dump(package.source.artifact_ids),
                        _dump(package.source.artifact_version_ids),
                        package.source.session_id,
                        package.source.source_revision,
                        _dump([item.model_dump(mode="json") for item in package.artifact_refs]),
                        _dump(package.video_manifest.model_dump(mode="json") if package.video_manifest else {}),
                        _dump([item.model_dump(mode="json") for item in package.carousel_manifests or []]),
                        _dump(package.cover_manifest.model_dump(mode="json") if package.cover_manifest else {}),
                        _dump(package.platform_copy.model_dump(mode="json")),
                        _dump(package.policy.model_dump(mode="json")),
                        package.package_fingerprint,
                        now,
                        package.invalidated_at,
                        package.invalidation_reason,
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise PublishPackageConflict(str(exc)) from exc
        return self.get_package(package.package_id)

    def get_package(self, package_id: str) -> PublishPackageV2:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM publish_packages_v2 WHERE package_id = ?", (package_id,)).fetchone()
        if row is None:
            raise PublishPackageNotFound(package_id)
        return self._package_from_row(row)

    def list_packages_for_source_version(self, artifact_version_id: str) -> list[PublishPackageV2]:
        """Return immutable packages whose frozen source includes one version."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM publish_packages_v2 ORDER BY created_at").fetchall()
        return [
            package
            for row in rows
            for package in [self._package_from_row(row)]
            if artifact_version_id in package.source.artifact_version_ids
        ]

    def list_packages_for_artifact(self, artifact_id: str) -> list[PublishPackageV2]:
        """Return immutable packages whose frozen source includes one artifact."""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM publish_packages_v2 ORDER BY created_at").fetchall()
        return [
            package
            for row in rows
            for package in [self._package_from_row(row)]
            if artifact_id in package.source.artifact_ids
        ]

    def list_packages_for_project(self, project_id: str) -> list[PublishPackageV2]:
        """Return package facts for deterministic source-version replacement checks."""

        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM publish_packages_v2 WHERE project_id = ? ORDER BY created_at", (project_id,)).fetchall()
        return [self._package_from_row(row) for row in rows]

    def invalidate_package(self, package_id: str, reason: str) -> PublishPackageV2:
        if not reason.strip():
            raise ValueError("PACKAGE_INVALIDATION_REASON_REQUIRED")
        with self._transaction() as conn:
            row = conn.execute("SELECT invalidated_at FROM publish_packages_v2 WHERE package_id = ?", (package_id,)).fetchone()
            if row is None:
                raise PublishPackageNotFound(package_id)
            if row["invalidated_at"]:
                return self.get_package(package_id)
            conn.execute(
                "UPDATE publish_packages_v2 SET invalidated_at = ?, invalidation_reason = ? WHERE package_id = ?",
                (_now(), reason.strip(), package_id),
            )
        return self.get_package(package_id)

    def create_run(
        self,
        package_id: str,
        account_id: str,
        platform: PublishPlatform,
        idempotency_key: str,
    ) -> tuple[PublishRun, bool]:
        package = self.get_package(package_id)
        if package.invalidated_at:
            raise PublishPackageConflict("PUBLISH_PACKAGE_STALE")
        with self._transaction() as conn:
            existing = conn.execute(
                "SELECT * FROM publish_runs_v2 WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing:
                if existing["package_id"] != package_id or existing["account_id"] != account_id or existing["platform"] != platform.value:
                    raise PublishRunConflict("IDEMPOTENCY_CONFLICT")
                return self._run_from_row(existing), True
            active = conn.execute(
                """
                SELECT r.* FROM publish_runs_v2 r
                JOIN publish_packages_v2 p ON p.package_id = r.package_id
                WHERE r.account_id = ? AND r.platform = ?
                  AND r.state IN ('queued','running','waiting_for_login','waiting_for_human','needs_attention')
                ORDER BY r.created_at DESC LIMIT 1
                """,
                (account_id, platform.value),
            ).fetchone()
            if active:
                if active["package_id"] == package_id:
                    return self._run_from_row(active), True
                raise PublishRunAlreadyActive("RUN_ALREADY_ACTIVE")
            run_id = _id("run")
            now = _now()
            try:
                conn.execute(
                    """
                    INSERT INTO publish_runs_v2(
                      run_id, package_id, account_id, platform, state, state_version,
                      attempt, current_step, idempotency_key, human_confirmation_required,
                      human_confirmed, checkpoint_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'queued', 1, 1, NULL, ?, 1, 0, '{}', ?, ?)
                    """,
                    (run_id, package_id, account_id, platform.value, idempotency_key, now, now),
                )
            except sqlite3.IntegrityError as exc:
                if "publish_active_run" in str(exc).lower() or "unique" in str(exc).lower():
                    raise PublishRunAlreadyActive("RUN_ALREADY_ACTIVE") from exc
                raise PublishRunConflict(str(exc)) from exc
        return self.get_run(run_id), False

    def attach_task(self, run_id: str, task_id: str) -> PublishRun:
        with self._transaction() as conn:
            row = conn.execute("SELECT task_id FROM publish_runs_v2 WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PublishRunNotFound(run_id)
            if row["task_id"] and row["task_id"] != task_id:
                raise PublishRunConflict("TASK_ALREADY_ATTACHED")
            if row["task_id"] == task_id:
                return self.get_run(run_id)
            conn.execute("UPDATE publish_runs_v2 SET task_id = ?, updated_at = ? WHERE run_id = ?", (task_id, _now(), run_id))
        return self.get_run(run_id)

    def get_run(self, run_id: str) -> PublishRun:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM publish_runs_v2 WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise PublishRunNotFound(run_id)
        return self._run_from_row(row)

    def transition_run(
        self,
        run_id: str,
        next_state: PublishRunState,
        *,
        expected_version: int,
        current_step: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        checkpoint: dict[str, Any] | None = None,
        human_confirmed: bool | None = None,
        actor_ref: str | None = None,
        event_type: str | None = None,
        event_payload: dict[str, Any] | None = None,
    ) -> PublishRun:
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM publish_runs_v2 WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PublishRunNotFound(run_id)
            current = PublishRunState(row["state"])
            if next_state not in RUN_TRANSITIONS[current]:
                raise PublishRunConflict("RUN_STATE_INVALID")
            if current is PublishRunState.NEEDS_ATTENTION and next_state is PublishRunState.WAITING_FOR_HUMAN:
                checkpoint_data = _load(row["checkpoint_json"], {})
                if not (
                    event_type == "verified_checkpoint_reconciled"
                    and checkpoint_data.get("last_stage") == PublishStage.VERIFY.value
                    and PublishStage.VERIFY.value in (checkpoint_data.get("completed_stages") or [])
                    and checkpoint_data.get("blocker_code") is None
                    and checkpoint_data.get("blocked_stage") is None
                    and checkpoint_data.get("final_action_guard_armed") is True
                    and checkpoint_data.get("final_publish_clicked") is False
                ):
                    raise PublishRunConflict("CHECKPOINT_NOT_VERIFIED")
            if next_state == PublishRunState.SUCCEEDED and not (human_confirmed or bool(row["human_confirmed"])):
                raise PublishRunConflict("SUCCESS_REQUIRES_HUMAN_CONFIRMATION")
            if row["state_version"] != expected_version:
                raise PublishRunConcurrencyConflict("RUN_VERSION_CONFLICT")
            confirmed = int(bool(row["human_confirmed"] if human_confirmed is None else human_confirmed))
            now = _now()
            updated = conn.execute(
                """
                UPDATE publish_runs_v2
                SET state = ?, state_version = state_version + 1, current_step = ?,
                    error_code = ?, error_message = ?, checkpoint_json = ?,
                    human_confirmed = ?, confirmed_at = CASE WHEN ? = 1 THEN COALESCE(confirmed_at, ?) ELSE confirmed_at END,
                    actor_ref = COALESCE(?, actor_ref), updated_at = ?
                WHERE run_id = ? AND state_version = ?
                """,
                (
                    next_state.value,
                    current_step,
                    error_code,
                    error_message,
                    _dump(checkpoint or _load(row["checkpoint_json"], {})),
                    confirmed,
                    confirmed,
                    now,
                    actor_ref,
                    now,
                    run_id,
                    expected_version,
                ),
            ).rowcount
            if not updated:
                raise PublishRunConcurrencyConflict("RUN_VERSION_CONFLICT")
            if event_type:
                self._append_event_locked(
                    conn,
                    run_id,
                    event_type,
                    state=next_state,
                    state_version=expected_version + 1,
                    payload=event_payload or {"step": current_step or next_state.value},
                )
        return self.get_run(run_id)

    def queue_step_retry(
        self,
        run_id: str,
        step: str,
        *,
        expected_version: int,
        step_attempt: int,
        actor_ref: str | None = None,
    ) -> PublishRun:
        """Atomically append a retry fact and requeue the run."""
        with self._transaction() as conn:
            row = conn.execute("SELECT * FROM publish_runs_v2 WHERE run_id = ?", (run_id,)).fetchone()
            if row is None:
                raise PublishRunNotFound(run_id)
            if row["state"] != PublishRunState.NEEDS_ATTENTION.value:
                raise PublishRunConflict("RUN_STATE_INVALID")
            if row["state_version"] != expected_version:
                raise PublishRunConcurrencyConflict("RUN_VERSION_CONFLICT")
            now = _now()
            conn.execute(
                "INSERT INTO publish_run_step_attempts(step_attempt_id, run_id, step, attempt, state, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                (_id("step"), run_id, step, step_attempt, now, now),
            )
            updated = conn.execute(
                "UPDATE publish_runs_v2 SET state = 'queued', state_version = state_version + 1, attempt = attempt + 1, current_step = ?, error_code = NULL, error_message = NULL, actor_ref = COALESCE(?, actor_ref), updated_at = ? WHERE run_id = ? AND state_version = ?",
                (step, actor_ref, now, run_id, expected_version),
            ).rowcount
            if not updated:
                raise PublishRunConcurrencyConflict("RUN_VERSION_CONFLICT")
            self._append_event_locked(conn, run_id, "step_retry_queued", state=PublishRunState.QUEUED, state_version=expected_version + 1, payload={"step": step, "retry_attempt": step_attempt})
        return self.get_run(run_id)

    def _append_event_locked(
        self,
        conn: sqlite3.Connection,
        run_id: str,
        event_type: str,
        *,
        state: PublishRunState | None,
        state_version: int,
        payload: dict[str, Any],
    ) -> PublishEvent:
        safe_payload = sanitize_event_payload(payload)
        row = conn.execute("SELECT state, state_version FROM publish_runs_v2 WHERE run_id = ?", (run_id,)).fetchone()
        if row is None:
            raise PublishRunNotFound(run_id)
        if row["state_version"] != state_version or (state is not None and row["state"] != state.value):
            raise PublishRunConflict("EVENT_STATE_VERSION_MISMATCH")
        event_id = _id("event")
        seq = conn.execute("SELECT COALESCE(MAX(event_seq), 0) + 1 FROM publish_events WHERE run_id = ?", (run_id,)).fetchone()[0]
        now = _now()
        conn.execute(
            "INSERT INTO publish_events(event_id, run_id, event_seq, event_type, state, state_version, payload_json, redacted, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (event_id, run_id, seq, event_type, state.value if state else None, state_version, _dump(safe_payload), now),
        )
        return PublishEvent(event_id=event_id, run_id=run_id, event_seq=seq, event_type=event_type, state=state, state_version=state_version, payload=safe_payload, created_at=now)

    def append_event(self, run_id: str, event_type: str, *, state: PublishRunState | None, state_version: int, payload: dict[str, Any] | None = None) -> PublishEvent:
        with self._transaction() as conn:
            return self._append_event_locked(conn, run_id, event_type, state=state, state_version=state_version, payload=payload or {})

    def list_events(self, run_id: str, *, after: int = 0) -> list[PublishEvent]:
        self.get_run(run_id)
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM publish_events WHERE run_id = ? AND event_seq > ? ORDER BY event_seq", (run_id, after)).fetchall()
        return [PublishEvent(event_id=row["event_id"], run_id=run_id, event_seq=row["event_seq"], event_type=row["event_type"], state=row["state"], state_version=row["state_version"], payload=_load(row["payload_json"], {}), created_at=row["created_at"]) for row in rows]

    def create_step_attempt(self, run_id: str, step: str, attempt: int, state: PublishRunState = PublishRunState.QUEUED) -> PublishStepAttempt:
        attempt_id = _id("step")
        now = _now()
        with self._transaction() as conn:
            conn.execute(
                "INSERT INTO publish_run_step_attempts(step_attempt_id, run_id, step, attempt, state, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (attempt_id, run_id, step, attempt, state.value, now, now),
            )
        return PublishStepAttempt(step_attempt_id=attempt_id, run_id=run_id, step=step, attempt=attempt, state=state, created_at=now, updated_at=now)

    def list_step_attempts(self, run_id: str, *, step: str | None = None) -> list[PublishStepAttempt]:
        self.get_run(run_id)
        query = "SELECT * FROM publish_run_step_attempts WHERE run_id = ?"
        params: list[Any] = [run_id]
        if step is not None:
            query += " AND step = ?"
            params.append(step)
        query += " ORDER BY step, attempt"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            PublishStepAttempt(
                step_attempt_id=row["step_attempt_id"],
                run_id=row["run_id"],
                step=row["step"],
                attempt=row["attempt"],
                state=PublishRunState(row["state"]),
                evidence_kind=row["evidence_kind"],
                evidence_ref=row["evidence_ref"],
                error_code=row["error_code"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    def update_step_attempt(
        self,
        run_id: str,
        step: str,
        attempt: int,
        state: PublishRunState,
        *,
        error_code: str | None = None,
    ) -> PublishStepAttempt:
        now = _now()
        with self._transaction() as conn:
            row = conn.execute(
                "SELECT state FROM publish_run_step_attempts WHERE run_id = ? AND step = ? AND attempt = ?",
                (run_id, step, attempt),
            ).fetchone()
            if row is None:
                raise PublishCoreError("STEP_ATTEMPT_NOT_FOUND")
            current_state = PublishRunState(row["state"])
            if current_state in {PublishRunState.SUCCEEDED, PublishRunState.FAILED, PublishRunState.CANCELLED}:
                if current_state is not state:
                    raise PublishRunConflict("STEP_ATTEMPT_TERMINAL")
                return next(item for item in self.list_step_attempts(run_id, step=step) if item.attempt == attempt)
            if state not in {PublishRunState.RUNNING, PublishRunState.SUCCEEDED, PublishRunState.FAILED, PublishRunState.CANCELLED}:
                raise PublishRunConflict("STEP_ATTEMPT_STATE_INVALID")
            updated = conn.execute(
                "UPDATE publish_run_step_attempts SET state = ?, error_code = ?, updated_at = ? WHERE run_id = ? AND step = ? AND attempt = ?",
                (state.value, error_code, now, run_id, step, attempt),
            ).rowcount
            if not updated:
                raise PublishCoreError("STEP_ATTEMPT_NOT_FOUND")
        return next(item for item in self.list_step_attempts(run_id, step=step) if item.attempt == attempt)

    def recover_inflight_runs(self) -> list[PublishRun]:
        recovered: list[PublishRun] = []
        with self._connect() as conn:
            # ``waiting_for_human`` is an intentional, durable safety
            # boundary.  A process restart must not turn it into
            # ``PROCESS_RESTART``/``needs_attention``: doing so loses the
            # verified checkpoint projection and makes every sidecar start
            # mutate an already human-gated run.  Only genuinely in-flight
            # scheduler states need restart recovery.
            rows = conn.execute("SELECT run_id, state, state_version, current_step FROM publish_runs_v2 WHERE state IN ('running', 'queued')").fetchall()
        for row in rows:
            try:
                recovered.append(self.transition_run(row["run_id"], PublishRunState.NEEDS_ATTENTION, expected_version=row["state_version"], current_step=row["current_step"] or "restart_recovery", error_code="PROCESS_RESTART", error_message="发布进程重启，需要人工恢复", event_type="process_restart_recovery", event_payload={"step": "restart_recovery", "error_code": "PROCESS_RESTART"}))
            except PublishCoreError:
                continue
        return recovered

    def _find_package_by_fingerprint(self, fingerprint: str) -> PublishPackageV2 | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM publish_packages_v2 WHERE package_fingerprint = ?", (fingerprint,)).fetchone()
        return self._package_from_row(row) if row else None

    @staticmethod
    def _package_from_row(row: sqlite3.Row) -> PublishPackageV2:
        return PublishPackageV2(
            schema_version=row["schema_version"],
            package_id=row["package_id"],
            project_id=row["project_id"],
            source=PublishSource(kind=row["source_kind"], artifact_ids=_load(row["source_artifact_ids_json"], []), artifact_version_ids=_load(row["source_artifact_version_ids_json"], []), session_id=row["source_session_id"], source_revision=row["source_revision"]),
            artifact_refs=[ArtifactRef(**item) for item in _load(row["artifact_refs_json"], [])],
            video_manifest=MediaManifest(**_load(row["video_manifest_json"], {})) if _load(row["video_manifest_json"], {}) else None,
            carousel_manifests=[MediaManifest(**item) for item in _load(row["carousel_manifests_json"], [])] or None,
            cover_manifest=MediaManifest(**_load(row["cover_manifest_json"], {})) if _load(row["cover_manifest_json"], {}) else None,
            platform_copy=PlatformCopy(**_load(row["platform_copy_json"], {})),
            policy=PublishPolicy(**_load(row["policy_json"], {})),
            package_fingerprint=row["package_fingerprint"],
            invalidated_at=row["invalidated_at"],
            invalidation_reason=row["invalidation_reason"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _run_from_row(row: sqlite3.Row) -> PublishRun:
        return PublishRun(
            run_id=row["run_id"], package_id=row["package_id"], account_id=row["account_id"], platform=PublishPlatform(row["platform"]),
            state=PublishRunState(row["state"]), state_version=row["state_version"], attempt=row["attempt"], current_step=row["current_step"],
            idempotency_key=row["idempotency_key"], human_confirmation=HumanConfirmation(required=True, confirmed=bool(row["human_confirmed"]), confirmed_at=row["confirmed_at"], actor_ref=row["actor_ref"]),
            task_id=row["task_id"], error_code=row["error_code"], error_message=row["error_message"],
            checkpoint=_load(row["checkpoint_json"], {}), created_at=row["created_at"], updated_at=row["updated_at"],
        )


def sanitize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    unknown = set(payload) - ALLOWED_EVENT_FIELDS
    forbidden = {key for key in payload if key.lower() in FORBIDDEN_EVENT_FIELDS}
    if unknown or forbidden:
        raise ValueError("EVENT_PAYLOAD_FIELD_FORBIDDEN")
    serialized = _dump(payload).lower()
    if any(marker in serialized for marker in FORBIDDEN_EVENT_FIELDS):
        raise ValueError("EVENT_PAYLOAD_SECRET_OR_BUSINESS_DATA")
    if re.search(r"(?:^|[\s\"':])/(?:users|private|tmp|var|home|volumes)/|[a-z]:[\\/]", serialized):
        raise ValueError("EVENT_PAYLOAD_ABSOLUTE_PATH")
    return json.loads(_dump(payload))


def _package_snapshot(package: PublishPackageV2) -> dict[str, Any]:
    data = package.model_dump(mode="json")
    for key in ("package_id", "package_fingerprint", "created_at", "invalidated_at", "invalidation_reason"):
        data.pop(key, None)
    return data


def _package_identity_snapshot(package: PublishPackageV2) -> dict[str, Any]:
    """Compare immutable delivery identity across source representations.

    `artifact_versions` and `legacy_session` are deliberately retained as
    audit facts on the stored package, but source kind/session/revision and
    artifact IDs are not part of the canonical package identity.
    """

    return {
        "project_id": package.project_id,
        "schema_version": package.schema_version,
        "video_sha256": package.video_manifest.sha256 if package.video_manifest else None,
        "cover_sha256": package.cover_manifest.sha256 if package.cover_manifest else None,
        "platform_copy": package.platform_copy.model_dump(mode="json"),
    }
