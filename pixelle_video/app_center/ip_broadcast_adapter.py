"""Application-center adapter for the existing IP broadcast workflow.

This module is deliberately a small integration seam.  It owns the identity
and recovery facts needed by an AppRun, while the legacy
``IpBroadcastSessionStore`` remains the source of step state until a later
implementation batch moves the actual workflow execution behind this
adapter.  No provider, browser, or platform side effect is performed here.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import stat
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from pixelle_video.app_center.models import AppRun, ArtifactVersion
from pixelle_video.app_center.registry import get_app
from pixelle_video.app_center.repository import (
    AppCenterRepository,
    AppCenterRepositoryError,
    NotFound,
)
from pixelle_video.app_center.runner import AppRunner, ExecutorOutput, RelatedArtifactOutput
from pixelle_video.app_center.state_machine import InvalidAppRunTransition
from pixelle_video.app_center.validation import validate_business_payload
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSession, IpBroadcastSessionStore
from pixelle_video.utils.os_util import get_data_path, get_output_path, get_temp_path

APP_ID = "builtin.digital-human-video"
APP_VERSION = "1.0.0"
SOURCE_MODES = frozenset({"blank_project", "copywriting", "selected_title"})
RESUME_MODES = frozenset({"new_session", "resume_existing"})
TERMINAL_APP_RUN_STATES = frozenset({"completed", "failed", "cancelled"})
LEGACY_ARTIFACT_SOURCE = "imported"
LEGACY_OUTPUT_TYPES = ("video", "cover", "publish_copy")
MAX_LEGACY_VIDEO_BYTES = 2 * 1024 * 1024 * 1024
MAX_LEGACY_COVER_BYTES = 20 * 1024 * 1024
ALLOWED_LEGACY_MIME = {
    "video": frozenset({"video/mp4", "video/quicktime"}),
    "cover": frozenset({"image/png", "image/jpeg"}),
}
_LEGACY_REGISTRATION_LOCKS: dict[str, threading.RLock] = {}
_LEGACY_REGISTRATION_LOCKS_GUARD = threading.Lock()
LEGACY_SOURCE_KEYS = frozenset(
    {
        "source_mode",
        "video_input",
        "source_text",
        "source_label",
        "business_preset_id",
        "business_goal_name",
        "business_script_structure",
        "business_visual_strategy",
        "business_publish_platforms",
        "business_intent_note",
        "ip_profile_url",
        "ip_manual_video_links",
        "ip_learning_video_urls",
        "ip_learning_scripts",
        "ip_learning_selected_topic",
        "ip_learning_requires_topic_confirmation",
        "industry_persona",
        "selling_points",
        "target_customer",
        "conversion_phrase",
        "other_reqs",
    }
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _fingerprint(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _session_revision(session: IpBroadcastSession) -> str:
    source_state = {key: session.state.get(key) for key in sorted(LEGACY_SOURCE_KEYS)}
    return _fingerprint({"session_id": session.session_id, "source_state": source_state})


def _legacy_registration_lock(app_run_id: str) -> threading.RLock:
    with _LEGACY_REGISTRATION_LOCKS_GUARD:
        lock = _LEGACY_REGISTRATION_LOCKS.get(app_run_id)
        if lock is None:
            lock = threading.RLock()
            _LEGACY_REGISTRATION_LOCKS[app_run_id] = lock
        return lock


class IpBroadcastAdapterError(RuntimeError):
    """Base error whose message starts with a stable contract error code."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(f"{code}: {message or code}")


class IpBroadcastInputError(IpBroadcastAdapterError):
    pass


class IpBroadcastSessionError(IpBroadcastAdapterError):
    pass


@dataclass(frozen=True)
class _TrustedRoot:
    root_id: str
    path: Path


@dataclass(frozen=True)
class IpBroadcastBinding:
    binding_id: str
    session_id: str
    project_id: str
    app_run_id: str
    source_revision: str
    context_snapshot_id: str | None = None
    app_id: str = APP_ID
    app_version: str = APP_VERSION
    idempotency_key: str | None = None
    explicit_claim: bool = False
    legacy_state_revision: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class IpBroadcastRunHandle:
    run: AppRun
    binding: IpBroadcastBinding
    session: IpBroadcastSession
    projection: dict[str, Any]


@dataclass(frozen=True)
class IpBroadcastStateProjection:
    when: str
    session_step_status: str
    task_status: str
    app_run_state: str
    completion_allowed: bool
    current_step: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "when": self.when,
            "session_step_status": self.session_step_status,
            "task_status": self.task_status,
            "app_run_state": self.app_run_state,
            "completion_allowed": self.completion_allowed,
            **({"current_step": self.current_step} if self.current_step else {}),
        }


_STATE_PROJECTIONS: dict[str, IpBroadcastStateProjection] = {
    "new_or_not_enqueued": IpBroadcastStateProjection("new_or_not_enqueued", "pending", "pending", "draft", False),
    "queued_for_execution": IpBroadcastStateProjection("queued_for_execution", "ready", "pending", "queued", False),
    "step_running": IpBroadcastStateProjection("step_running", "running", "running", "running", False),
    "user_must_edit_or_confirm": IpBroadcastStateProjection("user_must_edit_or_confirm", "ready", "needs_review", "needs_review", False),
    "waiting_for_login": IpBroadcastStateProjection("waiting_for_login", "ready", "waiting_for_login", "needs_review", False),
    "waiting_for_human": IpBroadcastStateProjection("waiting_for_human", "ready", "waiting_for_human", "needs_review", False),
    "needs_attention": IpBroadcastStateProjection("needs_attention", "error", "needs_attention", "needs_review", False),
    "ip_learning_topic_confirmation": IpBroadcastStateProjection("ip_learning_topic_confirmation", "ready", "needs_review", "needs_review", False, "source"),
    "retryable_step_error": IpBroadcastStateProjection("retryable_step_error", "error", "failed", "failed", False),
    "user_cancelled": IpBroadcastStateProjection("user_cancelled", "error", "cancelled", "cancelled", False),
    "all_outputs_verified": IpBroadcastStateProjection("all_outputs_verified", "done", "completed", "completed", True),
}


def project_legacy_state(when: str, *, current_step: str | None = None) -> IpBroadcastStateProjection:
    """Map a legacy lifecycle event without mutating either state store."""

    if when not in _STATE_PROJECTIONS:
        raise IpBroadcastAdapterError("UNKNOWN_LEGACY_STATE", when)
    base = _STATE_PROJECTIONS[when]
    if when == "ip_learning_topic_confirmation":
        current_step = "source"
    return IpBroadcastStateProjection(
        when=base.when,
        session_step_status=base.session_step_status,
        task_status=base.task_status,
        app_run_state=base.app_run_state,
        completion_allowed=base.completion_allowed,
        current_step=current_step,
    )


def project_session_state(session: IpBroadcastSession, *, app_run_state: str) -> IpBroadcastStateProjection:
    """Project current legacy session facts into the frozen lifecycle matrix.

    ``legacy_lifecycle_state`` is an adapter-owned, optional marker for a
    future workflow step that needs human login/confirmation.  Existing
    sessions need no migration: topic confirmation and error notices are
    inferred from their already persisted fields.
    """

    # Terminal AppRun facts are authoritative even if a stale legacy session
    # marker remains after a restart.
    if app_run_state == "completed":
        return project_legacy_state("all_outputs_verified")
    if app_run_state == "cancelled":
        return project_legacy_state("user_cancelled")
    # Queue/running/failed AppRun facts are authoritative over stale legacy
    # transient markers after a crash or restart.  Human-waiting overlays are
    # only valid while the AppRun is in needs_review.
    if app_run_state == "queued":
        return project_legacy_state("queued_for_execution")
    if app_run_state == "running":
        return project_legacy_state("step_running")
    if app_run_state == "failed":
        return project_legacy_state("retryable_step_error")
    explicit = session.state.get("legacy_lifecycle_state")
    if isinstance(explicit, str) and explicit in _STATE_PROJECTIONS:
        return project_legacy_state(explicit)
    if session.state.get("ip_learning_requires_topic_confirmation"):
        return project_legacy_state("ip_learning_topic_confirmation")
    if any(status == "running" for status in session.step_status.values()):
        return project_legacy_state("step_running")
    if any(notice.get("kind") == "error" for notice in session.notices.values() if isinstance(notice, dict)):
        retryable = any(
            notice.get("retryable") == "true"
            for notice in session.notices.values()
            if isinstance(notice, dict)
        )
        return project_legacy_state("retryable_step_error" if retryable else "needs_attention")
    if app_run_state == "needs_review":
        return project_legacy_state("user_must_edit_or_confirm")
    return project_legacy_state("new_or_not_enqueued")


class IpBroadcastBindingStore:
    """Small atomic JSON store for the cross-store session binding ledger."""

    def __init__(self, store_path: str | Path | None = None):
        raw = Path(store_path) if store_path else Path(get_data_path("app_center", "ip_broadcast_bindings"))
        self._path = raw if raw.suffix == ".json" else raw / "bindings.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._bindings: dict[str, IpBroadcastBinding] = {}
        self._load()

    def get(self, session_id: str) -> IpBroadcastBinding | None:
        return self._bindings.get(session_id)

    def get_by_app_run(self, app_run_id: str) -> IpBroadcastBinding | None:
        return next((item for item in self._bindings.values() if item.app_run_id == app_run_id), None)

    def list_for_session(self, session_id: str) -> list[IpBroadcastBinding]:
        return [item for item in self._bindings.values() if item.session_id == session_id]

    def save(self, binding: IpBroadcastBinding) -> IpBroadcastBinding:
        existing = self._bindings.get(binding.session_id)
        if existing and (
            existing.project_id != binding.project_id
            or existing.app_run_id != binding.app_run_id
            or existing.source_revision != binding.source_revision
            or existing.context_snapshot_id != binding.context_snapshot_id
        ):
            raise IpBroadcastSessionError("SESSION_BINDING_IMMUTABLE", "session binding cannot be overwritten")
        self._bindings[binding.session_id] = binding
        self._write()
        return binding

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise IpBroadcastSessionError("BINDING_STORE_INVALID", str(exc)) from exc
        for payload in raw.get("bindings", []) if isinstance(raw, dict) else []:
            binding = IpBroadcastBinding(**payload)
            self._bindings[binding.session_id] = binding

    def _write(self) -> None:
        payload = {
            "schema_version": 1,
            "bindings": [item.__dict__ for item in sorted(self._bindings.values(), key=lambda value: value.session_id)],
        }
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self._path)


class IpBroadcastAppAdapter:
    """Bind the legacy IP workflow to an AppRun without enabling providers."""

    app_id = APP_ID
    app_version = APP_VERSION

    def __init__(
        self,
        repository: AppCenterRepository,
        *,
        session_store: IpBroadcastSessionStore | None = None,
        binding_store: IpBroadcastBindingStore | None = None,
        task_projector: Any | None = None,
        enforce_feature_flag: bool = True,
        trusted_roots: Sequence[str | Path] | None = None,
    ):
        self.repository = repository
        self.session_store = session_store or IpBroadcastSessionStore()
        self.binding_store = binding_store or IpBroadcastBindingStore()
        self.task_projector = task_projector
        self.enforce_feature_flag = enforce_feature_flag
        self._trusted_roots = self._build_trusted_roots(trusted_roots)

    @staticmethod
    def _build_trusted_roots(trusted_roots: Sequence[str | Path] | None) -> tuple[_TrustedRoot, ...]:
        """Build an explicit allowlist for legacy media imports.

        The production default is deliberately limited to Pixelle's data,
        output and temp directories.  Tests and a future desktop resolver may
        inject a narrower directory.  No arbitrary user path is accepted.
        """

        if trusted_roots is None:
            candidates: list[tuple[str, str | Path]] = [
                ("data", get_data_path()),
                ("output", get_output_path()),
                ("temp", get_temp_path()),
            ]
        else:
            candidates = [(f"custom-{index}", value) for index, value in enumerate(trusted_roots)]
        result: list[_TrustedRoot] = []
        seen: set[str] = set()
        for root_id, raw in candidates:
            path = Path(raw).expanduser().resolve()
            key = os.fspath(path)
            if key in seen:
                continue
            path.mkdir(parents=True, exist_ok=True)
            result.append(_TrustedRoot(root_id, path))
            seen.add(key)
        return tuple(result)

    def _ensure_entry_enabled(self) -> None:
        if not self.enforce_feature_flag:
            return
        manifest = get_app(self.app_id)
        if manifest is None or not manifest.get("enabled"):
            raise IpBroadcastAdapterError("APP_FEATURE_DISABLED", "digitalHumanInAppCenter")
        if manifest.get("readiness", {}).get("status") != "ready":
            raise IpBroadcastAdapterError("APP_NOT_READY", str(manifest.get("readiness", {}).get("missing_capabilities", [])))

    def validate_input(self, project_id: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        """Validate and normalize source facts; return a pinned revision."""

        if not isinstance(input_payload, dict):
            raise IpBroadcastInputError("INPUT_PAYLOAD_INVALID")
        payload_project_id = input_payload.get("project_id")
        if payload_project_id is not None and payload_project_id != project_id:
            raise IpBroadcastInputError("PROJECT_ID_MISMATCH")
        try:
            self.repository.get_project(project_id)
        except NotFound as exc:
            raise IpBroadcastInputError("PROJECT_NOT_FOUND", project_id) from exc
        payload = dict(input_payload)
        resume_mode = payload.get("resume_mode", "new_session")
        if resume_mode not in RESUME_MODES:
            raise IpBroadcastInputError("RESUME_MODE_INVALID", str(resume_mode))
        session_reference = str(payload.get("session_id") or "") if resume_mode == "resume_existing" else None
        if resume_mode == "resume_existing":
            if not str(payload.get("session_id") or "").strip():
                raise IpBroadcastInputError("SESSION_ID_REQUIRED")
            # A resume may rely on the current legacy session state; source
            # fields are optional but, when supplied, are still validated.
            if not payload.get("source_mode"):
                session = self.session_store.get_session(str(payload["session_id"]))
                if session is None:
                    raise IpBroadcastSessionError("SESSION_NOT_FOUND", str(payload["session_id"]))
                return {
                    "resume_mode": resume_mode,
                    "session_id": session_reference,
                    "source_revision": _session_revision(session),
                    "source_artifact_version_ids": [],
                }

        mode = payload.get("source_mode")
        if mode not in SOURCE_MODES:
            raise IpBroadcastInputError("SOURCE_MODE_REQUIRED", str(mode))
        source_ids = payload.get("source_artifact_version_ids", [])
        if not isinstance(source_ids, list):
            raise IpBroadcastInputError("SOURCE_ARTIFACT_VERSION_IDS_INVALID")
        if mode == "blank_project":
            if source_ids:
                raise IpBroadcastInputError("SOURCE_MODE_EXACTLY_ONE", "blank_project cannot carry source versions")
            goal = str(payload.get("goal") or "").strip()
            if not goal:
                raise IpBroadcastInputError("GOAL_REQUIRED")
            return {
                "resume_mode": resume_mode,
                "session_id": session_reference,
                "source_mode": mode,
                "goal": goal,
                "source_artifact_version_ids": [],
                "source_revision": _fingerprint({"mode": mode, "goal": goal}),
            }
        if len(source_ids) != 1:
            raise IpBroadcastInputError("SOURCE_MODE_EXACTLY_ONE")
        version = self._get_source_version(project_id, str(source_ids[0]), mode)
        content = version.content if isinstance(version.content, dict) else {}
        if mode == "copywriting":
            index = payload.get("selected_variant_index")
            if isinstance(index, bool) or not isinstance(index, int):
                raise IpBroadcastInputError("COPYWRITING_VARIANT_REQUIRED")
            variants = content.get("variants") if isinstance(content.get("variants"), list) else []
            if index < 0 or index >= len(variants):
                raise IpBroadcastInputError("COPYWRITING_VARIANT_REQUIRED")
            selected = variants[index] if isinstance(variants[index], dict) else {}
            full_text = str(selected.get("full_text") or "").strip()
            if not full_text:
                raise IpBroadcastInputError("COPYWRITING_VARIANT_REQUIRED")
            revision = _fingerprint({"version_id": version.artifact_version_id, "fingerprint": version.content_fingerprint, "index": index})
            return {
                "resume_mode": resume_mode,
                "session_id": session_reference,
                "source_mode": mode,
                "source_artifact_version_ids": [version.artifact_version_id],
                "selected_variant_index": index,
                "source_revision": revision,
            }
        title = str(content.get("title") or "").strip()
        if not title:
            raise IpBroadcastInputError("SELECTED_TITLE_REQUIRED")
        return {
            "resume_mode": resume_mode,
            "session_id": session_reference,
            "source_mode": mode,
            "source_artifact_version_ids": [version.artifact_version_id],
            "source_revision": _fingerprint({"version_id": version.artifact_version_id, "fingerprint": version.content_fingerprint, "title": title}),
        }

    def create_or_resume(
        self,
        project_id: str,
        input_payload: dict[str, Any],
        *,
        idempotency_key: str,
        explicit_claim: bool = False,
        context_snapshot_id: str | None = None,
        prompt_version: str | None = None,
    ) -> IpBroadcastRunHandle:
        self._ensure_entry_enabled()
        if not str(idempotency_key or "").strip():
            raise IpBroadcastInputError("IDEMPOTENCY_KEY_REQUIRED")
        try:
            validate_business_payload(input_payload, label="IP broadcast AppRun input")
        except ValueError as exc:
            raise IpBroadcastInputError("INPUT_PAYLOAD_INVALID", str(exc)) from exc
        normalized = self.validate_input(project_id, input_payload)
        resume_mode = normalized["resume_mode"]
        existing = next((run for run in self.repository.list_app_runs() if run.idempotency_key == idempotency_key), None)
        if existing is not None:
            if existing.project_id != project_id or existing.app_id != self.app_id or existing.app_version != self.app_version:
                raise IpBroadcastSessionError("IDEMPOTENCY_CONFLICT", idempotency_key)
            if existing.context_snapshot_id != context_snapshot_id:
                raise IpBroadcastSessionError("APP_RUN_BINDING_MISMATCH", idempotency_key)
            binding = self.binding_store.get_by_app_run(existing.app_run_id)
            if binding is None:
                raise IpBroadcastSessionError("BINDING_MISSING", existing.app_run_id)
            if not normalized.get("source_mode") and binding.legacy_state_revision:
                session = self.session_store.get_session(binding.session_id)
                if session is None:
                    raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
                if _session_revision(session) != binding.legacy_state_revision:
                    raise IpBroadcastSessionError("SESSION_STATE_REVISION_MISMATCH", binding.session_id)
            if binding.source_revision != normalized["source_revision"]:
                raise IpBroadcastSessionError("SOURCE_REVISION_MISMATCH", "idempotent replay must use the pinned source")
            return self._handle(existing, binding)

        session_id = normalized.get("session_id")
        binding = self.binding_store.get(session_id) if session_id else None
        session: IpBroadcastSession
        if resume_mode == "resume_existing":
            session = self.session_store.get_session(str(session_id))  # type: ignore[arg-type]
            if session is None:
                raise IpBroadcastSessionError("SESSION_NOT_FOUND", str(session_id))
            if binding is not None:
                if binding.project_id != project_id:
                    raise IpBroadcastSessionError("SESSION_PROJECT_MISMATCH", str(session_id))
                if input_payload.get("app_run_id") and input_payload["app_run_id"] != binding.app_run_id:
                    raise IpBroadcastSessionError("APP_RUN_SESSION_MISMATCH", str(input_payload["app_run_id"]))
                if normalized.get("source_mode") and normalized["source_revision"] != binding.source_revision:
                    raise IpBroadcastSessionError("SOURCE_REVISION_MISMATCH", "resume must use the pinned source")
                if binding.legacy_state_revision and _session_revision(session) != binding.legacy_state_revision:
                    raise IpBroadcastSessionError("SESSION_STATE_REVISION_MISMATCH", str(session_id))
                current = self.repository.get_app_run(binding.app_run_id)
                if current.state not in TERMINAL_APP_RUN_STATES:
                    return self._handle(current, binding)
                # A terminal run can be resumed only by an explicit new
                # attempt in a later implementation batch; fail closed here.
                raise IpBroadcastSessionError("SESSION_RUN_TERMINAL", binding.app_run_id)
            if not explicit_claim:
                raise IpBroadcastSessionError("LEGACY_SESSION_EXPLICIT_CLAIM_REQUIRED", str(session_id))
            if any(item.project_id != project_id for item in self.binding_store.list_for_session(str(session_id))):
                raise IpBroadcastSessionError("SESSION_PROJECT_MISMATCH", str(session_id))
            normalized["source_revision"] = normalized.get("source_revision") or _session_revision(session)
        else:
            session = self.session_store.create_session()

        run_payload = {
            **dict(input_payload),
            **normalized,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "project_id": project_id,
            "session_id": session.session_id,
        }
        run = self.repository.create_app_run(
            project_id,
            self.app_id,
            self.app_version,
            run_payload,
            idempotency_key=idempotency_key,
            context_snapshot_id=context_snapshot_id,
            prompt_version=prompt_version,
            session_id=session.session_id,
        )
        now = _now()
        binding = IpBroadcastBinding(
            binding_id=f"binding_{uuid.uuid4().hex}",
            session_id=session.session_id,
            project_id=project_id,
            app_run_id=run.app_run_id,
            source_revision=normalized["source_revision"],
            context_snapshot_id=run.context_snapshot_id,
            idempotency_key=idempotency_key,
            explicit_claim=explicit_claim,
            legacy_state_revision=_session_revision(session) if explicit_claim else None,
            created_at=now,
            updated_at=now,
        )
        try:
            self.binding_store.save(binding)
        except Exception:
            # The AppRun is still an auditable fact.  Do not silently create a
            # second run; surface the binding failure for operator repair.
            raise
        return self._handle(run, binding)

    def reconcile(self, session_id: str, *, project_id: str, app_run_id: str | None = None) -> IpBroadcastRunHandle:
        session = self.session_store.get_session(session_id)
        if session is None:
            raise IpBroadcastSessionError("SESSION_NOT_FOUND", session_id)
        binding = self.binding_store.get(session_id)
        if binding is None:
            raise IpBroadcastSessionError("LEGACY_SESSION_EXPLICIT_CLAIM_REQUIRED", session_id)
        if binding.project_id != project_id:
            raise IpBroadcastSessionError("SESSION_PROJECT_MISMATCH", session_id)
        if app_run_id and app_run_id != binding.app_run_id:
            raise IpBroadcastSessionError("APP_RUN_SESSION_MISMATCH", app_run_id)
        run = self.repository.get_app_run(binding.app_run_id)
        return self._handle(run, binding)

    def cancel(self, app_run_id: str) -> IpBroadcastRunHandle:
        binding = self.binding_store.get_by_app_run(app_run_id)
        if binding is None:
            raise IpBroadcastSessionError("BINDING_MISSING", app_run_id)
        run = self.repository.cancel_app_run(app_run_id)
        session = self.session_store.get_session(binding.session_id)
        if session is None:
            raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
        if run.state == "cancelled":
            session.step_status[6] = "error"
            self.session_store.save_session(session)
        return self._handle(run, binding)

    def retry(self, app_run_id: str) -> IpBroadcastRunHandle:
        self._ensure_entry_enabled()
        binding = self.binding_store.get_by_app_run(app_run_id)
        if binding is None:
            raise IpBroadcastSessionError("BINDING_MISSING", app_run_id)
        try:
            run = self.repository.retry_app_run(app_run_id)
        except InvalidAppRunTransition as exc:
            raise IpBroadcastSessionError("APP_RUN_STATE_INVALID", str(exc)) from exc
        session = self.session_store.get_session(binding.session_id)
        if session is None:
            raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
        for step, status in list(session.step_status.items()):
            if status in {"running", "error"}:
                session.step_status[step] = "ready"
        if not any(status == "ready" for status in session.step_status.values()):
            session.step_status[6] = "ready"
        session.notices = {
            step: notice
            for step, notice in session.notices.items()
            if not isinstance(notice, dict) or notice.get("kind") != "error"
        }
        session.state.pop("legacy_lifecycle_state", None)
        session.state["ip_learning_requires_topic_confirmation"] = False
        self.session_store.save_session(session)
        return self._handle(run, binding)

    async def execute_local(self, app_run_id: str, *, context_snapshot_id: str | None = None) -> IpBroadcastRunHandle:
        """Execute the deterministic local bridge without provider side effects.

        This seam is deliberately available only to an explicitly isolated
        adapter (`enforce_feature_flag=False`).  It exercises the real
        AppRunner, attempt and task projection while preserving the strict
        binding/replay/accept boundaries used by the production adapter.
        """

        if self.enforce_feature_flag:
            self._ensure_entry_enabled()
            raise IpBroadcastAdapterError("APP_EXECUTOR_LOCAL_ONLY", self.app_id)
        with _legacy_registration_lock(app_run_id):
            binding = self.binding_store.get_by_app_run(app_run_id)
            if binding is None:
                raise IpBroadcastSessionError("BINDING_MISSING", app_run_id)
            run = self.repository.get_app_run(app_run_id)
            self._assert_execution_binding(run, binding, context_snapshot_id=context_snapshot_id)
            if run.state == "running":
                # A running AppRun observed after a process/sidecar restart
                # cannot safely be resumed by a new local executor instance.
                # Convert the orphaned attempt to a retryable failure instead
                # of leaving the run permanently stuck in running.
                attempts = self.repository.list_attempts(app_run_id)
                if attempts and attempts[-1].state == "running":
                    self.repository.update_attempt(
                        attempts[-1].attempt_id,
                        state="failed",
                        error_code="APP_EXECUTOR_INTERRUPTED",
                        error_message="isolated executor was interrupted before restart",
                        diagnostic_json={"type": "APP_EXECUTOR_INTERRUPTED"},
                        completed_at=run.updated_at,
                    )
                failed = self.repository.transition_app_run(app_run_id, "failed")
                failed = self.repository.set_app_run_error(app_run_id, "APP_EXECUTOR_INTERRUPTED")
                session = self.session_store.get_session(binding.session_id)
                if session is not None:
                    session.step_status[6] = "error"
                    self.session_store.save_session(session)
                return self._handle(failed, binding)
            if run.state == "needs_review":
                attempts = self.repository.list_attempts(app_run_id)
                if attempts and attempts[-1].state == "needs_review" and run.output_artifact_ids:
                    sources = []
                    for artifact_id in run.output_artifact_ids:
                        artifact = self.repository.get_artifact(artifact_id)
                        if artifact.current_version_id:
                            version = self.repository.get_artifact_version(artifact.current_version_id)
                            sources.append(version.source)
                    if sources and all(source == "generated" for source in sources):
                        local_fingerprint = self._local_output_fingerprint(run)
                        diagnostic = attempts[-1].diagnostic or {}
                        stored_fingerprint = diagnostic.get("local_output_fingerprint")
                        if stored_fingerprint is not None and stored_fingerprint != local_fingerprint:
                            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", app_run_id)
                        if stored_fingerprint is None:
                            self.repository.update_attempt(
                                attempts[-1].attempt_id,
                                diagnostic_json={"local_output_fingerprint": local_fingerprint},
                            )
                return self._handle(self.repository.get_app_run(app_run_id), binding)
            if run.state in {"completed", "cancelled"}:
                return self._handle(run, binding)
            session = self.session_store.get_session(binding.session_id)
            if session is None:
                raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
            session.step_status[6] = "running"
            self.session_store.save_session(session)

            output = self._local_executor_output(run)

            class _LocalExecutor:
                async def execute(self, _run: AppRun) -> ExecutorOutput:
                    if _run.input_payload.get("__local_executor_error"):
                        raise RuntimeError("isolated executor failure")
                    return output

            runner = AppRunner(
                self.repository,
                executors={self.app_id: _LocalExecutor()},
                task_projector=self.task_projector,
                enforce_readiness=False,
            )
            try:
                result = await runner.run(app_run_id)
            except Exception:
                current = self.repository.get_app_run(app_run_id)
                session = self.session_store.get_session(binding.session_id)
                if session is not None and current.state not in {"needs_review", "completed"}:
                    session.step_status[6] = "error"
                    self.session_store.save_session(session)
                raise
            session = self.session_store.get_session(binding.session_id)
            if session is None:
                raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
            if result.output_artifact_ids:
                for artifact_id in result.output_artifact_ids:
                    artifact = self.repository.get_artifact(artifact_id)
                    session.artifacts[artifact.artifact_type] = artifact_id
                attempts = self.repository.list_attempts(app_run_id)
                if attempts and result.state == "needs_review":
                    self.repository.update_attempt(
                        attempts[-1].attempt_id,
                        diagnostic_json={"local_output_fingerprint": self._local_output_fingerprint(result)},
                    )
            session.step_status[6] = "ready" if result.state == "needs_review" else ("error" if result.state in {"failed", "cancelled"} else session.step_status.get(6, "pending"))
            self.session_store.save_session(session)
            return self._handle(result, binding)

    @staticmethod
    def _local_executor_output(run: AppRun) -> ExecutorOutput:
        source_mode = str(run.input_payload.get("source_mode") or "resume_existing")
        session_id = run.session_id or "unknown-session"
        return ExecutorOutput(
            artifact_type="video",
            name="本地隔离口播视频",
            content={"fake": True, "source_mode": source_mode, "session_id": session_id},
            related_artifacts=[
                RelatedArtifactOutput("cover", "cover", "本地隔离封面", content={"fake": True, "source_mode": source_mode}),
                RelatedArtifactOutput(
                    "publish_copy",
                    "publish_copy",
                    "本地隔离发布文案",
                    content={"schema_version": 1, "artifact_type": "publish_copy", "title": "本地隔离口播", "description": "本地隔离执行结果", "hashtags": ["本地隔离"]},
                ),
            ],
            provider_class="local-isolated",
            model_ref="local-default:isolated",
        )

    async def run_fake(self, app_run_id: str) -> IpBroadcastRunHandle:
        """Backward-compatible alias for the isolated local executor seam."""

        return await self.execute_local(app_run_id)

    async def accept_fake(self, app_run_id: str) -> IpBroadcastRunHandle:
        self._ensure_entry_enabled()
        if self.enforce_feature_flag:
            # Production callers must use the imported-output review guard;
            # the fake shortcut is retained only for explicitly isolated
            # local tests (`enforce_feature_flag=False`).
            return self.accept_legacy_outputs(app_run_id)
        return self.accept_local_outputs(app_run_id)

    def accept_local_outputs(self, app_run_id: str) -> IpBroadcastRunHandle:
        """Explicitly accept an isolated generated output set.

        Local outputs are not legacy imports, so they use a separate
        deterministic fingerprint.  They still require the same binding,
        attempt, exact-output and review-state guards as the production
        imported-output accept path.
        """

        if self.enforce_feature_flag:
            raise IpBroadcastAdapterError("APP_EXECUTOR_LOCAL_ONLY", self.app_id)
        with _legacy_registration_lock(app_run_id):
            binding = self.binding_store.get_by_app_run(app_run_id)
            if binding is None:
                raise IpBroadcastSessionError("BINDING_MISSING", app_run_id)
            run = self.repository.get_app_run(app_run_id)
            self._assert_accept_binding(run, binding)
            attempts = self.repository.list_attempts(app_run_id)
            if run.state == "completed":
                if not attempts or attempts[-1].state != "completed":
                    raise IpBroadcastSessionError("ARTIFACT_REVIEW_ATTEMPT_REQUIRED", app_run_id)
                local_fingerprint = self._local_output_fingerprint(run)
                diagnostic = attempts[-1].diagnostic or {}
                if diagnostic.get("local_output_fingerprint") != local_fingerprint:
                    raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", app_run_id)
                session = self.session_store.get_session(binding.session_id)
                if session is None:
                    raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
                if session.step_status.get(6) != "done":
                    session.step_status[6] = "done"
                    self.session_store.save_session(session)
                return self._handle(run, binding)
            if run.state != "needs_review":
                raise IpBroadcastSessionError("ARTIFACT_OUTPUT_STATE_INVALID", run.state)
            if not attempts or attempts[-1].state != "needs_review":
                raise IpBroadcastSessionError("ARTIFACT_REVIEW_ATTEMPT_REQUIRED", app_run_id)
            fingerprint = self._local_output_fingerprint(run)
            diagnostic = attempts[-1].diagnostic or {}
            if diagnostic.get("local_output_fingerprint") != fingerprint:
                raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", app_run_id)
            completed = AppRunner(self.repository, enforce_readiness=False).accept_output(app_run_id)
            session = self.session_store.get_session(binding.session_id)
            if session is None:
                raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
            session.step_status[6] = "done"
            self.session_store.save_session(session)
            return self._handle(completed, binding)

    def register_legacy_outputs(self, app_run_id: str) -> IpBroadcastRunHandle:
        """Serialize one AppRun's import and make replay idempotent."""

        with _legacy_registration_lock(app_run_id):
            return self._register_legacy_outputs_locked(app_run_id)

    def _register_legacy_outputs_locked(self, app_run_id: str) -> IpBroadcastRunHandle:
        """Import already-produced legacy outputs as immutable AppCenter facts.

        This method is intentionally read-only with respect to the legacy
        workflow: it never invokes a provider or a browser and only accepts a
        bound ``needs_review`` AppRun whose existing files pass the trusted
        root and media checks.  ``imported`` is the repository's existing
        source value for this historical handoff; the source session and run
        remain explicit in the content and parent artifact fields.
        """

        self._ensure_entry_enabled()
        binding = self.binding_store.get_by_app_run(app_run_id)
        if binding is None:
            raise IpBroadcastSessionError("BINDING_MISSING", app_run_id)
        run = self.repository.get_app_run(app_run_id)
        if run.project_id != binding.project_id:
            raise IpBroadcastSessionError("SESSION_PROJECT_MISMATCH", binding.session_id)
        if run.state != "needs_review":
            raise IpBroadcastSessionError("ARTIFACT_OUTPUT_STATE_INVALID", run.state)
        session = self.session_store.get_session(binding.session_id)
        if session is None:
            raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)

        source_artifacts = [
            artifact
            for artifact in self.repository.list_artifacts(run.project_id, include_archived=True)
            if artifact.source_app_run_id == run.app_run_id
        ]
        if source_artifacts and not any(artifact.artifact_type in LEGACY_OUTPUT_TYPES for artifact in source_artifacts):
            raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_CONFLICT", app_run_id)
        existing = self._existing_legacy_output_versions(run)
        if existing:
            if set(existing) != set(LEGACY_OUTPUT_TYPES):
                raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_PARTIAL", app_run_id)
            existing_versions = {
                artifact_type: self.repository.get_artifact_version(version_id)
                for artifact_type, version_id in existing.items()
            }
            fingerprint = self._legacy_output_fingerprint(existing_versions)
            # A prior complete import is the idempotency anchor.  Do not
            # re-read or replace files if a user changed the legacy session
            # after the fact; the immutable versions remain the audit record.
            expected_artifact_ids = {
                self.repository.get_artifact_version(version_id).artifact_id for version_id in existing.values()
            }
            if set(run.output_artifact_ids) not in (set(), expected_artifact_ids):
                raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_CONFLICT", app_run_id)
            self._ensure_legacy_review_attempt(run, fingerprint)
            if run.output_artifact_ids:
                return self._handle(run, binding)
            repaired = self.repository.set_output_artifacts(
                app_run_id,
                [
                    self.repository.get_artifact_version(existing[artifact_type]).artifact_id
                    for artifact_type in LEGACY_OUTPUT_TYPES
                ],
            )
            return self._handle(repaired, binding)

        if run.output_artifact_ids:
            raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_CONFLICT", app_run_id)

        video_path = self._legacy_path(session, ("final_video", "digital_human_video"), "video")
        cover_path = self._legacy_path(session, ("cover",), "cover")
        video_ref = self._validate_legacy_file(video_path, artifact_type="video")
        cover_ref = self._validate_legacy_file(cover_path, artifact_type="cover")
        publish_copy = self._legacy_publish_copy(session)
        fingerprint = self._legacy_output_fingerprint_from_refs(video_ref, cover_ref, publish_copy)
        publish_copy["legacy_output_fingerprint"] = fingerprint
        review_attempt, review_attempt_created = self._ensure_legacy_review_attempt(run, fingerprint)

        # Validate every input before the first write, preventing normal
        # malformed sessions from leaving a partial three-artifact batch.
        output_specs = (
            ("video", "既有数字人口播视频", None, [video_ref]),
            ("cover", "既有视频封面", None, [cover_ref]),
            ("publish_copy", "既有发布文案", publish_copy, []),
        )
        created_artifact_ids: list[str] = []
        artifact_ids: list[str] = []
        try:
            for artifact_type, name, content, file_refs in output_specs:
                artifact = self.repository.create_artifact(
                    run.project_id,
                    artifact_type,
                    name,
                    source_app_run_id=app_run_id,
                )
                created_artifact_ids.append(artifact.artifact_id)
                version = self.repository.append_artifact_version(
                    artifact.artifact_id,
                    content=content,
                    file_refs=file_refs,
                    source=LEGACY_ARTIFACT_SOURCE,
                )
                artifact_ids.append(version.artifact_id)
            updated = self.repository.set_output_artifacts(app_run_id, artifact_ids)
        except Exception:
            # Compensate only this invocation; never delete older artifacts
            # owned by the same AppRun.
            self.repository.purge_artifacts_by_ids(created_artifact_ids)
            if review_attempt_created:
                self.repository.delete_attempt(review_attempt.attempt_id)
            raise

        return self._handle(updated, binding)

    def accept_legacy_outputs(self, app_run_id: str) -> IpBroadcastRunHandle:
        """Complete only an explicitly reviewed, imported legacy output set."""

        self._ensure_entry_enabled()
        with _legacy_registration_lock(app_run_id):
            binding = self.binding_store.get_by_app_run(app_run_id)
            if binding is None:
                raise IpBroadcastSessionError("BINDING_MISSING", app_run_id)
            run = self.repository.get_app_run(app_run_id)
            self._assert_accept_binding(run, binding)
            versions = self._legacy_output_versions(run)
            expected_artifact_ids = {version.artifact_id for version in versions.values()}
            if set(run.output_artifact_ids) != expected_artifact_ids:
                raise IpBroadcastSessionError("ARTIFACT_OUTPUT_BINDING_MISMATCH", app_run_id)
            if run.state == "completed":
                session = self.session_store.get_session(binding.session_id)
                if session is None:
                    raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
                attempts = self.repository.list_attempts(app_run_id)
                if attempts and attempts[-1].state == "needs_review":
                    self.repository.update_attempt(
                        attempts[-1].attempt_id,
                        state="completed",
                        completed_at=run.completed_at or run.updated_at,
                    )
                if session.step_status.get(6) != "done":
                    session.step_status[6] = "done"
                    self.session_store.save_session(session)
                return self._handle(run, binding)
            if run.state != "needs_review":
                raise IpBroadcastSessionError("ARTIFACT_OUTPUT_STATE_INVALID", run.state)
            fingerprint = self._legacy_output_fingerprint(versions)
            attempts = self.repository.list_attempts(app_run_id)
            if not attempts or attempts[-1].state != "needs_review":
                raise IpBroadcastSessionError("ARTIFACT_REVIEW_ATTEMPT_REQUIRED", app_run_id)
            diagnostic = attempts[-1].diagnostic or {}
            if diagnostic.get("legacy_output_fingerprint") != fingerprint:
                raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", app_run_id)
            runner = AppRunner(self.repository, enforce_readiness=False)
            try:
                completed = runner.accept_output(app_run_id)
            except Exception as exc:
                raise IpBroadcastSessionError("ARTIFACT_ACCEPT_INVALID", str(exc)) from exc
            session = self.session_store.get_session(binding.session_id)
            if session is None:
                raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
            session.step_status[6] = "done"
            self.session_store.save_session(session)
            return self._handle(completed, binding)

    def _existing_legacy_output_versions(self, run: AppRun) -> dict[str, str]:
        """Return current imported versions keyed by output type, if any."""

        found: dict[str, str] = {}
        for artifact in self.repository.list_artifacts(run.project_id, include_archived=True):
            if artifact.source_app_run_id != run.app_run_id or artifact.artifact_type not in LEGACY_OUTPUT_TYPES:
                continue
            if artifact.status == "archived":
                raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_PARTIAL", run.app_run_id)
            if not artifact.current_version_id:
                raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_PARTIAL", run.app_run_id)
            version = self.repository.get_artifact_version(artifact.current_version_id)
            if version.source != LEGACY_ARTIFACT_SOURCE:
                raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_PARTIAL", run.app_run_id)
            if artifact.artifact_type in found:
                raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_CONFLICT", run.app_run_id)
            found[artifact.artifact_type] = version.artifact_version_id
        return found

    def _legacy_output_versions(self, run: AppRun) -> dict[str, ArtifactVersion]:
        existing = self._existing_legacy_output_versions(run)
        if set(existing) != set(LEGACY_OUTPUT_TYPES):
            raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_PARTIAL", run.app_run_id)
        return {
            artifact_type: self.repository.get_artifact_version(version_id)
            for artifact_type, version_id in existing.items()
        }

    @staticmethod
    def _legacy_output_fingerprint_from_refs(
        video_ref: dict[str, Any],
        cover_ref: dict[str, Any],
        publish_copy: dict[str, Any],
    ) -> str:
        canonical_copy = {
            key: value
            for key, value in publish_copy.items()
            if key not in {"legacy_output_fingerprint", "source_session_id"}
        }
        return _fingerprint(
            {
                "video_sha256": video_ref.get("sha256"),
                "cover_sha256": cover_ref.get("sha256"),
                "publish_copy": canonical_copy,
            }
        )

    def _legacy_output_fingerprint(self, versions: dict[str, ArtifactVersion]) -> str:
        if set(versions) != set(LEGACY_OUTPUT_TYPES):
            raise IpBroadcastSessionError("ARTIFACT_REGISTRATION_PARTIAL", "output types")
        video_refs = versions["video"].file_refs
        cover_refs = versions["cover"].file_refs
        if len(video_refs) != 1 or len(cover_refs) != 1:
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", "media refs")
        self._validate_stored_file_ref(video_refs[0], artifact_type="video")
        self._validate_stored_file_ref(cover_refs[0], artifact_type="cover")
        publish_content = versions["publish_copy"].content
        if not isinstance(publish_content, dict):
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", "publish copy")
        self._validate_stored_publish_copy(publish_content)
        computed = self._legacy_output_fingerprint_from_refs(video_refs[0], cover_refs[0], publish_content)
        stored = publish_content.get("legacy_output_fingerprint")
        if stored is not None and stored != computed:
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", "stored fingerprint")
        return computed

    def _local_output_fingerprint(self, run: AppRun) -> str:
        if len(set(run.output_artifact_ids)) != len(run.output_artifact_ids) or not run.output_artifact_ids:
            raise IpBroadcastSessionError("ARTIFACT_OUTPUT_BINDING_MISMATCH", run.app_run_id)
        output_facts: list[dict[str, Any]] = []
        output_types: set[str] = set()
        for artifact_id in run.output_artifact_ids:
            artifact = self.repository.get_artifact(artifact_id)
            if artifact.source_app_run_id != run.app_run_id or artifact.status == "archived" or not artifact.current_version_id:
                raise IpBroadcastSessionError("ARTIFACT_OUTPUT_BINDING_MISMATCH", run.app_run_id)
            version = self.repository.get_artifact_version(artifact.current_version_id)
            if version.source != "generated" or artifact.artifact_type in output_types:
                raise IpBroadcastSessionError("ARTIFACT_OUTPUT_BINDING_MISMATCH", run.app_run_id)
            output_types.add(artifact.artifact_type)
            output_facts.append(
                {
                    "artifact_type": artifact.artifact_type,
                    "content": version.content,
                    "file_refs": version.file_refs,
                    "content_fingerprint": version.content_fingerprint,
                }
            )
        if output_types != set(LEGACY_OUTPUT_TYPES):
            raise IpBroadcastSessionError("ARTIFACT_OUTPUT_BINDING_MISMATCH", run.app_run_id)
        return _fingerprint(sorted(output_facts, key=lambda item: item["artifact_type"]))

    def _validate_stored_file_ref(self, file_ref: dict[str, Any], *, artifact_type: str) -> None:
        if not isinstance(file_ref, dict):
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", "file ref")
        root_id = str(file_ref.get("root") or "")
        root = next((item for item in self._trusted_roots if item.root_id == root_id), None)
        relative_path = str(file_ref.get("relative_path") or "")
        normalized_relative = relative_path.replace("\\", "/")
        if root is None or not relative_path or Path(relative_path).is_absolute() or any(
            part in {"", ".", ".."} for part in normalized_relative.split("/")
        ):
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", "file ref path")
        mime_type = file_ref.get("mime_type")
        digest = str(file_ref.get("sha256") or "")
        size_bytes = file_ref.get("size_bytes")
        if (
            file_ref.get("kind") != artifact_type
            or mime_type not in ALLOWED_LEGACY_MIME[artifact_type]
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
            or isinstance(size_bytes, bool)
            or not isinstance(size_bytes, int)
            or size_bytes <= 0
        ):
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", "file ref metadata")
        candidate = (root.path / relative_path).resolve(strict=False)
        try:
            candidate.relative_to(root.path)
        except ValueError as exc:
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", "file ref root") from exc
        observed = self._validate_legacy_file(str(candidate), artifact_type=artifact_type)
        for key in ("file_key", "root", "relative_path", "kind", "mime_type", "sha256", "size_bytes"):
            if observed.get(key) != file_ref.get(key):
                raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", f"file ref {key}")

    @staticmethod
    def _validate_stored_publish_copy(content: dict[str, Any]) -> None:
        title = content.get("title")
        description = content.get("description")
        hashtags = content.get("hashtags")
        if (
            content.get("schema_version") != 1
            or content.get("artifact_type") != "publish_copy"
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(description, str)
            or not description.strip()
            or not isinstance(hashtags, list)
            or any(not isinstance(item, str) or not item.strip() for item in hashtags)
        ):
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", "publish copy fields")
        try:
            validate_business_payload(content, label="legacy publish copy")
        except ValueError as exc:
            raise IpBroadcastSessionError("ARTIFACT_FINGERPRINT_MISMATCH", str(exc)) from exc

    def _ensure_legacy_review_attempt(self, run: AppRun, fingerprint: str):
        try:
            return self.repository.ensure_review_attempt(run.app_run_id, fingerprint=fingerprint)
        except AppCenterRepositoryError as exc:
            if "ARTIFACT_REVIEW_ATTEMPT_CONFLICT" in str(exc):
                raise IpBroadcastSessionError("ARTIFACT_REVIEW_ATTEMPT_CONFLICT", run.app_run_id) from exc
            raise

    @staticmethod
    def _assert_accept_binding(run: AppRun, binding: IpBroadcastBinding) -> None:
        if run.project_id != binding.project_id:
            raise IpBroadcastSessionError("SESSION_PROJECT_MISMATCH", binding.project_id)
        if run.app_id != binding.app_id or run.app_version != binding.app_version:
            raise IpBroadcastSessionError("APP_RUN_BINDING_MISMATCH", run.app_run_id)
        if run.session_id != binding.session_id:
            raise IpBroadcastSessionError("APP_RUN_SESSION_MISMATCH", run.app_run_id)
        if run.context_snapshot_id != binding.context_snapshot_id:
            raise IpBroadcastSessionError("APP_RUN_BINDING_MISMATCH", run.app_run_id)

    @staticmethod
    def _assert_execution_binding(
        run: AppRun,
        binding: IpBroadcastBinding,
        *,
        context_snapshot_id: str | None = None,
    ) -> None:
        if run.project_id != binding.project_id:
            raise IpBroadcastSessionError("SESSION_PROJECT_MISMATCH", run.app_run_id)
        if run.app_id != binding.app_id or run.app_version != binding.app_version:
            raise IpBroadcastSessionError("APP_RUN_BINDING_MISMATCH", run.app_run_id)
        if run.session_id != binding.session_id:
            raise IpBroadcastSessionError("APP_RUN_SESSION_MISMATCH", run.app_run_id)
        if run.context_snapshot_id != binding.context_snapshot_id:
            raise IpBroadcastSessionError("APP_RUN_BINDING_MISMATCH", run.app_run_id)
        if context_snapshot_id is not None and context_snapshot_id != run.context_snapshot_id:
            raise IpBroadcastSessionError("APP_RUN_BINDING_MISMATCH", run.app_run_id)
        if run.input_payload.get("source_revision") != binding.source_revision:
            raise IpBroadcastSessionError("SOURCE_REVISION_MISMATCH", run.app_run_id)

    def _legacy_path(self, session: IpBroadcastSession, keys: tuple[str, ...], artifact_type: str) -> str:
        for key in keys:
            value = session.artifacts.get(key) or session.state.get(f"{key}_path")
            if isinstance(value, str) and value.strip():
                return value.strip()
        raise IpBroadcastSessionError("ARTIFACT_OUTPUT_NOT_READY", artifact_type)

    def _validate_legacy_file(self, raw_path: str, *, artifact_type: str) -> dict[str, Any]:
        resolved, matched_root = self._resolve_trusted_file(raw_path, artifact_type)

        size_bytes, header, digest = self._read_stable_legacy_file(resolved, artifact_type)
        if size_bytes <= 0:
            raise IpBroadcastSessionError("ARTIFACT_FILE_EMPTY", artifact_type)
        max_size = MAX_LEGACY_VIDEO_BYTES if artifact_type == "video" else MAX_LEGACY_COVER_BYTES
        if size_bytes > max_size:
            raise IpBroadcastSessionError("ARTIFACT_FILE_TOO_LARGE", artifact_type)
        mime_type = mimetypes.guess_type(resolved.name)[0]
        if mime_type not in ALLOWED_LEGACY_MIME[artifact_type]:
            raise IpBroadcastSessionError("ARTIFACT_FILE_MIME_INVALID", artifact_type)

        # Extension-derived MIME is supplemented with minimal container magic
        # so a renamed text file cannot enter the artifact store as media.
        if artifact_type == "video" and b"ftyp" not in header[:16]:
            raise IpBroadcastSessionError("ARTIFACT_FILE_SIGNATURE_INVALID", artifact_type)
        if artifact_type == "cover":
            valid_image = header.startswith(b"\x89PNG\r\n\x1a\n") or header.startswith(b"\xff\xd8\xff")
            if not valid_image:
                raise IpBroadcastSessionError("ARTIFACT_FILE_SIGNATURE_INVALID", artifact_type)

        relative_path = str(resolved.relative_to(matched_root.path))
        return {
            "file_key": f"{artifact_type}{resolved.suffix.lower()}",
            "root": matched_root.root_id,
            "relative_path": relative_path,
            "kind": artifact_type,
            "mime_type": mime_type,
            "sha256": f"sha256:{digest}",
            "size_bytes": size_bytes,
        }

    @staticmethod
    def _read_stable_legacy_file(path: Path, artifact_type: str) -> tuple[int, bytes, str]:
        """Read one inode and reject replacement or mutation during read."""

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(os.fspath(path), flags)
        except OSError as exc:
            raise IpBroadcastSessionError("ARTIFACT_FILE_READ_FAILED", artifact_type) from exc
        try:
            before = os.fstat(descriptor)
            if not stat.S_ISREG(before.st_mode):
                raise IpBroadcastSessionError("ARTIFACT_FILE_NOT_FOUND", artifact_type)
            digest = hashlib.sha256()
            header = b""
            size_bytes = 0
            with os.fdopen(descriptor, "rb", closefd=True) as stream:
                header = stream.read(32)
                digest.update(header)
                size_bytes = len(header)
                while True:
                    chunk = stream.read(1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size_bytes += len(chunk)
                after = os.fstat(stream.fileno())
        except IpBroadcastSessionError:
            raise
        except OSError as exc:
            raise IpBroadcastSessionError("ARTIFACT_FILE_READ_FAILED", artifact_type) from exc

        try:
            path_stat = os.stat(path, follow_symlinks=False)
        except OSError as exc:
            raise IpBroadcastSessionError("ARTIFACT_FILE_CHANGED", artifact_type) from exc
        def signature(item: os.stat_result) -> tuple[int, int, int, int, int]:
            return (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if signature(before) != signature(after) or signature(before) != signature(path_stat) or size_bytes != before.st_size:
            raise IpBroadcastSessionError("ARTIFACT_FILE_CHANGED", artifact_type)
        return size_bytes, header, digest.hexdigest()

    def _resolve_trusted_file(self, raw_path: str, label: str) -> tuple[Path, _TrustedRoot]:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise IpBroadcastSessionError("ARTIFACT_FILE_NOT_ABSOLUTE", label)
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError) as exc:
            raise IpBroadcastSessionError("ARTIFACT_FILE_NOT_FOUND", label) from exc
        if not resolved.is_file():
            raise IpBroadcastSessionError("ARTIFACT_FILE_NOT_FOUND", label)

        matched_root: _TrustedRoot | None = None
        for root in sorted(self._trusted_roots, key=lambda item: len(item.path.parts), reverse=True):
            try:
                resolved.relative_to(root.path)
            except ValueError:
                continue
            matched_root = root
            break
        if matched_root is None:
            raise IpBroadcastSessionError("ARTIFACT_FILE_OUTSIDE_ROOT", label)
        return resolved, matched_root

    def _legacy_publish_copy(self, session: IpBroadcastSession) -> dict[str, Any]:
        raw_package = session.state.get("publish_package")
        package: dict[str, Any] | None = raw_package if isinstance(raw_package, dict) else None
        if not package:
            package_path = session.artifacts.get("publish_package_json")
            if isinstance(package_path, str) and package_path.strip():
                # Reuse the trusted-root/path checks, but do not expose the
                # package file as an ArtifactVersion ref.
                package_file, _ = self._resolve_trusted_file(package_path.strip(), "publish_package")
                try:
                    package = json.loads(package_file.read_text(encoding="utf-8"))
                except (OSError, ValueError) as exc:
                    raise IpBroadcastSessionError("ARTIFACT_PUBLISH_COPY_INVALID", "package") from exc
        if not isinstance(package, dict):
            raise IpBroadcastSessionError("ARTIFACT_PUBLISH_COPY_INVALID", "package")
        raw_title = package.get("title") or session.state.get("title")
        raw_description = package.get("description") or session.state.get("description")
        title = raw_title.strip() if isinstance(raw_title, str) else ""
        description = raw_description.strip() if isinstance(raw_description, str) else ""
        hashtags = package.get("hashtags", session.state.get("hashtags", []))
        if not title or not description or not isinstance(hashtags, list) or any(
            not isinstance(item, str) or not item.strip() for item in hashtags
        ):
            raise IpBroadcastSessionError("ARTIFACT_PUBLISH_COPY_INVALID", "required fields")
        content: dict[str, Any] = {
            "schema_version": 1,
            "artifact_type": "publish_copy",
            "title": title,
            "description": description,
            "hashtags": [item.strip() for item in hashtags],
            "source_session_id": session.session_id,
        }
        for key in ("cover_title", "comment_cta", "script_summary"):
            value = package.get(key)
            if isinstance(value, str) and value.strip():
                content[key] = value.strip()
        try:
            validate_business_payload(content, label="legacy publish copy")
        except ValueError as exc:
            raise IpBroadcastSessionError("ARTIFACT_PUBLISH_COPY_INVALID", str(exc)) from exc
        return content

    def _get_source_version(self, project_id: str, version_id: str, mode: str) -> ArtifactVersion:
        try:
            version = self.repository.get_artifact_version(version_id)
            artifact = self.repository.get_artifact(version.artifact_id)
        except NotFound as exc:
            raise IpBroadcastInputError("SOURCE_VERSION_NOT_FOUND", version_id) from exc
        if version.project_id != project_id or artifact.project_id != project_id:
            raise IpBroadcastInputError("SOURCE_VERSION_PROJECT_MISMATCH", version_id)
        if artifact.artifact_type != mode:
            raise IpBroadcastInputError("SOURCE_ARTIFACT_TYPE_MISMATCH", artifact.artifact_type)
        return version

    def _handle(self, run: AppRun, binding: IpBroadcastBinding) -> IpBroadcastRunHandle:
        session = self.session_store.get_session(binding.session_id)
        if session is None:
            raise IpBroadcastSessionError("SESSION_NOT_FOUND", binding.session_id)
        projection = project_session_state(session, app_run_state=run.state)
        self._project_task(run, projection)
        return IpBroadcastRunHandle(run=run, binding=binding, session=session, projection=projection.as_dict())

    def _project_task(self, run: AppRun, projection: IpBroadcastStateProjection) -> None:
        """Optionally mirror AppRun facts into GenericTask without payloads."""

        if self.task_projector is None:
            return
        task = next(
            (
                item
                for item in self.task_projector.manager.list_tasks()
                if item.source_kind == "app_run" and item.source_fact_id == run.app_run_id
            ),
            None,
        )
        if task is None:
            task = self.task_projector.create(run)
        self.task_projector.update(run, task.task_id)
        # ``AppRunTaskProjector`` only sees AppRun states.  Apply the
        # session-derived waiting/attention/current-step overlay afterwards.
        task_status = projection.task_status
        if task_status in {
            "pending",
            "running",
            "waiting_for_login",
            "waiting_for_human",
            "needs_attention",
            "needs_review",
            "completed",
            "failed",
            "cancelled",
        }:
            from api.tasks.models import TaskStatus

            task.status = TaskStatus(task_status)
            task.step_key = projection.current_step or projection.when
            self.task_projector.manager._persist_task(task)


__all__ = [
    "APP_ID",
    "APP_VERSION",
    "IpBroadcastAdapterError",
    "IpBroadcastAppAdapter",
    "IpBroadcastBinding",
    "IpBroadcastBindingStore",
    "IpBroadcastInputError",
    "IpBroadcastRunHandle",
    "IpBroadcastSessionError",
    "IpBroadcastStateProjection",
    "project_legacy_state",
    "project_session_state",
]
