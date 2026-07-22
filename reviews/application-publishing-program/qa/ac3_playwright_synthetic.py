"""Bounded local UI smoke for AC-3; all app-center writes are mocked in the browser.

This is not a target-user study and never calls a real LLM/provider or publish API.
"""

import json
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, Route, sync_playwright


def run() -> None:
    projects: list[dict] = []
    runs: list[dict] = []
    blocked_unknown_writes: list[dict[str, str]] = []

    def fulfill(route: Route, payload: object, status: int = 200) -> None:
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))

    def api(route: Route) -> None:
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        if path == "/api/content-projects" and request.method == "GET":
            fulfill(route, projects)
            return
        if path == "/api/ip-broadcast/sessions" and request.method == "POST":
            fulfill(route, {
                "session_id": "pw-synthetic-session",
                "current_step": 1,
                "completed_steps": 0,
                "next_action": {"key": "copywriting", "step": 1, "label": "文案", "description": "合成预检", "disabled": False},
                "missing_requirements": [],
                "step_status": {},
                "notices": {},
                "artifacts": {},
                "state": {},
            })
            return
        if path == "/api/content-projects" and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            project = {
                "project_id": "pw-synthetic-project",
                "schema_version": 1,
                "name": body["name"],
                "status": "active",
                "primary_goal": body["primary_goal"],
                "brand_id": None,
                "current_context_snapshot_id": None,
                "created_at": "now",
                "updated_at": "now",
            }
            projects[:] = [project]
            fulfill(route, project)
            return
        if path == "/api/content-projects/pw-synthetic-project/context-snapshots":
            fulfill(route, None)
            return
        if path == "/api/app-runs" and request.method == "GET":
            fulfill(route, runs)
            return
        if path == "/api/app-runs" and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            run = {
                "app_run_id": "pw-synthetic-run",
                "project_id": body["project_id"],
                "app_id": body["app_id"],
                "app_version": body["app_version"],
                "state": "draft",
                "state_version": 1,
                "idempotency_key": body["idempotency_key"],
                "input_payload": body["input_payload"],
                "context_snapshot_id": None,
                "output_artifact_ids": [],
                "error_code": None,
                "archived_at": None,
                "created_at": "now",
                "updated_at": "now",
            }
            runs[:] = [run]
            fulfill(route, run)
            return
        if path == "/api/app-runs/pw-synthetic-run/execute" and request.method == "POST":
            runs[0]["state"] = "needs_review"
            runs[0]["state_version"] = 2
            fulfill(route, {"app_run_id": "pw-synthetic-run", "task_id": "pw-synthetic-task", "state": "queued"})
            return
        if path == "/api/app-runs/pw-synthetic-run/complete" and request.method == "POST":
            runs[0]["state"] = "completed"
            runs[0]["state_version"] = 3
            fulfill(route, runs[0])
            return
        # Prevent any unrecognised write from reaching the local API during this
        # browser-only smoke; read-only calls may continue for shell hydration.
        if path.startswith("/api/") and request.method != "GET":
            blocked_unknown_writes.append({"method": request.method, "path": path})
            fulfill(route, {})
            return
        route.continue_()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page: Page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.route("**/api/content-projects*", api)
        page.route("**/api/app-runs*", api)
        page.route("**/api/content-projects/**", api)
        page.route("**/api/app-runs/**", api)
        page.route("**/api/ip-broadcast/sessions*", api)
        page.route("**/api/**", api)
        page.goto("http://127.0.0.1:1420/#/apps", wait_until="networkidle")
        page.get_by_role("button", name="打开流程").first.click()
        page.get_by_placeholder("项目名称").fill("咖啡店老板")
        page.get_by_placeholder("本次营销目标").fill("下午茶到店")
        page.get_by_placeholder("产品或服务").fill("咖啡")
        page.get_by_role("button", name="保存草稿").click()
        page.get_by_role("button", name="创建运行草稿").click()
        page.get_by_role("button", name="执 行").click()
        page.get_by_role("button", name="确认完成").wait_for(timeout=5000)
        page.get_by_role("button", name="确认完成").click()
        screenshot_path = Path("docs/reviews/application-publishing-program/qa/AC-3-user-completion-playwright-synthetic.png")
        evidence_path = Path("docs/reviews/application-publishing-program/qa/AC-3-user-completion-playwright-synthetic.json")
        page.screenshot(path=str(screenshot_path), full_page=True)
        evidence = {
            "status": "passed",
            "scenario": "咖啡老板",
            "final_state": runs[0]["state"],
            "url": page.url,
            "api_write_policy": "app-center and unrecognised non-GET requests route-mocked; no local API writes",
            "blocked_unknown_write_count": len(blocked_unknown_writes),
            "blocked_unknown_writes": blocked_unknown_writes,
            "screenshot_sha256": sha256(screenshot_path.read_bytes()).hexdigest(),
            "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        }
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(evidence, ensure_ascii=False))
        browser.close()


if __name__ == "__main__":
    run()
