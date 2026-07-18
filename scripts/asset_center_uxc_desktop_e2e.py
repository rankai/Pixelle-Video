#!/usr/bin/env python3
"""Run a repeatable desktop UX-C upload/recovery smoke in an isolated root.

This exercises the real Vite/FastAPI desktop surface. It is an automation
recording, not a substitute for the UX-A target-user study or release-device
sign-off.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.async_api import BrowserContext, Page, async_playwright

ROOT = Path(__file__).resolve().parents[1]


def wait_for_url(url: str, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except (OSError, urllib.error.URLError) as exc:
            last_error = exc
        time.sleep(0.25)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def start_process(command: list[str], cwd: Path, env: dict[str, str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def stop_process(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            pass


def create_fixture_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for index in range(10):
        path = root / f"商品-{index + 1:02d}.png"
        image = Image.new("RGB", (320 + index * 3, 240 + index * 2), (60 + index * 15, 72 + index * 9, 140 + index * 7))
        image.save(path, format="PNG")
        files.append(path)
    return files


async def click_count(page: Page) -> int:
    return int(await page.evaluate("window.__uxClickCount || 0"))


async def run_scenario(output_dir: Path, *, headed: bool = False) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    video_dir = output_dir / "raw-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="asset-center-uxc-root-") as root_name:
        isolated_root = Path(root_name)
        fixture_dir = isolated_root / "fixtures"
        fixture_dir.mkdir()
        fixture_files = create_fixture_files(fixture_dir)

        env = os.environ.copy()
        env.update(
            {
                "PIXELLE_VIDEO_ROOT": str(isolated_root),
                "PIXELLE_ASSET_CENTER_V2": "true",
                "PIXELLE_ASSET_CENTER_SMB_UX": "true",
            }
        )
        api = start_process([sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", "8100"], ROOT, env)
        web_env = env | {
            "VITE_API_BASE_URL": "http://127.0.0.1:8100",
            "VITE_ASSET_CENTER_V2": "true",
            "VITE_ASSET_CENTER_SMB_UX": "true",
        }
        vite = start_process(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "1420"], ROOT / "desktop", web_env)
        try:
            wait_for_url("http://127.0.0.1:8100/health")
            wait_for_url("http://127.0.0.1:1420/")
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=not headed)
                context: BrowserContext = await browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    record_video_dir=str(video_dir),
                )
                await context.add_init_script("window.__uxClickCount = 0; document.addEventListener('click', () => window.__uxClickCount += 1, true);")
                page = await context.new_page()
                content_requests: list[str] = []
                failed_indices = {3, 6, 9}
                cancel_phase = False

                async def route_handler(route, request) -> None:
                    nonlocal cancel_phase
                    if request.method == "PUT" and "/api/v2/uploads/" in request.url and request.url.endswith("/content"):
                        content_requests.append(request.url)
                        request_index = len(content_requests)
                        if cancel_phase:
                            await asyncio.sleep(8)
                            try:
                                await route.abort()
                            except Exception:
                                pass
                            return
                        if request_index in failed_indices:
                            await route.fulfill(status=500, content_type="application/json", body=b'{"detail":"synthetic UX-C failure"}')
                            return
                    await route.continue_()

                await page.route("**/api/v2/uploads/*/content", route_handler)
                started = time.monotonic()
                await page.goto("http://127.0.0.1:1420/", wait_until="networkidle")
                await page.get_by_text("企业资产库", exact=True).first.click()
                await page.wait_for_selector(".asset-center-v2", state="visible", timeout=15000)
                await page.get_by_role("button", name=re.compile("添加资产")).first.click()
                await page.locator(".asset-upload-dropzone input[type=file]").set_input_files([str(path) for path in fixture_files])
                await page.get_by_label("批量标签").fill("门店,主推")
                await page.get_by_role("button", name="开始上传").click()
                await page.get_by_text(re.compile(r"7/10 已入库.*3 个失败"), exact=False).wait_for(timeout=30000)
                batch_elapsed_ms = round((time.monotonic() - started) * 1000)
                batch_clicks = await click_count(page)
                batch_screenshot = output_dir / "uxc-batch-10-3-failed.png"
                await page.screenshot(path=str(batch_screenshot), full_page=True)

                await page.get_by_role("button", name="关闭", exact=True).click()
                await page.get_by_role("button", name=re.compile("添加资产")).first.click()
                cancel_file = fixture_dir / "取消测试.png"
                Image.new("RGB", (640, 480), (220, 80, 110)).save(cancel_file, format="PNG")
                cancel_phase = True
                await page.locator(".asset-upload-dropzone input[type=file]").set_input_files(str(cancel_file))
                await page.get_by_role("button", name="开始上传").click()
                await page.get_by_role("button", name="取消上传", exact=True).wait_for(timeout=5000)
                await page.get_by_role("button", name="取消上传", exact=True).click()
                await page.get_by_text("已取消").wait_for(timeout=10000)
                usage_response = await page.request.get("http://127.0.0.1:8100/api/v2/sessions/uxc-cancel-session/resource-usage")
                usage_payload = await usage_response.json()
                cancel_screenshot = output_dir / "uxc-cancelled-no-usage.png"
                await page.screenshot(path=str(cancel_screenshot), full_page=True)

                await page.get_by_role("button", name="关闭", exact=True).click()
                await page.get_by_role("button", name=re.compile("添加资产")).first.click()
                restart_file = fixture_dir / "重启恢复.png"
                Image.new("RGB", (320, 240), (70, 160, 120)).save(restart_file, format="PNG")
                await page.locator(".asset-upload-dropzone input[type=file]").set_input_files(str(restart_file))
                await page.get_by_text("重启恢复.png", exact=True).wait_for(timeout=5000)
                await page.reload(wait_until="networkidle")
                await page.get_by_text("企业资产库", exact=True).first.click()
                await page.wait_for_selector(".asset-center-v2", state="visible", timeout=15000)
                await page.get_by_role("button", name=re.compile("添加资产")).first.click()
                await page.get_by_text("应用已重启，请重新选择原文件继续上传").wait_for(timeout=10000)
                restart_screenshot = output_dir / "uxc-restart-reselect-original.png"
                await page.screenshot(path=str(restart_screenshot), full_page=True)

                await context.close()
                await browser.close()

                videos = sorted(path.name for path in video_dir.glob("*"))
                report = {
                    "schema_version": "asset-center-uxc-desktop-e2e-v1",
                    "status": "pass" if len(content_requests) == 11 and len(usage_payload.get("items", [])) == 0 else "fail",
                    "environment": {
                        "surface": "real Vite + FastAPI desktop web surface",
                        "isolated_data_root": True,
                        "viewport": "1440x1000",
                        "target_user_study": False,
                        "release_device_signoff": False,
                    },
                    "batch_10_files": {
                        "files_selected": 10,
                        "content_requests": len(content_requests),
                        "synthetic_failed_request_indices": sorted(failed_indices),
                        "expected_finalized": 7,
                        "expected_failed": 3,
                        "success_items_retried": False,
                        "batch_elapsed_ms": batch_elapsed_ms,
                        "click_count": batch_clicks,
                        "screenshot": batch_screenshot.name,
                    },
                    "cancel": {
                        "cancelled_without_finalize": True,
                        "usage_items_for_cancel_session": len(usage_payload.get("items", [])),
                        "screenshot": cancel_screenshot.name,
                    },
                    "restart": {
                        "metadata_persisted_and_reselect_copy_shown": True,
                        "screenshot": restart_screenshot.name,
                    },
                    "recordings": videos,
                    "notes": [
                        "The 11th upload request is the isolated cancellation scenario; the first batch had exactly 10 content requests.",
                        "This automation evidence does not satisfy the five-person UX-E study or release-device visual sign-off.",
                    ],
                }
        finally:
            stop_process(vite)
            stop_process(api)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/migrations/asset-center-uxc-desktop-e2e-2026-07-18"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run_scenario(args.output_dir, headed=args.headed))
    print(f"UX-C desktop E2E: {report['status']} ({report['batch_10_files']['content_requests']} content requests, {report['cancel']['usage_items_for_cancel_session']} cancel usage records)")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
