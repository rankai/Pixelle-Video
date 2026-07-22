#!/usr/bin/env python3
"""Run real desktop recovery, archive/restore, and snapshot rollback smoke."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
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

from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

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
    return subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


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


def seed_asset(root: Path) -> dict[str, str]:
    fixture_dir = root / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    fixture = fixture_dir / "归档回滚素材.png"
    Image.new("RGB", (640, 360), (109, 93, 246)).save(fixture, format="PNG")
    repository = AssetLibraryRepository(root / "data")
    payload = fixture.read_bytes()
    upload = repository.create_upload_session(fixture.name, len(payload), "image")
    repository.append_upload_chunk(upload["upload_id"], payload)
    asset = repository.finalize_upload(upload["upload_id"])
    asset_id = str(asset["asset_id"])
    projection = repository.get_asset(asset_id)
    if not projection:
        raise RuntimeError("failed to load seeded asset projection")
    session_id = "uxc-recovery-snapshot-session"
    snapshot = repository.create_snapshot(asset_id, session_id, "visual")
    if not snapshot:
        raise RuntimeError("failed to create snapshot fixture")
    return {"asset_id": asset_id, "revision_id": str(projection["current_revision_id"]), "session_id": session_id}


async def enter_asset_center(page: Page, base_url: str) -> None:
    await page.goto(base_url, wait_until="networkidle")
    await page.get_by_text("企业资产库", exact=True).first.click()
    await page.locator(".asset-center-v2").wait_for(timeout=15000)


async def run_scenario(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    video_dir = output_dir / "raw-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="asset-center-uxc-recovery-root-") as root_name:
        isolated_root = Path(root_name)
        fixture = seed_asset(isolated_root)
        env = os.environ.copy() | {
            "PIXELLE_VIDEO_ROOT": str(isolated_root),
            "PIXELLE_ASSET_CENTER_V2": "true",
            "PIXELLE_ASSET_CENTER_SMB_UX": "true",
        }
        api_port = "8122"
        web_port = "1442"
        api_url = f"http://127.0.0.1:{api_port}"
        web_url = f"http://127.0.0.1:{web_port}/"
        api = start_process([sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", api_port], ROOT, env)
        vite = start_process(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", web_port],
            ROOT / "desktop",
            env | {"VITE_API_BASE_URL": api_url, "VITE_ASSET_CENTER_V2": "true", "VITE_ASSET_CENTER_SMB_UX": "true"},
        )
        try:
            wait_for_url(f"{api_url}/health")
            wait_for_url(web_url)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context: BrowserContext = await browser.new_context(viewport={"width": 1440, "height": 900}, record_video_dir=str(video_dir))
                page: Page = await context.new_page()
                failed_once = False

                async def fail_first_library_request(route, request) -> None:
                    nonlocal failed_once
                    if not failed_once and request.method == "GET" and "/api/v2/library/items?" in request.url:
                        failed_once = True
                        await route.abort()
                        return
                    await route.continue_()

                await enter_asset_center(page, web_url)
                await page.route("**/api/v2/library/items**", fail_first_library_request)
                await page.get_by_role("button", name="刷新资产").click()
                error = page.locator(".asset-center-v2-error[role='alert']")
                await error.wait_for(timeout=10000)
                error_text = await error.inner_text()
                await error.get_by_role("button", name="重试").click()
                card = page.locator(".asset-center-v2-card").filter(has_text="归档回滚素材").first
                await card.wait_for(timeout=15000)
                service_recovery = failed_once and "127.0.0.1" not in error_text and await error.count() == 0
                await page.screenshot(path=str(output_dir / "uxc-recovery-after-retry.png"), full_page=True)

                await card.click()
                detail = page.get_by_role("dialog", name="归档回滚素材详情")
                await detail.wait_for(timeout=10000)
                await detail.get_by_role("button", name="归档").click()
                await detail.wait_for(state="hidden", timeout=10000)
                archived_response = await page.request.get(f"{api_url}/api/v2/library/items?kind=image&include_archived=true&limit=50")
                archived = await archived_response.json()
                archived_item = next(item for item in archived["items"] if item["resource_id"] == fixture["asset_id"])
                snapshot_before_response = await page.request.get(f"{api_url}/api/v2/sessions/{fixture['session_id']}/resource-snapshots")
                snapshot_before_restore = await snapshot_before_response.json()

                await page.get_by_role("button", name="显示已归档").click()
                archived_card = page.locator(".asset-center-v2-card").filter(has_text="归档回滚素材").first
                await archived_card.wait_for(timeout=10000)
                await archived_card.click()
                archived_detail = page.get_by_role("dialog", name="归档回滚素材详情")
                await archived_detail.get_by_role("button", name="恢复").click()
                await archived_detail.get_by_role("button", name="归档").wait_for(timeout=10000)
                restored_response = await page.request.get(f"{api_url}/api/v2/library/items?kind=image&limit=50")
                restored = await restored_response.json()
                restored_item = next(item for item in restored["items"] if item["resource_id"] == fixture["asset_id"])
                snapshot_after_response = await page.request.get(f"{api_url}/api/v2/sessions/{fixture['session_id']}/resource-snapshots")
                snapshot_after_restore = await snapshot_after_response.json()
                await page.screenshot(path=str(output_dir / "uxc-archive-restore-snapshot.png"), full_page=True)
                await context.close()
                await browser.close()
                recordings = sorted(path.name for path in video_dir.glob("*"))
        finally:
            stop_process(vite)
            stop_process(api)
    snapshot_before = snapshot_before_restore.get("items", [])
    snapshot_after = snapshot_after_restore.get("items", [])
    snapshot_intact = bool(snapshot_before) and bool(snapshot_after) and snapshot_before[0]["resource_id"] == fixture["asset_id"] == snapshot_after[0]["resource_id"]
    report = {
        "schema_version": "asset-center-uxc-recovery-rollback-desktop-e2e-v1",
        "status": "pass" if service_recovery and archived_item["status"] == "archived" and restored_item["status"] == "ready" and snapshot_intact else "fail",
        "environment": {"surface": "real Vite + FastAPI desktop web surface", "isolated_data_root": True, "viewport": "1440x900", "target_user_study": False, "release_device_signoff": False},
        "service_recovery": {"connection_failure_injected": failed_once, "error_shown_without_api_address": "127.0.0.1" not in error_text, "retry_recovered_asset_list": service_recovery, "screenshot": "uxc-recovery-after-retry.png"},
        "archive_restore": {"archived_status": archived_item["status"], "restored_status": restored_item["status"], "screenshot": "uxc-archive-restore-snapshot.png"},
        "snapshot": {"session_id": fixture["session_id"], "before_restore_count": len(snapshot_before), "after_restore_count": len(snapshot_after), "resource_id_stable": snapshot_intact},
        "recordings": recordings,
        "notes": ["The service failure was injected at the browser network boundary; retry then used the real Vite/FastAPI API.", "Archive/restore was selected through the real detail dialog; the pre-existing resource snapshot remained resolvable.", "This technical evidence does not replace target-user or release-device sign-off."],
    }
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/migrations/asset-center-uxc-recovery-rollback-desktop-e2e-2026-07-18"))
    args = parser.parse_args()
    report = asyncio.run(run_scenario(args.output_dir))
    print(f"UX-C recovery/rollback desktop E2E: {report['status']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
