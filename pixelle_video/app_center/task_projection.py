"""Redacted GenericTask projection for AppRun facts."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api.tasks import TaskStatus, TaskType, task_manager
from api.tasks.models import TaskProgress

from .models import AppRun

ALLOWED_PROJECTION_FIELDS = frozenset({"task_id", "source_kind", "source_fact_id", "status", "progress", "title", "step_key", "error_code", "created_at", "updated_at"})
FORBIDDEN_PROJECTION_FIELDS = frozenset({"request_params", "absolute_file_path", "cookie", "authorization", "api_key", "result"})


def project_app_run(run: AppRun, *, task_id: str | None = None) -> dict[str, Any]:
    """Return only the fields a GenericTask projection may expose."""

    status = {
        "draft": "pending",
        "queued": "pending",
        "running": "running",
        "needs_review": "needs_review",
        "completed": "completed",
        "failed": "failed",
        "cancelled": "cancelled",
    }[run.state]
    return {
        "task_id": task_id or f"app-run:{run.app_run_id}",
        "source_kind": "app_run",
        "source_fact_id": run.app_run_id,
        "status": status,
        "progress": 100 if run.state in {"completed", "failed", "cancelled"} else 0,
        "title": run.app_id,
        "step_key": run.state,
        "error_code": run.error_code,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


class AppRunTaskProjector:
    """Optional bridge into the existing TaskManager without copying facts."""

    def __init__(self, manager=task_manager):
        self.manager = manager

    def create(self, run: AppRun):
        task = self.manager.create_task(
            task_type=TaskType.APP_RUN,
            request_params=None,
            display_name=run.app_id,
            flow_name="application-center",
            step_key=run.state,
            session_id=f"app_run:{run.app_run_id}",
            artifact_keys=[],
            retry_payload=None,
            source_kind="app_run",
            source_fact_id=run.app_run_id,
        )
        return task

    def update(self, run: AppRun, task_id: str):
        projected = project_app_run(run, task_id=task_id)
        task = self.manager.get_task(task_id)
        if task is None:
            return None
        timestamp = datetime.fromisoformat(projected["updated_at"].replace("Z", "+00:00")).replace(tzinfo=None)
        if run.state == "cancelled":
            self.manager.cancel_task(task_id)
        task.status = TaskStatus({"pending": "pending", "running": "running", "needs_review": "needs_review", "completed": "completed", "failed": "failed", "cancelled": "cancelled"}[projected["status"]])
        task.source_kind = projected["source_kind"]
        task.source_fact_id = projected["source_fact_id"]
        task.display_name = projected["title"]
        task.step_key = projected["step_key"]
        task.progress = TaskProgress(current=projected["progress"], total=100, percentage=projected["progress"], message=projected["step_key"])
        task.error = projected["error_code"]
        if run.state in {"running", "needs_review", "completed", "failed", "cancelled"}:
            task.started_at = task.started_at or timestamp
        elif run.state in {"queued", "draft"}:
            task.started_at = None
        if run.state in {"completed", "failed", "cancelled"}:
            task.completed_at = timestamp
        else:
            task.completed_at = None
        self.manager._persist_task(task)
        return task
