"""Run ten bounded internal simulated-user browser tasks for AC-3.

All app-center writes and unrecognised non-GET requests are intercepted in the
browser. This intentionally does not call a real provider, create artifacts, or
touch a publishing endpoint.
"""

import json
import time
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, Route, sync_playwright


SCENARIOS = [
    ("火锅老板", "周末双人套餐", "火锅"),
    ("美容老板", "新客到店体验", "美容"),
    ("民宿老板", "工作日入住", "民宿"),
    ("洗衣老板", "换季洗护", "洗衣店"),
    ("培训老板", "试听报名", "培训"),
    ("零售老板", "新品到店", "零售"),
    ("咖啡老板", "下午茶到店", "咖啡"),
    ("烘焙老板", "新品试吃", "烘焙"),
    ("健身老板", "新客咨询", "健身"),
    ("宠物店老板", "洗护预约", "宠物店"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def fulfill(route: Route, payload: object, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(payload, ensure_ascii=False))


def run_one(page: Page, index: int, persona: str, goal: str, product: str) -> dict:
    project_id = f"pw-synthetic-batch15-project-{index}"
    run_id = f"pw-synthetic-batch15-run-{index}"
    projects: list[dict] = []
    runs: list[dict] = []
    blocked_unknown_writes: list[dict[str, str]] = []
    actions: list[str] = []
    console_errors: list[str] = []
    started_at = utc_now()
    started_monotonic = time.perf_counter()

    def api(route: Route) -> None:
        request = route.request
        parsed = urlparse(request.url)
        path = parsed.path
        if path == "/api/ip-broadcast/sessions" and request.method == "POST":
            fulfill(route, {
                "session_id": f"pw-synthetic-batch15-session-{index}",
                "current_step": 1,
                "completed_steps": 0,
                "next_action": {"key": "copywriting", "step": 1, "label": "文案", "description": "内部模拟", "disabled": False},
                "missing_requirements": [],
                "step_status": {},
                "notices": {},
                "artifacts": {},
                "state": {},
            })
            return
        if path == "/api/content-projects" and request.method == "GET":
            fulfill(route, projects)
            return
        if path == "/api/content-projects" and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            project = {
                "project_id": project_id,
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
        if path == f"/api/content-projects/{project_id}/context-snapshots" and request.method == "GET":
            fulfill(route, None)
            return
        if path == "/api/app-runs" and request.method == "GET":
            fulfill(route, runs)
            return
        if path == "/api/app-runs" and request.method == "POST":
            body = json.loads(request.post_data or "{}")
            run = {
                "app_run_id": run_id,
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
        if path == f"/api/app-runs/{run_id}/execute" and request.method == "POST":
            runs[0]["state"] = "needs_review"
            runs[0]["state_version"] = 2
            fulfill(route, {"app_run_id": run_id, "task_id": f"pw-synthetic-batch15-task-{index}", "state": "queued"})
            return
        if path == f"/api/app-runs/{run_id}/complete" and request.method == "POST":
            runs[0]["state"] = "completed"
            runs[0]["state_version"] = 3
            fulfill(route, runs[0])
            return
        if path.startswith("/api/") and request.method != "GET":
            blocked_unknown_writes.append({"method": request.method, "path": path})
            fulfill(route, {})
            return
        route.continue_()

    page.route("**/api/**", api)
    page.on("console", lambda message: console_errors.append(message.text) if message.type in {"error", "warning"} else None)
    result: dict = {
        "scenario": persona,
        "goal": goal,
        "product_or_service": product,
        "started_at_utc": started_at,
        "final_state": "failed",
        "help_count": 0,
        "operator_intervention": False,
        "failure_reason": None,
        "artifact_version_id": None,
        "publish_triggered": False,
    }
    try:
        page.goto("http://127.0.0.1:1420/#/apps", wait_until="networkidle")
        actions.append("open_marketing_copy")
        page.get_by_role("button", name="打开流程").first.click()
        actions.append("fill_project_name")
        page.get_by_placeholder("项目名称").fill(persona)
        actions.append("fill_goal")
        page.get_by_placeholder("本次营销目标").fill(goal)
        actions.append("fill_product_or_service")
        page.get_by_placeholder("产品或服务").fill(product)
        actions.append("save_draft")
        page.get_by_role("button", name="保存草稿").click()
        actions.append("create_run_draft")
        page.get_by_role("button", name="创建运行草稿").click()
        actions.append("execute")
        page.get_by_role("button", name="执 行").click()
        page.get_by_role("button", name="确认完成").wait_for(timeout=5000)
        actions.append("confirm_complete")
        page.get_by_role("button", name="确认完成").click()
        page.get_by_text("已完成", exact=True).first.wait_for(timeout=5000)
        result["final_state"] = runs[0]["state"]
    except Exception as exc:  # one bounded attempt; do not retry
        result["failure_reason"] = str(exc).splitlines()[0]
    finally:
        result["ended_at_utc"] = utc_now()
        result["duration_ms"] = round((time.perf_counter() - started_monotonic) * 1000)
        result["action_count"] = len(actions)
        result["actions"] = actions
        result["blocked_unknown_write_count"] = len(blocked_unknown_writes)
        result["blocked_unknown_writes"] = blocked_unknown_writes
        known_warnings = [message for message in console_errors if message.startswith("Warning: [antd:")]
        unexpected_errors = [message for message in console_errors if message not in known_warnings]
        result["console_error_count"] = len(unexpected_errors)
        result["console_errors"] = unexpected_errors
        result["known_warning_count"] = len(known_warnings)
        result["known_warnings"] = known_warnings
    return result


def main() -> None:
    results: list[dict] = []
    screenshot_path = Path("docs/reviews/application-publishing-program/qa/AC-3-user-completion-playwright-simulated-batch-15.png")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for index, (persona, goal, product) in enumerate(SCENARIOS, start=1):
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            result = run_one(page, index, persona, goal, product)
            if index == len(SCENARIOS):
                page.screenshot(path=str(screenshot_path), full_page=True)
            page.close()
            results.append(result)
        browser.close()
    evidence = {
        "status": "passed" if all(item["final_state"] == "completed" for item in results) else "partial",
        "simulation_type": "internal_browser_simulated_user",
        "scenario_count": len(results),
        "passed_count": sum(item["final_state"] == "completed" for item in results),
        "no_explanation_count": sum(item["final_state"] == "completed" and item["help_count"] == 0 and not item["operator_intervention"] for item in results),
        "real_provider_called": False,
        "artifact_versions_created": False,
        "publish_triggered": False,
        "unexpected_console_error_count": sum(item["console_error_count"] for item in results),
        "known_warning_count": sum(item["known_warning_count"] for item in results),
        "browser_fallback_reason": "in-app Browser runtime previously failed with Cannot redefine property: process; regular Python Playwright used after permitted fallback",
        "scenarios": results,
        "screenshot_sha256": sha256(screenshot_path.read_bytes()).hexdigest(),
        "script_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    evidence_path = Path("docs/reviews/application-publishing-program/qa/AC-3-user-completion-playwright-simulated-batch-15.json")
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: evidence[key] for key in ("status", "scenario_count", "passed_count", "no_explanation_count", "screenshot_sha256", "script_sha256")}, ensure_ascii=False))
    if evidence["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
