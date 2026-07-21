"""Run the PROGRAM-ROLLOUT bounded app-center scale check.

The check is deliberately local and uses a temporary SQLite database.  It
exercises the public repository operations required by the Entry contract:
100 active ContentProjects and 1,000 active Artifacts (ten per project), then
reads both collections back and verifies the per-project distribution.  It
does not touch the user's application-center database or start an API/browser.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from pixelle_video.app_center.repository import AppCenterRepository

PROJECT_COUNT = 100
ARTIFACTS_PER_PROJECT = 10
ARTIFACT_COUNT = PROJECT_COUNT * ARTIFACTS_PER_PROJECT


def run_scale_check(db_path: str | Path) -> dict[str, Any]:
    """Populate and read a bounded fixture, returning auditable metrics."""

    repository = AppCenterRepository(db_path)
    create_started = time.perf_counter()
    projects = [
        repository.create_project(
            f"规模检查项目-{index:03d}",
            "PROGRAM-ROLLOUT bounded scale check",
        )
        for index in range(PROJECT_COUNT)
    ]
    artifact_ids: list[str] = []
    for project in projects:
        for index in range(ARTIFACTS_PER_PROJECT):
            artifact_ids.append(
                repository.create_artifact(
                    project.project_id,
                    "brief",
                    f"规模检查素材-{index:02d}",
                ).artifact_id
            )
    create_ms = (time.perf_counter() - create_started) * 1000

    read_started = time.perf_counter()
    listed_projects = repository.list_projects()
    listed_artifacts_by_project = {
        project.project_id: repository.list_artifacts(project.project_id)
        for project in listed_projects
    }
    read_ms = (time.perf_counter() - read_started) * 1000
    per_project_counts = sorted(len(items) for items in listed_artifacts_by_project.values())

    with sqlite3.connect(repository.db_path) as conn:
        project_rows = conn.execute(
            "SELECT COUNT(*) FROM content_projects WHERE status = 'active'"
        ).fetchone()[0]
        artifact_rows = conn.execute(
            "SELECT COUNT(*) FROM artifacts WHERE status <> 'archived'"
        ).fetchone()[0]

    result: dict[str, Any] = {
        "status": "passed_local_bounded",
        "scope": "temporary_sqlite_only",
        "project_target": PROJECT_COUNT,
        "artifact_target": ARTIFACT_COUNT,
        "projects_created": len(projects),
        "artifacts_created": len(artifact_ids),
        "projects_read": len(listed_projects),
        "artifacts_read": sum(per_project_counts),
        "active_project_rows": int(project_rows),
        "active_artifact_rows": int(artifact_rows),
        "artifacts_per_project": per_project_counts,
        "create_ms": round(create_ms, 3),
        "read_ms": round(read_ms, 3),
        "api_started": False,
        "browser_actions": 0,
        "external_actions": 0,
    }
    valid = (
        len(projects) == PROJECT_COUNT
        and len(artifact_ids) == ARTIFACT_COUNT
        and len(listed_projects) == PROJECT_COUNT
        and sum(per_project_counts) == ARTIFACT_COUNT
        and per_project_counts == [ARTIFACTS_PER_PROJECT] * PROJECT_COUNT
        and int(project_rows) == PROJECT_COUNT
        and int(artifact_rows) == ARTIFACT_COUNT
    )
    if not valid:
        result["status"] = "failed"
        raise RuntimeError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pixelle-rollout-scale-") as runtime_dir:
        result = run_scale_check(Path(runtime_dir) / "app-center.sqlite")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
