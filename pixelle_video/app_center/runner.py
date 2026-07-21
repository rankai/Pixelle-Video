"""Shared AppRunner with deterministic fake executors."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Protocol

from .llm_port import AppLLMPortError
from .models import AppRun
from .registry import get_app
from .repository import AppCenterRepository, AppCenterRepositoryError


@dataclass(frozen=True)
class RelatedArtifactOutput:
    """A secondary ArtifactVersion produced alongside the primary output."""

    key: str
    artifact_type: str
    name: str
    content: dict[str, Any] | None = None
    file_refs: list[dict[str, Any]] | None = None
    source: str = "generated"


@dataclass(frozen=True)
class ExecutorOutput:
    artifact_type: str
    name: str
    content: dict[str, Any] | None = None
    file_refs: list[dict[str, Any]] | None = None
    source: str = "generated"
    model_ref: str | None = None
    provider_class: str | None = None
    input_units: int | None = None
    output_units: int | None = None
    related_artifacts: list[RelatedArtifactOutput] | None = None


class AppExecutor(Protocol):
    async def execute(self, app_run: AppRun) -> ExecutorOutput: ...


class FakeExecutor:
    """No-provider executor for AppRun lifecycle tests."""

    def __init__(self, output: ExecutorOutput | None = None):
        self.output = output or ExecutorOutput("copywriting", "Fake output", {"text": "fake"})

    async def execute(self, app_run: AppRun) -> ExecutorOutput:
        failure = app_run.input_payload.get("__fake_error")
        if failure:
            raise RuntimeError(str(failure))
        return ExecutorOutput(
            self.output.artifact_type,
            self.output.name,
            self.output.content or {"input": app_run.input_payload},
            self.output.file_refs,
            self.output.source,
            self.output.model_ref,
            self.output.provider_class,
            self.output.input_units,
            self.output.output_units,
        )


class AppRunnerConfigurationError(RuntimeError):
    """The registry, feature flag, or required capability is not ready."""


class AppRunner:
    def __init__(self, repository: AppCenterRepository, *, executors: dict[str, AppExecutor] | None = None, task_projector=None, enforce_readiness: bool = True):
        self.repository = repository
        self.executors = executors or {}
        self.task_projector = task_projector
        self.enforce_readiness = enforce_readiness
        self._active_attempts: dict[str, tuple[str, str | None]] = {}
        self._cancel_requested: set[str] = set()

    def register_fake_executor(self, app_id: str, executor: AppExecutor | None = None) -> None:
        self.executors[app_id] = executor or FakeExecutor()

    @staticmethod
    def _duration_ms(started_monotonic: float) -> int:
        return max(0, round((time.perf_counter() - started_monotonic) * 1000))

    async def run(self, app_run_id: str, *, task_id: str | None = None) -> AppRun:
        run = self.repository.get_app_run(app_run_id)
        if self.enforce_readiness:
            manifest = get_app(run.app_id)
            if manifest is None or manifest["version"] != run.app_version:
                raise AppRunnerConfigurationError("应用版本未登记")
            readiness = manifest["readiness"]
            if not manifest["enabled"] or readiness["status"] != "ready":
                raise AppRunnerConfigurationError(f"应用尚未就绪: {readiness['status']}")
        self._cancel_requested.discard(app_run_id)
        if run.state == "failed":
            run = self.repository.retry_app_run(app_run_id)
        if run.state == "draft":
            run = self.repository.transition_app_run(app_run_id, "queued")
        if run.state != "queued":
            return run
        run = self.repository.transition_app_run(app_run_id, "running")
        previous_attempts = self.repository.list_attempts(app_run_id)
        task_id = task_id or (previous_attempts[-1].task_id if previous_attempts and previous_attempts[-1].task_id else None)
        projected_task = None
        if self.task_projector:
            if task_id:
                projected_task = self.task_projector.manager.get_task(task_id)
            else:
                projected_task = self.task_projector.create(run)
        attempt = self.repository.create_attempt(app_run_id, task_id=projected_task.task_id if projected_task else task_id)
        started_monotonic = time.perf_counter()
        self._active_attempts[app_run_id] = (attempt.attempt_id, attempt.task_id)
        self.repository.update_attempt(attempt.attempt_id, state="running", started_at=run.updated_at)
        if projected_task:
            self.task_projector.update(run, projected_task.task_id)
        executor = self.executors.get(run.app_id)
        if executor is None:
            result = await self._fail(run, attempt.attempt_id, "APP_EXECUTOR_NOT_REGISTERED", "应用尚未注册执行器", started_monotonic=started_monotonic)
            self._project(result, attempt.task_id)
            self._active_attempts.pop(app_run_id, None)
            return result
        try:
            output = await executor.execute(run)
            current = self.repository.get_app_run(app_run_id)
            if app_run_id in self._cancel_requested or current.state == "cancelled":
                self.repository.update_attempt(attempt.attempt_id, state="cancelled", completed_at=current.updated_at, duration_ms=self._duration_ms(started_monotonic))
                result = self.repository.get_app_run(app_run_id)
                self._project(result, attempt.task_id)
                self._active_attempts.pop(app_run_id, None)
                return result
            try:
                created_artifact_ids: list[str] = []
                related_artifact_ids: list[str] = []
                related_version_ids: dict[str, str] = {}
                for related in output.related_artifacts or []:
                    if not related.key or related.key in related_version_ids:
                        raise ValueError("related artifact key must be unique")
                    related_artifact = self.repository.create_artifact(
                        run.project_id,
                        related.artifact_type,
                        related.name,
                        source_app_run_id=run.app_run_id,
                    )
                    created_artifact_ids.append(related_artifact.artifact_id)
                    related_version = self.repository.append_artifact_version(
                        related_artifact.artifact_id,
                        content=_resolve_artifact_output_refs(related.content, related_version_ids),
                        file_refs=related.file_refs,
                        source=related.source,
                    )
                    related_artifact_ids.append(related_version.artifact_id)
                    related_version_ids[related.key] = related_version.artifact_version_id
                artifact = self.repository.create_artifact(run.project_id, output.artifact_type, output.name, source_app_run_id=run.app_run_id)
                created_artifact_ids.append(artifact.artifact_id)
                version = self.repository.append_artifact_version(
                    artifact.artifact_id,
                    content=_resolve_artifact_output_refs(output.content, related_version_ids),
                    file_refs=output.file_refs,
                    source=output.source,
                )
                self.repository.set_output_artifacts(run.app_run_id, [version.artifact_id, *related_artifact_ids])
            except Exception:
                # Compensate only artifacts created by this attempt.  A retry
                # must preserve prior successful ArtifactVersion history.
                self.repository.purge_artifacts_by_ids(created_artifact_ids)
                raise
            self.repository.update_attempt(
                attempt.attempt_id,
                state="needs_review",
                completed_at=self.repository.get_app_run(app_run_id).updated_at,
                model_ref=output.model_ref or "local-default:fake",
                provider_class=output.provider_class or "fake",
                input_units=output.input_units,
                output_units=output.output_units,
                duration_ms=self._duration_ms(started_monotonic),
            )
            result = self.repository.transition_app_run(app_run_id, "needs_review")
            self._project(result, attempt.task_id)
            self._active_attempts.pop(app_run_id, None)
            return result
        except AppLLMPortError as exc:
            result = await self._fail(run, attempt.attempt_id, exc.code, str(exc), diagnostic=exc.diagnostic, started_monotonic=started_monotonic)
            self._project(result, attempt.task_id)
            self._active_attempts.pop(app_run_id, None)
            return result
        except Exception as exc:
            current = self.repository.get_app_run(app_run_id)
            if app_run_id in self._cancel_requested or current.state == "cancelled":
                self.repository.update_attempt(attempt.attempt_id, state="cancelled", completed_at=current.updated_at, duration_ms=self._duration_ms(started_monotonic))
                result = current
            else:
                result = await self._fail(run, attempt.attempt_id, "APP_EXECUTOR_FAILED", "应用执行失败", diagnostic=type(exc).__name__, started_monotonic=started_monotonic)
            self._project(result, attempt.task_id)
            self._active_attempts.pop(app_run_id, None)
            return result

    async def _fail(self, run: AppRun, attempt_id: str, code: str, message: str, *, diagnostic: str | None = None, started_monotonic: float | None = None) -> AppRun:
        current = self.repository.get_app_run(run.app_run_id)
        if current.state == "cancelled":
            values = {"state": "cancelled", "completed_at": current.updated_at}
            if started_monotonic is not None:
                values["duration_ms"] = self._duration_ms(started_monotonic)
            self.repository.update_attempt(attempt_id, **values)
            return current
        values = {
            "state": "failed",
            "error_code": code,
            "error_message": message,
            "diagnostic_json": {"type": diagnostic} if diagnostic else None,
            "completed_at": current.updated_at,
        }
        if started_monotonic is not None:
            values["duration_ms"] = self._duration_ms(started_monotonic)
        self.repository.update_attempt(attempt_id, **values)
        result = self.repository.transition_app_run(run.app_run_id, "failed")
        return self.repository.set_app_run_error(result.app_run_id, code)

    def _project(self, run: AppRun, task_id: str | None) -> None:
        if self.task_projector and task_id:
            self.task_projector.update(run, task_id)

    def accept_output(self, app_run_id: str) -> AppRun:
        current = self.repository.get_app_run(app_run_id)
        if current.state != "needs_review":
            raise AppCenterRepositoryError("only needs_review AppRuns can be completed")
        attempts = self.repository.list_attempts(app_run_id)
        if not attempts or attempts[-1].state != "needs_review" or not current.output_artifact_ids:
            raise AppCenterRepositoryError("AppRun has no reviewable output")
        result = self.repository.transition_app_run(app_run_id, "completed")
        self.repository.update_attempt(attempts[-1].attempt_id, state="completed", completed_at=result.completed_at)
        self._project(result, attempts[-1].task_id if attempts else None)
        return result

    def cancel(self, app_run_id: str) -> AppRun:
        self._cancel_requested.add(app_run_id)
        result = self.repository.cancel_app_run(app_run_id)
        attempts = self.repository.list_attempts(app_run_id)
        if attempts and attempts[-1].state not in {"completed", "failed", "cancelled"}:
            self.repository.update_attempt(attempts[-1].attempt_id, state="cancelled", completed_at=result.completed_at)
        self._project(result, attempts[-1].task_id if attempts else None)
        return result

    def retry(self, app_run_id: str) -> AppRun:
        result = self.repository.retry_app_run(app_run_id)
        attempts = self.repository.list_attempts(app_run_id)
        self._project(result, attempts[-1].task_id if attempts else None)
        return result

    def archive(self, app_run_id: str) -> AppRun:
        return self.repository.archive_app_run(app_run_id)


def _resolve_artifact_output_refs(value: Any, refs: dict[str, str]) -> Any:
    """Resolve executor-local placeholders without exposing provider metadata."""

    if isinstance(value, str) and value.startswith("artifact_output:"):
        key = value.removeprefix("artifact_output:")
        if key not in refs:
            raise ValueError(f"unknown related artifact reference: {key}")
        return refs[key]
    if isinstance(value, list):
        return [_resolve_artifact_output_refs(item, refs) for item in value]
    if isinstance(value, dict):
        return {key: _resolve_artifact_output_refs(item, refs) for key, item in value.items()}
    return value
