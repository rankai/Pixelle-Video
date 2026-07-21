"""SQLite persistence for desktop task records."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Iterable

from api.tasks.models import Task, TaskProgress, TaskStatus, TaskType


class TaskPersistence:
    def __init__(self, db_path: str | Path | None = None):
        configured_path = db_path or os.getenv("PIXELLE_DESKTOP_TASKS_DB") or "data/desktop_tasks.sqlite"
        self.db_path = Path(configured_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def save_task(self, task: Task) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks (
                    task_id, task_type, status, display_name, flow_name, step_key,
                    session_id, request_params, progress, result, error, artifact_keys,
                    retry_payload, source_kind, source_fact_id, created_at, started_at, completed_at, duration_ms
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task_type=excluded.task_type,
                    status=excluded.status,
                    display_name=excluded.display_name,
                    flow_name=excluded.flow_name,
                    step_key=excluded.step_key,
                    session_id=excluded.session_id,
                    request_params=excluded.request_params,
                    progress=excluded.progress,
                    result=excluded.result,
                    error=excluded.error,
                    artifact_keys=excluded.artifact_keys,
                    retry_payload=excluded.retry_payload,
                    source_kind=excluded.source_kind,
                    source_fact_id=excluded.source_fact_id,
                    created_at=excluded.created_at,
                    started_at=excluded.started_at,
                    completed_at=excluded.completed_at,
                    duration_ms=excluded.duration_ms
                """,
                _task_to_row(task),
            )

    def load_tasks(self, limit: int = 500) -> list[Task]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_row_to_task(row) for row in rows]

    def mark_interrupted_tasks_failed(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE tasks
                SET status = ?, error = ?, completed_at = COALESCE(completed_at, datetime('now'))
                WHERE status IN (?, ?)
                """,
                (
                    TaskStatus.FAILED.value,
                    "服务重启，任务已中断，请重新执行。",
                    TaskStatus.PENDING.value,
                    TaskStatus.RUNNING.value,
                ),
            )

    def delete_tasks(self, task_ids: Iterable[str]) -> None:
        ids = list(task_ids)
        if not ids:
            return
        placeholders = ",".join("?" for _ in ids)
        with self._connect() as conn:
            conn.execute(f"DELETE FROM tasks WHERE task_id IN ({placeholders})", ids)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    task_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    flow_name TEXT NOT NULL DEFAULT '',
                    step_key TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    request_params TEXT,
                    progress TEXT,
                    result TEXT,
                    error TEXT,
                    artifact_keys TEXT NOT NULL DEFAULT '[]',
                    retry_payload TEXT,
                    source_kind TEXT,
                    source_fact_id TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_ms INTEGER
                )
                """
            )
            columns = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            if "source_kind" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN source_kind TEXT")
            if "source_fact_id" not in columns:
                conn.execute("ALTER TABLE tasks ADD COLUMN source_fact_id TEXT")


def _task_to_row(task: Task) -> tuple:
    return (
        task.task_id,
        task.task_type.value,
        task.status.value,
        task.display_name,
        task.flow_name,
        task.step_key,
        task.session_id,
        _dump_json(task.request_params),
        _dump_json(task.progress.model_dump(mode="json") if task.progress else None),
        _dump_json(task.result),
        task.error,
        _dump_json(task.artifact_keys),
        _dump_json(task.retry_payload),
        task.source_kind,
        task.source_fact_id,
        task.created_at.isoformat(),
        task.started_at.isoformat() if task.started_at else None,
        task.completed_at.isoformat() if task.completed_at else None,
        task.duration_ms,
    )


def _row_to_task(row: sqlite3.Row) -> Task:
    progress = _load_json(row["progress"])
    return Task(
        task_id=row["task_id"],
        task_type=TaskType(row["task_type"]),
        status=TaskStatus(row["status"]),
        progress=TaskProgress(**progress) if isinstance(progress, dict) else None,
        result=_load_json(row["result"]),
        error=row["error"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        completed_at=row["completed_at"],
        request_params=_load_json(row["request_params"]),
        display_name=row["display_name"],
        flow_name=row["flow_name"],
        step_key=row["step_key"],
        session_id=row["session_id"],
        artifact_keys=_load_json(row["artifact_keys"]) or [],
        duration_ms=row["duration_ms"],
        retry_payload=_load_json(row["retry_payload"]),
        source_kind=row["source_kind"] if "source_kind" in row.keys() else None,
        source_fact_id=row["source_fact_id"] if "source_fact_id" in row.keys() else None,
    )


def _dump_json(value) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _load_json(value: str | None):
    if not value:
        return None
    return json.loads(value)
