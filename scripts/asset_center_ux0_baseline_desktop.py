#!/usr/bin/env python3
"""Record the current V2 desktop baseline for the seven UX-A tasks.

The runner uses an isolated data root and the real Vite/FastAPI desktop
surface. It is a reproducible current-version baseline, not a target-user
study, release-device sign-off, or evidence that UX-A has passed.
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

from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

ROOT = Path(__file__).resolve().parents[1]
API_PORT = 8110
WEB_PORT = 1430
API_BASE = f"http://127.0.0.1:{API_PORT}"
WEB_BASE = f"http://127.0.0.1:{WEB_PORT}"


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


def write_media_fixtures(root: Path) -> dict[str, Path | list[Path]]:
    fixture_dir = root / "ux0-baseline-fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    shop = fixture_dir / "门店招牌.png"
    logo = fixture_dir / "品牌Logo.png"
    archive = fixture_dir / "待归档图片.png"
    Image.new("RGB", (720, 1280), (92, 60, 164)).save(shop, format="PNG")
    Image.new("RGBA", (480, 240), (251, 113, 133, 255)).save(logo, format="PNG")
    Image.new("RGBA", (1200, 320), (0, 0, 0, 0)).save(archive, format="PNG")
    video = fixture_dir / "门店演示.mp4"
    audio = fixture_dir / "品牌BGM.wav"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=coral:s=320x568:d=1.5",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1.5",
            str(audio),
        ],
        check=True,
    )
    batch = []
    for index in range(10):
        path = fixture_dir / f"商品基线-{index + 1:02d}.png"
        Image.new("RGB", (320 + index * 4, 240 + index * 3), (60 + index * 12, 72 + index * 8, 140 + index * 7)).save(path, format="PNG")
        batch.append(path)
    return {"shop": shop, "logo": logo, "archive": archive, "video": video, "audio": audio, "batch": batch}


def seed_asset_kernel(data_root: Path, fixtures: dict[str, Path | list[Path]]) -> dict[str, str]:
    repository = AssetLibraryRepository(data_root)

    def ingest(kind: str, path: Path, name: str) -> dict[str, object]:
        session = repository.create_upload_session(path.name, path.stat().st_size, kind, name=name)
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                repository.append_upload_chunk(session["upload_id"], chunk)
        return repository.finalize_upload(session["upload_id"])

    shop = ingest("image", fixtures["shop"], "门店招牌")["asset_id"]
    logo = ingest("image", fixtures["logo"], "品牌Logo")["asset_id"]
    archive = ingest("image", fixtures["archive"], "待归档图片")["asset_id"]
    video = ingest("video", fixtures["video"], "门店演示视频")["asset_id"]
    audio = ingest("audio", fixtures["audio"], "品牌BGM")["asset_id"]
    repository.create_brand_kit(
        {
            "brand_id": "baseline-brand",
            "brand_name": "基线门店品牌",
            "logo_asset_id": logo,
            "default_bgm_asset_id": audio,
            "primary_color": "#7c3aed",
            "secondary_color": "#fb7185",
            "font_family": "noto-sans-sc-bold",
            "ending_card_text": "到店报暗号立减",
            "store_address": "上海市静安区基线路 18 号",
            "phone": "021-60000000",
            "coupon_phrase": "新客到店享双人套餐",
        }
    )
    digital_human = repository.create_digital_human_profile(
        {
            "profile_id": "baseline-digital-human",
            "name": "基线张老板",
            "poster_asset_id": shop,
            "source_asset_id": shop,
            "scene_name": "门店招牌场景",
            "shot_size": "medium",
            "location": "门店前台",
        }
    )
    repository.create_digital_human_scene(
        digital_human["resource_id"],
        {"name": "演示视频场景", "source_asset_id": video, "shot_size": "full", "location": "门店大厅"},
    )
    template_contract = json.loads((ROOT / "tests/fixtures/ux0/template-layout/valid.json").read_text(encoding="utf-8"))
    repository.create_template_revision(
        {
            "template_id": "baseline-template",
            "display_name": "基线门店模板",
            "short_description": "当前版基线模板",
            "schema_version": 2,
            "renderer_version": "ip-broadcast-composer-v2",
            "layout_contract": template_contract,
            "cover_contract": {"canvas_width": 1080, "canvas_height": 1920},
            "subtitle_contract": {"font_size": 48},
        }
    )
    return {"shop": str(shop), "logo": str(logo), "archive": str(archive), "video": str(video), "audio": str(audio), "archive_asset_id": str(archive), "digital_human": str(digital_human["resource_id"]), "video_asset_id": str(video), "template": "baseline-template"}


async def click_count(page: Page) -> int:
    return int(await page.evaluate("window.__uxClickCount || 0"))


async def visible_errors(page: Page) -> list[str]:
    values = await page.locator('[role="alert"]').all_inner_texts()
    return [value.strip() for value in values if value.strip()]


async def open_assets(page: Page) -> None:
    print("open assets: start", flush=True)
    await page.locator(".side-menu .ant-menu-item").filter(has_text="企业资产库").click()
    try:
        await page.wait_for_selector(".asset-center-v2, .asset-center", state="visible", timeout=15000)
    except Exception:
        print((await page.locator("body").inner_text())[:1800], flush=True)
        raise
    print("open assets: ready", flush=True)


async def open_production_with_script(page: Page, request, script: str) -> None:
    print("open production: click", flush=True)
    await page.locator(".side-menu .ant-menu-item").filter(has_text="口播剪辑").click()
    try:
        await page.wait_for_selector(".workspace", state="visible", timeout=15000)
    except Exception:
        print((await page.locator("body").inner_text())[:1200], flush=True)
        raise
    print("open production: ready", flush=True)
    session_id = await page.evaluate("window.localStorage.getItem('pixelle_ipb_session_id')")
    if not session_id:
        raise RuntimeError("production session was not created")
    response = await request.patch(f"{API_BASE}/api/ip-broadcast/sessions/{session_id}/config", data={"source_mode": "paste", "source_text": script, "final_script": script, "copywriting_confirmed": True})
    if not response.ok:
        raise RuntimeError(f"session seed failed: {response.status} {await response.text()}")
    await page.reload(wait_until="networkidle")
    await page.locator(".side-menu .ant-menu-item").filter(has_text="口播剪辑").click()
    await page.wait_for_selector(".workspace", state="visible", timeout=15000)
    await page.get_by_text("成片", exact=True).last.click()
    await page.get_by_role("button", name=re.compile("打开画面规划|手动调整")).click()
    await page.wait_for_selector(".storyboard-layout", state="visible", timeout=10000)


async def task_record(page: Page, name: str, action, screenshot: Path) -> dict[str, object]:
    await page.evaluate("window.__uxClickCount = 0")
    started = time.monotonic()
    status = "pass"
    error = ""
    try:
        print(f"task {name}: start", flush=True)
        await asyncio.wait_for(action(), timeout=45)
    except Exception as exc:
        status = "observed_error"
        error = str(exc)
    elapsed_ms = round((time.monotonic() - started) * 1000)
    await page.screenshot(path=str(screenshot), full_page=True)
    print(f"task {name}: {status} ({elapsed_ms}ms)", flush=True)
    return {"status": status, "click_count": await click_count(page), "elapsed_ms": elapsed_ms, "errors": ([error] if error else []) + await visible_errors(page), "screenshot": screenshot.name, "task": name}


async def run_baseline(output_dir: Path, *, headed: bool = False) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    video_dir = output_dir / "raw-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    tasks: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="asset-center-ux0-baseline-root-") as root_name:
        isolated_root = Path(root_name)
        fixtures = write_media_fixtures(isolated_root)
        data_root = isolated_root / "data"
        data_root.mkdir(parents=True, exist_ok=True)
        seeded = seed_asset_kernel(data_root, fixtures)
        env = os.environ.copy()
        env.update({"PIXELLE_VIDEO_ROOT": str(isolated_root), "PIXELLE_ASSET_CENTER_V2": "true", "PIXELLE_ASSET_CENTER_SMB_UX": "false"})
        api = start_process([sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", str(API_PORT)], ROOT, env)
        web_env = env | {"VITE_API_BASE_URL": API_BASE, "VITE_ASSET_CENTER_V2": "true", "VITE_ASSET_CENTER_SMB_UX": "false"}
        vite = start_process(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(WEB_PORT)], ROOT / "desktop", web_env)
        try:
            wait_for_url(f"{API_BASE}/health")
            wait_for_url(f"{WEB_BASE}/")
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=not headed)
                context: BrowserContext = await browser.new_context(viewport={"width": 1440, "height": 1000}, record_video_dir=str(video_dir))
                await context.add_init_script("window.__uxClickCount = 0; document.addEventListener('click', () => window.__uxClickCount += 1, true);")
                page = await context.new_page()
                page_errors: list[str] = []
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                await page.goto(f"{WEB_BASE}/", wait_until="networkidle")

                async def task_find_image() -> None:
                    await open_production_with_script(page, context.request, "第一段介绍门店环境\n第二段介绍招牌菜品")
                    await page.locator(".storyboard-timeline input[type=checkbox]").first.check()
                    await page.get_by_role("button", name="勾选段落成组").click()
                    await page.locator(".group-card select").select_option("uploaded_image")
                    await page.get_by_role("button", name="选择图片素材").click()
                    await page.get_by_role("button", name=re.compile("门店招牌")).click()
                    await page.get_by_role("button", name="确认使用").click()
                    await page.get_by_role("button", name="保存规划").click()
                    await page.wait_for_selector(".storyboard-layout", state="hidden")

                tasks.append(await task_record(page, "找到已有门店图片并用于画面规划", task_find_image, output_dir / "ux0-01-find-image-and-storyboard.png"))

                await open_assets(page)

                async def task_batch_upload() -> None:
                    await page.get_by_role("button", name="图片素材").click()
                    await page.get_by_role("button", name="添加图片素材").click()
                    await page.get_by_label("图片素材").set_input_files([str(path) for path in fixtures["batch"]])

                tasks.append(await task_record(page, "批量上传 10 张商品图片并打标签", task_batch_upload, output_dir / "ux0-02-batch-upload-10.png"))
                if await page.locator(".asset-modal").count():
                    await page.get_by_role("button", name="关闭", exact=True).click()

                async def task_add_digital_human() -> None:
                    await page.get_by_role("button", name="形象库").click()
                    await page.get_by_role("button", name="添加数字人形象").click()
                    await page.locator(".asset-modal input").first.fill("基线数字人")
                    await page.get_by_label("图片或视频形象").set_input_files(str(fixtures["shop"]))
                    await page.get_by_role("button", name="保存到素材库").click()
                    await page.wait_for_selector(".asset-modal", state="hidden", timeout=30000)

                tasks.append(await task_record(page, "添加带封面和演示视频的数字人并选择场景", task_add_digital_human, output_dir / "ux0-03-add-digital-human-scene.png"))
                tasks[-1]["limitations"] = ["当前版只接受一个图片或视频形象文件，没有封面/演示视频双字段和场景选择。"]
                if await page.locator(".asset-preview-modal").count():
                    await page.get_by_role("button", name="关闭", exact=True).click()
                if await page.locator(".asset-modal").count():
                    await page.get_by_role("button", name="关闭", exact=True).click()

                async def task_brand() -> None:
                    await page.get_by_role("button", name="品牌包").click()
                    await page.get_by_placeholder("品牌/门店名称").fill("基线可用品牌")
                    await page.get_by_placeholder("品牌色").fill("#7c3aed")
                    await page.get_by_placeholder("门店地址").fill("上海市静安区体验路 18 号")
                    await page.get_by_placeholder("电话").fill("021-61111111")
                    await page.get_by_placeholder("团购口令").fill("新客到店享双人套餐")
                    await page.get_by_role("button", name="保存品牌包").click()

                tasks.append(await task_record(page, "修改品牌 Logo/BGM/地址并套用", task_brand, output_dir / "ux0-04-brand-apply.png"))
                tasks[-1]["limitations"] = ["当前版可保存地址、电话和团购口令，但没有 Logo 字段和稳定 BGM 资产选择，也没有明确生产 picker 确认。"]

                async def task_template() -> None:
                    await page.get_by_role("button", name="画面模板库").click()
                    await page.get_by_text("基线门店模板", exact=True).wait_for(timeout=15000)
                    raise RuntimeError("当前版模板库仅支持浏览，没有字幕/封面位置编辑或保存预览控件")

                tasks.append(await task_record(page, "预览模板字幕/封面位置后用于成片", task_template, output_dir / "ux0-05-template-preview.png"))

                failed_once = True

                async def fail_once(route, request) -> None:
                    nonlocal failed_once
                    if failed_once and request.method == "PUT" and request.url.endswith("/content"):
                        failed_once = False
                        await route.fulfill(status=500, content_type="application/json", body=b'{"detail":"baseline synthetic failure"}')
                        return
                    await route.continue_()

                await page.route("**/api/v2/uploads/*/content", fail_once)

                async def task_upload_recovery() -> None:
                    await page.get_by_role("button", name="图片素材").click()
                    await page.get_by_role("button", name="添加图片素材").click()
                    await page.locator(".asset-modal input").first.fill("基线失败恢复")
                    await page.get_by_label("图片素材").set_input_files(str(fixtures["batch"][0]))
                    await page.get_by_role("button", name="保存到资产库").click()
                    await page.get_by_text(re.compile("baseline synthetic failure|HTTP 500|失败"), exact=False).wait_for(timeout=15000)
                    await page.get_by_role("button", name="保存到资产库").click()
                    await page.get_by_text("基线失败恢复", exact=True).wait_for(timeout=30000)

                tasks.append(await task_record(page, "上传失败后恢复", task_upload_recovery, output_dir / "ux0-06-upload-failure-recovery.png"))
                await page.unroute("**/api/v2/uploads/*/content", fail_once)
                if await page.locator(".asset-modal").count():
                    await page.get_by_role("button", name="关闭", exact=True).click()

                async def task_archive_restore() -> None:
                    await page.get_by_role("button", name="图片素材", exact=True).click()
                    archive_card = page.locator(".asset-card").filter(has_text="待归档图片")
                    await archive_card.get_by_role("button", name="删除", exact=True).click()
                    await page.get_by_role("button", name="确认删除图片素材").click()
                    await archive_card.wait_for(state="hidden", timeout=15000)
                    raise RuntimeError("当前版可归档但没有恢复入口；只验证归档成功，恢复需要兼容 API")

                tasks.append(await task_record(page, "归档后恢复资产", task_archive_restore, output_dir / "ux0-07-archive-restore.png"))
                await context.close()
                await browser.close()
                recording_names = sorted(path.name for path in video_dir.glob("*"))
                report = {
                    "schema_version": "asset-center-ux0-current-baseline-v1",
                    "status": "evidence_recorded" if len(tasks) == 7 else "fail",
                    "environment": {
                        "surface": "real Vite + FastAPI desktop web surface",
                        "isolated_data_root": True,
                        "viewport": "1440x1000",
                        "asset_center_v2": True,
                        "asset_center_smb_ux": False,
                        "target_user_study": False,
                        "release_device_signoff": False,
                    },
                    "tasks": tasks,
                    "recordings": recording_names,
                    "seeded": seeded,
                    "page_errors": page_errors,
                    "notes": [
                        "This is the current-version interaction baseline requested by UX-0, recorded with synthetic isolated data.",
                        "It does not replace the UX-E five-person study or release-device sign-off.",
                        "The task durations include real desktop UI waits and are not user-study results.",
                    ],
                }
        finally:
            stop_process(vite)
            stop_process(api)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/migrations/asset-center-ux0-current-baseline-2026-07-18"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run_baseline(args.output_dir, headed=args.headed))
    print(f"UX-0 current baseline: {report['status']} ({len(report['tasks'])}/7 tasks recorded)")
    return 0 if report["status"] == "evidence_recorded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
