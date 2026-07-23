"""PUB-2 run orchestration with a hard human-stop before platform actions."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from api.tasks.manager import TaskManager, task_manager
from api.tasks.models import TaskProgress, TaskStatus, TaskType

from .account_models import AccountLoginState, PublishPlatform
from .account_repository import PublishAccountNotFound, PublishAccountRepository
from .core_models import PublishRun, PublishRunState
from .core_repository import (
    PublishCoreRepository,
    PublishRunConcurrencyConflict,
    PublishRunConflict,
)
from .execution_protocol import (
    BLOCKER_REGISTRY,
    PublishBlockerCode,
    PublishExecutionCheckpoint,
    PublishStage,
    parse_checkpoint,
)
from .package_service import PublishPackageBuildError
from .platform_profiles import canonical_platform
from .profile_manager import BrowserProfileManager, ProfileLockError


class PublishRunServiceError(RuntimeError):
    """Base error for orchestration operations."""

    def __init__(self, code: str, message: str | None = None):
        self.code = code
        super().__init__(message or code)


class PublishRunService:
    """Coordinate durable run facts and a redacted Generic Task projection.

    ``executor`` is intentionally a preparation-only hook. The default path
    stops at ``waiting_for_human`` and never selects a platform or uploads.
    """

    def __init__(
        self,
        core_repository: PublishCoreRepository,
        account_repository: PublishAccountRepository,
        *,
        manager: TaskManager = task_manager,
        executor: Callable[[PublishRun], Awaitable[None]] | None = None,
        profile_manager: BrowserProfileManager | None = None,
        media_verifier: Callable[[Any], None] | None = None,
    ):
        self.core_repository = core_repository
        self.account_repository = account_repository
        self.manager = manager
        self.executor = executor
        self.profile_manager = profile_manager or BrowserProfileManager(repository=account_repository)
        self.media_verifier = media_verifier
        self._jobs: dict[str, asyncio.Task[Any]] = {}
        self._locks: dict[str, Any] = {}

    def create_run(
        self,
        package_id: str,
        account_id: str,
        platform: PublishPlatform,
        idempotency_key: str,
        *,
        auto_start: bool = False,
    ) -> tuple[PublishRun, bool]:
        try:
            account = self.account_repository.get_account(account_id)
        except PublishAccountNotFound as exc:
            raise PublishRunConflict("ACCOUNT_NOT_FOUND") from exc
        if account.platform != platform:
            raise PublishRunConflict("ACCOUNT_PLATFORM_MISMATCH")
        # Non-Douyin adapters are implementation-ready but remain behind the
        # independent live-gate/release boundary.  Keep the durable run API
        # from opening a browser for an unverified platform; copy/download
        # fallback stays available in the desktop workbench.
        if account.platform is not PublishPlatform.DOUYIN and account.platform_release_state != "pilot":
            raise PublishRunConflict("PLATFORM_RELEASE_NOT_READY")
        run, replay = self.core_repository.create_run(package_id, account_id, platform, idempotency_key)
        if run.task_id is None:
            task = self.manager.create_task(
                task_type=TaskType.PUBLISH_ASSISTANT,
                request_params=None,
                display_name="发布助手",
                flow_name="publishing-v2",
                step_key=run.current_step or run.state.value,
                session_id=f"publish_run:{run.run_id}",
                artifact_keys=[],
                retry_payload=None,
                source_kind="publish_run",
                source_fact_id=run.run_id,
            )
            run = self.core_repository.attach_task(run.run_id, task.task_id)
            self._sync_task(run)
            self.core_repository.append_event(run.run_id, "run_created", state=run.state, state_version=run.state_version, payload={"step": "queued"})
        if auto_start and not replay:
            self.schedule(run.run_id)
        return run, replay

    def schedule(self, run_id: str) -> asyncio.Task[Any]:
        existing = self._jobs.get(run_id)
        if existing and not existing.done():
            return existing
        try:
            job = asyncio.create_task(self.start(run_id))
        except RuntimeError as exc:
            raise PublishRunServiceError("RUN_REQUIRES_ASYNC_CONTEXT") from exc
        self._jobs[run_id] = job
        return job

    async def start(self, run_id: str) -> PublishRun:
        run = self.core_repository.get_run(run_id)
        if run.state is PublishRunState.QUEUED:
            try:
                package = self.core_repository.get_package(run.package_id)
                current_attempts = [item for item in self.core_repository.list_step_attempts(run_id, step="preflight") if item.attempt == run.attempt]
                if not current_attempts:
                    self.core_repository.create_step_attempt(run_id, "preflight", run.attempt, PublishRunState.QUEUED)
                if package.invalidated_at or not package.policy.human_confirmation_required or package.policy.allow_final_publish:
                    raise ValueError("PUBLISH_PACKAGE_STALE_OR_POLICY_INVALID")
                if self.media_verifier:
                    self.media_verifier(package)
                self.core_repository.update_step_attempt(run_id, "preflight", run.attempt, PublishRunState.SUCCEEDED)
            except PublishPackageBuildError as exc:
                code = str(exc)
                self._mark_preflight_failed(run, code)
                run = self.core_repository.transition_run(run_id, PublishRunState.NEEDS_ATTENTION, expected_version=run.state_version, current_step="preflight", error_code=code, event_type="preflight_failed", event_payload={"step": "preflight", "error_code": code})
                self._sync_task(run)
                return run
            except Exception:
                self._mark_preflight_failed(run, "PUBLISH_PREFLIGHT_FAILED")
                run = self.core_repository.transition_run(run_id, PublishRunState.NEEDS_ATTENTION, expected_version=run.state_version, current_step="preflight", error_code="PUBLISH_PREFLIGHT_FAILED", event_type="preflight_failed", event_payload={"step": "preflight", "error_code": "PUBLISH_PREFLIGHT_FAILED"})
                self._sync_task(run)
                return run
            run = self.core_repository.transition_run(run_id, PublishRunState.RUNNING, expected_version=run.state_version, current_step="preflight", event_type="run_started")
            self._sync_task(run)
        if run.state is not PublishRunState.RUNNING:
            return run
        try:
            account = self.account_repository.get_account(run.account_id)
        except Exception:
            run = self.core_repository.transition_run(run_id, PublishRunState.NEEDS_ATTENTION, expected_version=run.state_version, current_step="account", error_code="ACCOUNT_UNAVAILABLE", event_type="account_unavailable", event_payload={"step": "account", "error_code": "ACCOUNT_UNAVAILABLE"})
            self._sync_task(run)
            return run
        if account.login_state is not AccountLoginState.AUTHENTICATED:
            run = self.core_repository.transition_run(
                run_id,
                PublishRunState.WAITING_FOR_LOGIN,
                expected_version=run.state_version,
                current_step="await_login",
                error_code="LOGIN_REQUIRED",
                error_message=None,
                event_type="login_required",
                event_payload={"step": "await_login", "error_code": "LOGIN_REQUIRED"},
            )
            self._sync_task(run)
            return run
        try:
            lock = self.profile_manager.acquire_lock(account, owner_ref=f"publish-run:{run_id}")
        except ProfileLockError:
            run = self.core_repository.transition_run(run_id, PublishRunState.NEEDS_ATTENTION, expected_version=run.state_version, current_step="profile_lock", error_code="PROFILE_LOCKED", event_type="profile_locked", event_payload={"step": "profile_lock", "error_code": "PROFILE_LOCKED"})
            self._sync_task(run)
            return run
        try:
            if self.executor is not None:
                await self.executor(run)
        except Exception as exc:
            error_code = exc.code if isinstance(exc, PublishRunServiceError) else "RUNNER_ERROR"
            event_error_code = error_code
            if any(marker in error_code.lower() for marker in ("description", "title", "profile", "path", "cookie", "authorization", "request_params")):
                event_error_code = "RUNNER_ERROR"
            current = self.core_repository.get_run(run_id)
            if current.state is not PublishRunState.RUNNING:
                self._sync_task(current)
                lock.release()
                return current
            run = self.core_repository.transition_run(run_id, PublishRunState.NEEDS_ATTENTION, expected_version=current.state_version, current_step=current.current_step or "runner", error_code=error_code, error_message=None, event_type="runner_error", event_payload={"step": current.current_step or "runner", "error_code": event_error_code})
            self._sync_task(run)
            lock.release()
            return run
        run = self.core_repository.get_run(run_id)
        if run.state is PublishRunState.RUNNING:
            run = self.core_repository.transition_run(run_id, PublishRunState.WAITING_FOR_HUMAN, expected_version=run.state_version, current_step="await_human_publish", event_type="await_human_publish")
            self._sync_task(run)
            self._locks[run_id] = lock
        else:
            lock.release()
        return run

    def resume(self, run_id: str, *, expected_version: int | None = None) -> PublishRun:
        run = self.core_repository.get_run(run_id)
        if expected_version is not None and run.state_version != expected_version:
            raise PublishRunConcurrencyConflict("RUN_VERSION_CONFLICT")
        if run.state is PublishRunState.NEEDS_ATTENTION:
            if run.error_code in {
                PublishBlockerCode.FOREIGN_DRAFT.value,
                PublishBlockerCode.STATE_AMBIGUOUS.value,
            }:
                # Identity blockers invalidate the prior attempt's draft
                # claims. Start a new durable attempt so the executor can
                # inspect the live page and, only when it is truly empty,
                # perform one bounded upload instead of replaying stale
                # checkpoint identity.
                prior = self.core_repository.list_step_attempts(run_id, step="resume")
                next_attempt = max((item.attempt for item in prior), default=0) + 1
                run = self.core_repository.queue_step_retry(
                    run_id,
                    "resume",
                    expected_version=run.state_version,
                    step_attempt=next_attempt,
                )
                self._sync_task(run)
                self._release_lock(run_id, run.account_id)
                return run
            run = self.core_repository.transition_run(run_id, PublishRunState.QUEUED, expected_version=run.state_version, current_step="resume", event_type="run_resumed", event_payload={"step": "resume"})
            return run
        if run.state is PublishRunState.WAITING_FOR_LOGIN:
            run = self.core_repository.transition_run(run_id, PublishRunState.RUNNING, expected_version=run.state_version, current_step="resume", event_type="run_resumed", event_payload={"step": "resume"})
            return run
        raise PublishRunConflict("RUN_STATE_INVALID")

    def cancel(self, run_id: str, *, expected_version: int | None = None, actor_ref: str | None = None) -> PublishRun:
        run = self.core_repository.get_run(run_id)
        if expected_version is not None and run.state_version != expected_version:
            raise PublishRunConcurrencyConflict("RUN_VERSION_CONFLICT")
        if run.state in {PublishRunState.SUCCEEDED, PublishRunState.FAILED, PublishRunState.CANCELLED}:
            return run
        run = self.core_repository.transition_run(run_id, PublishRunState.CANCELLED, expected_version=run.state_version, current_step="cancelled", error_code="CANCELLED", actor_ref=actor_ref, event_type="run_cancelled", event_payload={"step": "cancelled"})
        if run.task_id:
            self.manager.cancel_task(run.task_id)
        self._release_lock(run_id, run.account_id)
        return run

    def retry_step(self, run_id: str, step: str, *, actor_ref: str | None = None) -> PublishRun:
        if not step.strip():
            raise PublishRunServiceError("STEP_REQUIRED")
        run = self.core_repository.get_run(run_id)
        if run.state is not PublishRunState.NEEDS_ATTENTION:
            raise PublishRunConflict("RUN_STATE_INVALID")
        retryable_steps = {
            "preflight",
            "media_preflight",
            "prepare_package",
            "verify_media",
            "await_login",
            "adapter_prepare",
            "resume",
        }
        if step not in retryable_steps or run.current_step not in {None, step}:
            raise PublishRunConflict("STEP_NOT_RETRYABLE")
        prior = self.core_repository.list_step_attempts(run_id, step=step)
        if not prior:
            raise PublishRunConflict("STEP_NOT_RETRYABLE")
        next_attempt = max((item.attempt for item in prior), default=0) + 1
        run = self.core_repository.queue_step_retry(run_id, step, expected_version=run.state_version, step_attempt=next_attempt, actor_ref=actor_ref)
        self._sync_task(run)
        self._release_lock(run_id, run.account_id)
        return run

    def record_execution_checkpoint(
        self,
        run_id: str,
        checkpoint: PublishExecutionCheckpoint,
        *,
        stage: PublishStage,
        blocker: str | None = None,
    ) -> PublishRun:
        """Persist one stateful executor checkpoint with a CAS transition.

        Checkpoints advance ``state_version`` even when the run state remains
        ``running`` or ``needs_attention``.  This makes a browser/runtime
        callback observable and prevents a stale executor from overwriting a
        newer recovery decision.
        """

        current = self.core_repository.get_run(run_id)
        if current.state not in {PublishRunState.RUNNING, PublishRunState.NEEDS_ATTENTION}:
            raise PublishRunConflict("RUN_CHECKPOINT_STATE_INVALID")
        package = self.core_repository.get_package(current.package_id)
        account = self.account_repository.get_account(current.account_id)
        if checkpoint.package_fingerprint != package.package_fingerprint:
            raise PublishRunServiceError("CHECKPOINT_PACKAGE_MISMATCH")
        if checkpoint.account_id != current.account_id or canonical_platform(checkpoint.platform) != canonical_platform(current.platform.value):
            raise PublishRunServiceError("CHECKPOINT_RUN_BINDING_MISMATCH")
        if checkpoint.attempt != current.attempt:
            raise PublishRunServiceError("CHECKPOINT_ATTEMPT_MISMATCH")
        if checkpoint.draft_identity and checkpoint.draft_identity.profile_ref != account.profile_ref:
            raise PublishRunServiceError("CHECKPOINT_PROFILE_MISMATCH")
        blocker_code = PublishBlockerCode(blocker) if blocker else None
        if blocker_code is not None:
            if checkpoint.blocker_code is not blocker_code:
                raise PublishRunServiceError("CHECKPOINT_BLOCKER_MISMATCH")
            if stage != checkpoint.blocked_stage:
                raise PublishRunServiceError("CHECKPOINT_STAGE_MISMATCH")
            target_state = PublishRunState(BLOCKER_REGISTRY[blocker_code].run_state)
        else:
            if checkpoint.blocker_code is not None or checkpoint.blocked_stage is not None:
                raise PublishRunServiceError("CHECKPOINT_BLOCKER_MISMATCH")
            if checkpoint.last_stage != stage:
                raise PublishRunServiceError("CHECKPOINT_STAGE_MISMATCH")
            target_state = current.state
        return self.core_repository.transition_run(
            run_id,
            target_state,
            expected_version=current.state_version,
            current_step=stage.value,
            error_code=blocker or current.error_code,
            checkpoint=checkpoint.as_checkpoint(),
            event_type="execution_checkpoint",
            event_payload={
                "step": stage.value,
                "evidence_kind": "stateful_execution_checkpoint",
            },
        )

    def mark_human_outcome(self, run_id: str, *, published: bool, actor_ref: str) -> PublishRun:
        if not actor_ref.strip():
            raise PublishRunServiceError("ACTOR_REQUIRED")
        run = self.core_repository.get_run(run_id)
        if run.state is not PublishRunState.WAITING_FOR_HUMAN:
            raise PublishRunConflict("RUN_STATE_INVALID")
        if published:
            run = self.core_repository.transition_run(run_id, PublishRunState.SUCCEEDED, expected_version=run.state_version, current_step="human_published", human_confirmed=True, actor_ref=actor_ref, event_type="human_publish_confirmed", event_payload={"step": "human_published", "human_outcome": "published"})
        else:
            run = self.core_repository.transition_run(run_id, PublishRunState.CANCELLED, expected_version=run.state_version, current_step="human_not_published", error_code="HUMAN_NOT_PUBLISHED", actor_ref=actor_ref, event_type="human_publish_declined", event_payload={"step": "human_not_published", "human_outcome": "not_published"})
        self._sync_task(run)
        self._release_lock(run_id, run.account_id)
        return run

    def reconcile_verified_checkpoint(self, run_id: str) -> PublishRun:
        """Promote a durably verified, no-click checkpoint after a runner error."""

        run = self.core_repository.get_run(run_id)
        if run.state is not PublishRunState.NEEDS_ATTENTION:
            raise PublishRunConflict("RUN_STATE_INVALID")
        try:
            checkpoint = parse_checkpoint(run.checkpoint)
        except Exception as exc:
            raise PublishRunConflict("CHECKPOINT_CORRUPT") from exc
        if checkpoint is None or checkpoint.attempt != run.attempt:
            raise PublishRunConflict("CHECKPOINT_ATTEMPT_MISMATCH")
        if (
            checkpoint.last_stage is not PublishStage.VERIFY
            or PublishStage.VERIFY not in checkpoint.completed_stages
            or checkpoint.blocker_code is not None
            or checkpoint.blocked_stage is not None
            or checkpoint.final_publish_clicked
            or not checkpoint.final_action_guard_armed
        ):
            raise PublishRunConflict("CHECKPOINT_NOT_VERIFIED")
        run = self.core_repository.transition_run(
            run_id,
            PublishRunState.WAITING_FOR_HUMAN,
            expected_version=run.state_version,
            current_step="await_human_publish",
            error_code=None,
            event_type="verified_checkpoint_reconciled",
            event_payload={
                "step": "await_human_publish",
                "evidence_kind": "stateful_checkpoint_reconciled",
            },
        )
        self._sync_task(run)
        return run

    def recover_after_restart(self) -> list[PublishRun]:
        recovered = self.core_repository.recover_inflight_runs()
        for run in recovered:
            self._sync_task(run)
            try:
                account = self.account_repository.get_account(run.account_id)
                self.profile_manager.release_lock(account, f"publish-run:{run.run_id}")
            except Exception:
                pass
            # recover_inflight_runs emits the state transition event atomically.
        return recovered

    def _record_transition(self, run: PublishRun, event_type: str, *, payload: dict[str, Any] | None = None) -> None:
        self._sync_task(run)

    def _sync_task(self, run: PublishRun) -> None:
        if not run.task_id:
            return
        task = self.manager.get_task(run.task_id)
        if task is None:
            return
        status = {
            PublishRunState.QUEUED: TaskStatus.PENDING,
            PublishRunState.RUNNING: TaskStatus.RUNNING,
            PublishRunState.WAITING_FOR_LOGIN: TaskStatus.WAITING_FOR_LOGIN,
            PublishRunState.WAITING_FOR_HUMAN: TaskStatus.WAITING_FOR_HUMAN,
            PublishRunState.NEEDS_ATTENTION: TaskStatus.NEEDS_ATTENTION,
            PublishRunState.SUCCEEDED: TaskStatus.COMPLETED,
            PublishRunState.FAILED: TaskStatus.FAILED,
            PublishRunState.CANCELLED: TaskStatus.CANCELLED,
        }[run.state]
        task.status = status
        task.source_kind = "publish_run"
        task.source_fact_id = run.run_id
        task.display_name = "发布助手"
        task.flow_name = "publishing-v2"
        task.step_key = run.current_step or run.state.value
        task.progress = TaskProgress(current=100 if status is TaskStatus.COMPLETED else 0, total=100, percentage=100 if status is TaskStatus.COMPLETED else 0, message=task.step_key)
        task.error = run.error_code
        self.manager._persist_task(task)

    def _release_lock(self, run_id: str, account_id: str) -> None:
        lock = self._locks.pop(run_id, None)
        if lock is not None:
            lock.release()
            return
        try:
            account = self.account_repository.get_account(account_id)
            self.profile_manager.release_lock(account, f"publish-run:{run_id}")
        except Exception:
            pass

    def _mark_preflight_failed(self, run: PublishRun, error_code: str) -> None:
        attempts = [item for item in self.core_repository.list_step_attempts(run.run_id, step="preflight") if item.attempt == run.attempt and item.state is PublishRunState.QUEUED]
        if attempts:
            self.core_repository.update_step_attempt(run.run_id, "preflight", run.attempt, PublishRunState.FAILED, error_code=error_code)
