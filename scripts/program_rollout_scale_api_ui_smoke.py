"""Exercise the bounded 100-project/1,000-artifact fixture through local API/UI.

This complements the repository-only scale check.  It starts an isolated
FastAPI process and Vite development server, then reads the same temporary
SQLite fixture through the content-project and artifact endpoints and through
the real React digital-human route.  No provider, browser platform, account,
upload, or final-publish action is involved.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from pixelle_video.app_center.repository import AppCenterRepository

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "program-rollout-scale-api-ui-token"
PROJECT_COUNT = 100
ARTIFACT_COUNT = 1000
ARTIFACTS_PER_PROJECT = 10
API_PORT = 8113
UI_PORT = 4175


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(percentile * len(ordered)) - 1))
    return ordered[index]


def _request_json(url: str, headers: dict[str, str] | None = None) -> tuple[int, Any]:
    request = Request(url, headers=headers or {})
    with urlopen(request, timeout=10) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _wait_for(url: str, headers: dict[str, str] | None = None, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, _ = _request_json(url, headers)
            if status < 500:
                return
        except Exception as exc:  # pragma: no cover - startup timing
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def _wait_for_http(url: str, timeout: float = 30) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=5) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - startup timing
            last_error = exc
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def _port_is_bindable(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _stop(process: subprocess.Popen[bytes] | None, port: int) -> bool:
    if process is None or process.poll() is not None:
        return _port_is_bindable(port)
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    return process.poll() is not None and _port_is_bindable(port)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _user_data_signature() -> dict[str, Any]:
    """Hash user-persistent paths without reading any payload into evidence."""

    roots = [
        ROOT / "data" / "app_center.sqlite",
        ROOT / "data" / "desktop_tasks.sqlite",
        ROOT / "data" / "publishing" / "publishing.sqlite3",
        ROOT / "data" / "ip_broadcast_sessions",
    ]
    signature: dict[str, Any] = {}
    for root in roots:
        key = str(root.relative_to(ROOT))
        if not root.exists():
            signature[key] = {"exists": False}
            continue
        if root.is_file():
            stat = root.stat()
            signature[key] = {
                "exists": True,
                "kind": "file",
                "sha256": _hash_file(root),
                "size": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
            }
            continue
        entries: list[dict[str, Any]] = []
        for item in sorted(root.rglob("*")):
            if not item.is_file():
                continue
            stat = item.stat()
            entries.append(
                {
                    "path": str(item.relative_to(root)),
                    "sha256": _hash_file(item),
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        signature[key] = {"exists": True, "kind": "directory", "entries": entries}
    return signature


def _global_app_center_signature() -> tuple[bool, int, int, int, int] | None:
    path = ROOT / "data" / "app_center.sqlite"
    if not path.exists():
        return None
    stat = path.stat()
    with sqlite3.connect(path) as conn:
        projects = int(conn.execute("SELECT COUNT(*) FROM content_projects").fetchone()[0])
        artifacts = int(conn.execute("SELECT COUNT(*) FROM artifacts").fetchone()[0])
    return (True, projects, artifacts, stat.st_mtime_ns, stat.st_size)


def _prepare_fixture(db_path: Path) -> list[str]:
    repository = AppCenterRepository(db_path)
    project_ids: list[str] = []
    for project_index in range(PROJECT_COUNT):
        project = repository.create_project(
            f"API/UI规模检查项目-{project_index:03d}",
            "PROGRAM-ROLLOUT bounded API/UI scale check",
        )
        project_ids.append(project.project_id)
        for artifact_index in range(ARTIFACTS_PER_PROJECT):
            repository.create_artifact(project.project_id, "copywriting", f"API/UI素材-{artifact_index:02d}")
    return project_ids


def run_scale_api_ui_check(runtime_root: str | Path) -> dict[str, Any]:
    runtime_root = Path(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)
    app_db = runtime_root / "app-center.sqlite"
    tasks_db = runtime_root / "tasks.sqlite"
    publishing_db = runtime_root / "publishing.sqlite"
    project_ids = _prepare_fixture(app_db)
    global_before = _global_app_center_signature()
    user_data_before = _user_data_signature()
    env = {
        **os.environ,
        # Browser-based UI measurement uses the local CORS development mode;
        # the isolated database and no-op flags still keep this probe local.
        "PIXELLE_DESKTOP_MODE": "0",
        "PIXELLE_DESKTOP_TOKEN": TOKEN,
        "PIXELLE_LOCAL_CAPABILITY": TOKEN,
        "PIXELLE_APP_CENTER_DB": str(app_db),
        "PIXELLE_DESKTOP_TASKS_DB": str(tasks_db),
        "PIXELLE_PUBLISHING_DB": str(publishing_db),
        "PIXELLE_APP_CENTER_CONTENT_APPS": "true",
        "PIXELLE_APP_CENTER_DIGITAL_HUMAN": "true",
        "PIXELLE_ASSET_CENTER_V2": "true",
        "PIXELLE_PUBLISH_V2_ENABLED": "false",
        "VITE_API_BASE_URL": f"http://127.0.0.1:{API_PORT}",
        "VITE_DESKTOP_TOKEN": TOKEN,
        "VITE_APP_CENTER_SHELL": "true",
        "VITE_CONTENT_PROJECTS": "true",
        "VITE_CONTENT_APPS": "true",
        "VITE_APP_CENTER_DIGITAL_HUMAN": "true",
        "VITE_APP_CENTER_NEW_NAV": "true",
        "VITE_ASSET_CENTER_V2": "true",
    }
    headers = {
        "X-Pixelle-Desktop-Token": TOKEN,
        "X-Pixelle-Local-Capability": TOKEN,
        "Origin": "tauri://localhost",
    }
    api: subprocess.Popen[bytes] | None = None
    ui: subprocess.Popen[bytes] | None = None
    browser = None
    playwright = None
    result: dict[str, Any] | None = None
    try:
        api = subprocess.Popen(
            [sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", str(API_PORT)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_for(f"http://127.0.0.1:{API_PORT}/health")
        project_list_ms: list[float] = []
        listed_project_ids: list[str] = []
        for _ in range(10):
            started = time.perf_counter()
            status, projects = _request_json(f"http://127.0.0.1:{API_PORT}/api/content-projects", headers)
            project_list_ms.append((time.perf_counter() - started) * 1000)
            if status != 200 or not isinstance(projects, list) or len(projects) != PROJECT_COUNT:
                raise RuntimeError("content-project API did not return 100 projects")
            listed_project_ids = [str(item["project_id"]) for item in projects]

        artifacts_started = time.perf_counter()
        artifact_total = 0
        artifact_project_reads = 0
        for project_id in listed_project_ids:
            status, artifacts = _request_json(
                f"http://127.0.0.1:{API_PORT}/api/content-projects/{project_id}/artifacts",
                headers,
            )
            if status != 200 or not isinstance(artifacts, list) or len(artifacts) != ARTIFACTS_PER_PROJECT:
                raise RuntimeError(f"artifact API did not return 10 artifacts for {project_id}")
            artifact_project_reads += 1
            artifact_total += len(artifacts)
        artifact_read_ms = (time.perf_counter() - artifacts_started) * 1000

        ui = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(UI_PORT)],
            cwd=ROOT / "desktop",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _wait_for_http(f"http://127.0.0.1:{UI_PORT}/")
        from playwright.sync_api import sync_playwright

        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        ui_route_ms: list[float] = []
        ui_project_option_counts: list[int] = []
        ui_artifact_option_counts: list[int] = []
        route = f"http://127.0.0.1:{UI_PORT}/#/apps/digital-human-video"
        for _ in range(10):
            started = time.perf_counter()
            page.goto(route, wait_until="domcontentloaded", timeout=15_000)
            page.locator('section[aria-label="数字人口播应用"]').wait_for(state="visible", timeout=15_000)
            project_select = page.locator("#digital-human-project")
            project_select.wait_for(state="visible", timeout=15_000)
            try:
                page.wait_for_function(
                    "document.querySelector('#digital-human-project')?.options.length === 101",
                    timeout=15_000,
                )
            except Exception as exc:
                option_count = project_select.locator("option").count()
                body_text = page.locator("body").inner_text()[:2000]
                raise RuntimeError(f"project options={option_count}; body={body_text}") from exc
            page.get_by_role("tab", name="已有文案").click()
            artifact_select = page.locator('select[aria-label="来源产物"]')
            artifact_select.wait_for(state="visible", timeout=15_000)
            page.wait_for_function(
                "document.querySelector('select[aria-label=\"来源产物\"]')?.options.length === 11",
                timeout=15_000,
            )
            ui_project_option_counts.append(project_select.locator("option").count() - 1)
            ui_artifact_option_counts.append(artifact_select.locator("option").count() - 1)
            ui_route_ms.append((time.perf_counter() - started) * 1000)
        page.close()
        browser.close()
        browser = None
        playwright.stop()
        playwright = None
        api_released = _stop(api, API_PORT)
        ui_released = _stop(ui, UI_PORT)
        global_after = _global_app_center_signature()
        user_data_after = _user_data_signature()
        result = {
            "status": "passed_local_bounded",
            "scope": "temporary_sqlite_api_ui_only",
            "projects_created": len(project_ids),
            "projects_api_read": len(listed_project_ids),
            "artifacts_api_read": artifact_total,
            "artifact_project_reads": artifact_project_reads,
            "artifacts_per_project": ARTIFACTS_PER_PROJECT,
            "api_project_list_samples": len(project_list_ms),
            "api_project_list_p95_ms": round(_percentile(project_list_ms, 0.95), 3),
            "api_artifact_all_projects_ms": round(artifact_read_ms, 3),
            "ui_route_samples": len(ui_route_ms),
            "ui_route_p95_ms": round(_percentile(ui_route_ms, 0.95), 3),
            "ui_project_option_counts": sorted(set(ui_project_option_counts)),
            "ui_artifact_option_counts": sorted(set(ui_artifact_option_counts)),
            "api_started": True,
            "browser_actions": 0,
            "local_ui_browser_actions": 20,
            "external_actions": 0,
            "final_publish_clicks": 0,
            "global_app_center_db_unchanged": global_before == global_after,
            "global_app_center_db_mutations": 0 if global_before == global_after else 1,
            "user_data_unchanged": user_data_before == user_data_after,
            "user_data_mutations": 0 if user_data_before == user_data_after else 1,
            "user_data_paths_checked": sorted(user_data_before),
            "user_database_touched": user_data_before != user_data_after,
            "api_port_released": api_released,
            "ui_port_released": ui_released,
        }
        if not (
            result["projects_created"] == PROJECT_COUNT
            and result["projects_api_read"] == PROJECT_COUNT
            and result["artifacts_api_read"] == ARTIFACT_COUNT
            and result["artifact_project_reads"] == PROJECT_COUNT
            and result["ui_project_option_counts"] == [PROJECT_COUNT]
            and result["ui_artifact_option_counts"] == [ARTIFACTS_PER_PROJECT]
            and result["global_app_center_db_unchanged"]
            and result["user_data_unchanged"]
        ):
            raise RuntimeError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    finally:
        if browser is not None:
            browser.close()
        if playwright is not None:
            playwright.stop()
        api_released = _stop(api, API_PORT)
        ui_released = _stop(ui, UI_PORT)
        global_after = _global_app_center_signature()
        user_data_after = _user_data_signature()
        if result is not None:
            result["global_app_center_db_unchanged"] = global_before == global_after
            result["global_app_center_db_mutations"] = 0 if global_before == global_after else 1
            result["user_data_unchanged"] = user_data_before == user_data_after
            result["user_data_mutations"] = 0 if user_data_before == user_data_after else 1
            result["user_database_touched"] = user_data_before != user_data_after
            result["api_port_released"] = api_released
            result["ui_port_released"] = ui_released
    if result is None:
        raise RuntimeError("scale API/UI probe produced no result")
    if not (
        result["global_app_center_db_unchanged"]
        and result["user_data_unchanged"]
        and result["api_port_released"]
        and result["ui_port_released"]
    ):
        raise RuntimeError(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return result


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="pixelle-rollout-scale-api-ui-") as runtime_dir:
        result = run_scale_api_ui_check(runtime_dir)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        if not result["api_port_released"] or not result["ui_port_released"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
