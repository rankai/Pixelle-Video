#!/usr/bin/env python3
"""Run the real desktop picker -> production -> MP4 UX-C smoke.

The fixture uses an isolated data root and local ffmpeg media. It is a
repeatable release-surface check, not a substitute for the UX-E participant
study or release-device sign-off.
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
from playwright.async_api import (
    BrowserContext,
    Page,
    async_playwright,
)
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

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


def start_process(command: list[str], cwd: Path, env: dict[str, str], log_path: Path) -> subprocess.Popen[bytes]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("wb")
    process = subprocess.Popen(
        command,
        cwd=cwd,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log.close()
    return process


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


def run_ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args], check=True)


def create_media(root: Path) -> dict[str, Path]:
    media = root / "fixtures"
    media.mkdir(parents=True, exist_ok=True)
    video = media / "门店环境.mp4"
    voice = media / "老板音色.mp3"
    bgm = media / "品牌BGM.mp3"
    image = media / "套餐图片.png"
    run_ffmpeg(
        "-f", "lavfi", "-i", "color=c=0x243b53:s=320x568:r=25",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=16000",
        "-t", "1.4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video),
    )
    for frequency, path in ((660, voice), (880, bgm)):
        run_ffmpeg(
            "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=16000",
            "-t", "1.4", "-c:a", "libmp3lame", str(path),
        )
    Image.new("RGB", (480, 640), (238, 121, 80)).save(image, format="PNG")
    return {"video": video, "voice": voice, "bgm": bgm, "image": image}


def seed_assets(root: Path, media: dict[str, Path]) -> dict[str, object]:
    repository = AssetLibraryRepository(root / "data")

    def upload(path: Path, kind: str) -> dict[str, object]:
        payload = path.read_bytes()
        upload_session = repository.create_upload_session(path.name, len(payload), kind)
        repository.append_upload_chunk(upload_session["upload_id"], payload)
        result = repository.finalize_upload(upload_session["upload_id"])
        asset_id = str(result["asset_id"])
        asset = repository.get_asset(asset_id)
        if not asset:
            raise RuntimeError(f"unable to seed asset: {path}")
        return asset

    image_asset = upload(media["image"], "image")
    video_asset = upload(media["video"], "video")
    voice_asset = upload(media["voice"], "audio")
    bgm_asset = upload(media["bgm"], "audio")
    voice_profile = repository.create_voice_profile(
        {
            "voice_id": "uxc-production-voice",
            "name": "门店老板音色",
            "audio_asset_id": voice_asset["asset_id"],
            "language": "zh-CN",
            "style": "自然",
        }
    )
    person = repository.create_digital_human_profile(
        {"name": "门店老板数字人", "source_asset_id": image_asset["asset_id"]}
    )
    brand = repository.create_brand_kit(
        {
            "brand_name": "门店示例品牌",
            "default_bgm_asset_id": bgm_asset["asset_id"],
            "primary_color": "#6D5DF6",
            "secondary_color": "#F05A47",
            "store_address": "示例街 1 号",
            "phone": "000-0000",
        }
    )
    template = repository.create_template_revision(
        {
            "display_name": "门店竖屏模板",
            "renderer_version": "ip-broadcast-composer-v2-test",
            "cover_contract": {"base_template_id": "boss_clean", "canvas_width": 1080, "canvas_height": 1920},
            "subtitle_contract": {"font_size": 48, "margin_v": 180},
        }
    )
    return {
        "image_asset_id": image_asset["asset_id"],
        "video_asset_id": video_asset["asset_id"],
        "voice_profile_id": voice_profile["resource_id"],
        "bgm_asset_id": bgm_asset["asset_id"],
        "person_id": person["resource_id"],
        "brand_id": brand["resource_id"],
        "template_id": template["resource_id"],
        "scene_id": person["scenes"][0]["scene_id"],
        "image_name": image_asset["name"],
        "video_name": video_asset["name"],
        "image_path": str(media["image"]),
        "video_path": str(media["video"]),
        "voice_path": str(media["voice"]),
    }


def request_json(base_url: str, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


async def choose_picker_asset(page: Page, group, kind: str, name: str) -> None:
    await group.get_by_role("button", name=f"选择{kind}素材").click()
    await page.get_by_role("dialog", name=f"选择{kind}资产").wait_for(timeout=10000)
    await page.locator(".library-picker-card").filter(has_text=name).first.click()
    await page.get_by_role("button", name="确认使用").click()
    await page.get_by_role("dialog", name=f"选择{kind}资产").wait_for(state="hidden", timeout=10000)


async def run_scenario(output_dir: Path, *, headed: bool = False) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    video_dir = output_dir / "raw-video"
    video_dir.mkdir(parents=True, exist_ok=True)
    api_port = "8110"
    web_port = "1430"
    base_api = f"http://127.0.0.1:{api_port}"
    with tempfile.TemporaryDirectory(prefix="asset-center-uxc-production-root-") as root_name:
        isolated_root = Path(root_name)
        media = create_media(isolated_root)
        seeded = seed_assets(isolated_root, media)
        env = os.environ.copy()
        env.update(
            {
                "PIXELLE_VIDEO_ROOT": str(isolated_root),
                "PIXELLE_ASSET_CENTER_V2": "true",
                "PIXELLE_ASSET_CENTER_SMB_UX": "true",
            }
        )
        api = start_process([sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", api_port], ROOT, env, output_dir / "api.log")
        vite_env = env | {
            "VITE_API_BASE_URL": base_api,
            "VITE_ASSET_CENTER_V2": "true",
            "VITE_ASSET_CENTER_SMB_UX": "true",
        }
        vite = start_process(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", web_port], ROOT / "desktop", vite_env, output_dir / "vite.log")
        try:
            wait_for_url(f"{base_api}/health")
            wait_for_url(f"http://127.0.0.1:{web_port}/")
            session = request_json(base_api, "POST", "/api/ip-broadcast/sessions")
            session_id = str(session["session_id"])
            request_json(
                base_api,
                "PATCH",
                f"/api/ip-broadcast/sessions/{session_id}/config",
                {
                    "source_text": "双人套餐今日到店可用，欢迎到店体验。",
                    "final_script": "双人套餐今日到店可用。\n欢迎到店体验。",
                    "tts_ref_audio_id": seeded["voice_profile_id"],
                    "tts_ref_audio_path": seeded["voice_path"],
                    "audio_path": seeded["voice_path"],
                    "tts_inference_mode": "comfyui",
                    "tts_workflow": "runninghub/tts_index_custom.json",
                    "portrait_id": seeded["person_id"],
                    "portrait_path": seeded["image_path"],
                    "portrait_media_type": "image",
                    "digital_human_scene_id": seeded["scene_id"],
                    "digital_human_video_path": seeded["video_path"],
                    "brand_kit_id": seeded["brand_id"],
                    "brand_bgm_asset_id": "",
                    "bgm_asset_id": "",
                    "template_id": seeded["template_id"],
                    "story_segments": [
                        {"segment_id": "1", "index": 1, "text": "双人套餐今日到店可用。"},
                        {"segment_id": "2", "index": 2, "text": "欢迎到店体验。"},
                    ],
                    "visual_groups": [],
                    "overlay_enabled": False,
                    "subtitle_enabled": True,
                },
            )
            # final_script invalidation is intentionally protected by a second
            # write, matching the desktop confirmation action.
            request_json(
                base_api,
                "PATCH",
                f"/api/ip-broadcast/sessions/{session_id}/config",
                {"copywriting_confirmed": True},
            )

            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch(headless=not headed)
                context: BrowserContext = await browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    record_video_dir=str(video_dir),
                )
                page = await context.new_page()
                await page.goto(f"http://127.0.0.1:{web_port}/", wait_until="networkidle")
                await page.evaluate(
                    "([sessionId]) => { localStorage.setItem('pixelle_ipb_session_id', sessionId); localStorage.setItem('pixelle_desktop_theme_skin', 'fresh'); }",
                    [session_id],
                )
                await page.reload(wait_until="networkidle")
                await page.get_by_text("口播剪辑", exact=True).first.click()
                await page.locator(".step-workspace").wait_for(timeout=15000)
                await page.locator(".ant-steps-item").nth(1).click()
                await page.locator(".voice-step-layout").wait_for(timeout=15000)
                await page.locator(".voice-step-layout .voice-config-panel .choice-summary-card").first.click()
                await page.get_by_role("dialog", name="选择音色资产").wait_for(timeout=10000)
                await page.locator(".library-picker-card").filter(has_text="门店老板音色").first.click()
                audition = page.locator('audio[aria-label="门店老板音色试听"]')
                await audition.wait_for(timeout=10000)
                await page.get_by_role("button", name="确认使用").click()
                await page.get_by_role("dialog", name="选择音色资产").wait_for(state="hidden", timeout=10000)
                selected_voice_after_existing = request_json(base_api, "GET", f"/api/ip-broadcast/sessions/{session_id}")
                existing_voice_selected = selected_voice_after_existing.get("state", {}).get("tts_ref_audio_id") == seeded["voice_profile_id"]

                await page.locator(".voice-step-layout .voice-config-panel .choice-summary-card").first.click()
                await page.get_by_role("dialog", name="选择音色资产").wait_for(timeout=10000)
                await page.get_by_role("button", name="快捷上传").click()
                upload_dialog = page.get_by_role("dialog", name="添加音色参考音频")
                await upload_dialog.wait_for(timeout=10000)
                await upload_dialog.locator('input[type="file"]').set_input_files(str(media["voice"]))
                await upload_dialog.get_by_role("button", name="开始上传").click()
                duplicate_action = page.get_by_role("button", name="创建独立资产")
                try:
                    await duplicate_action.wait_for(timeout=15000)
                    await duplicate_action.click()
                except PlaywrightTimeoutError:
                    await upload_dialog.locator("footer").get_by_text(re.compile(r"^1/1 已入库")).wait_for(timeout=15000)
                await page.get_by_role("dialog", name="添加音色参考音频").wait_for(state="hidden", timeout=10000)
                await page.get_by_role("button", name="关闭选择器").click()
                await page.get_by_role("dialog", name="选择音色资产").wait_for(state="hidden", timeout=10000)
                await page.locator(".voice-step-layout .voice-config-panel .choice-summary-card").first.click()
                await page.get_by_role("dialog", name="选择音色资产").wait_for(timeout=10000)
                uploaded_card = page.locator(".library-picker-card").filter(has_text=media["voice"].name).first
                await uploaded_card.wait_for(timeout=10000)
                await uploaded_card.click()
                await page.locator(f'audio[aria-label="{media["voice"].name}试听"]').wait_for(timeout=10000)
                await page.get_by_role("button", name="确认使用").click()
                await page.get_by_role("dialog", name="选择音色资产").wait_for(state="hidden", timeout=10000)
                selected_voice_after_upload = request_json(base_api, "GET", f"/api/ip-broadcast/sessions/{session_id}")
                uploaded_voice_id = str(selected_voice_after_upload.get("state", {}).get("tts_ref_audio_id") or "")
                voice_upload_selected = bool(uploaded_voice_id) and uploaded_voice_id != str(seeded["voice_profile_id"])
                voice_screenshot = output_dir / "uxd-voice-picker-audition-upload.png"
                await page.screenshot(path=str(voice_screenshot), full_page=True)
                # Selecting a voice intentionally invalidates a prior audio
                # artifact in the real workflow.  This harness uses a seeded
                # local audio file instead of invoking an external TTS
                # provider, so restore that deterministic audio artifact
                # before exercising the downstream production boundary.
                request_json(
                    base_api,
                    "PATCH",
                    f"/api/ip-broadcast/sessions/{session_id}/config",
                    {
                        "audio_path": seeded["voice_path"],
                        "digital_human_video_path": seeded["video_path"],
                    },
                )

                await page.locator(".ant-steps-item").nth(2).click()
                await page.get_by_role("button", name="从统一资产库选择").wait_for(timeout=15000)
                await page.get_by_role("button", name="从统一资产库选择").click()
                await page.get_by_role("dialog", name="选择数字人资产").wait_for(timeout=10000)
                await page.locator(".library-picker-card").filter(has_text="门店老板数字人").first.click()
                scene_panel = page.locator(".library-picker-scene-panel")
                await scene_panel.wait_for(timeout=10000)
                scene_choice = scene_panel.locator(".library-picker-scene-grid button").first
                await scene_choice.click()
                await page.get_by_role("button", name="确认使用").click()
                await page.get_by_role("dialog", name="选择数字人资产").wait_for(state="hidden", timeout=10000)
                selected_scene_session = request_json(base_api, "GET", f"/api/ip-broadcast/sessions/{session_id}")
                digital_human_scene_selected = (
                    selected_scene_session.get("state", {}).get("portrait_id") == seeded["person_id"]
                    and selected_scene_session.get("state", {}).get("digital_human_scene_id") == seeded["scene_id"]
                )
                scene_screenshot = output_dir / "uxd-digital-human-scene-picker.png"
                await page.screenshot(path=str(scene_screenshot), full_page=True)
                # Selecting a scene also invalidates an old generated video;
                # restore the seeded local fixture before the final production
                # boundary, just as the voice fixture is restored above.
                request_json(
                    base_api,
                    "PATCH",
                    f"/api/ip-broadcast/sessions/{session_id}/config",
                    {"digital_human_video_path": seeded["video_path"]},
                )

                await page.locator(".ant-steps-item").nth(3).click()
                await page.get_by_role("button", name="打开画面规划").wait_for(timeout=15000)
                await page.get_by_role("button", name="打开画面规划").click()
                await page.locator(".storyboard-timeline-item input[type=checkbox]").nth(0).check()
                await page.get_by_role("button", name="勾选段落成组").click()
                await page.locator(".storyboard-timeline-item input[type=checkbox]").nth(1).check()
                await page.get_by_role("button", name="勾选段落成组").click()
                groups = page.locator(".group-card")
                await choose_picker_asset(page, groups.nth(0), "视频", str(seeded["video_name"]))
                await groups.nth(1).locator("select").select_option("uploaded_image")
                await choose_picker_asset(page, groups.nth(1), "图片", str(seeded["image_name"]))
                await page.get_by_role("button", name="保存规划").click()
                await page.locator(".postproduction-step-layout").wait_for(timeout=10000)
                picker_screenshot = output_dir / "uxc-production-picker-image-video.png"
                await page.screenshot(path=str(picker_screenshot), full_page=True)

                render_started = time.monotonic()
                await page.get_by_role("button", name="一键成片").click()
                final_session: dict[str, object] = {}
                final_task_status = ""
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    response = await page.request.get(f"{base_api}/api/ip-broadcast/sessions/{session_id}")
                    final_session = await response.json()
                    tasks_response = await page.request.get(f"{base_api}/api/tasks?limit=100")
                    tasks = await tasks_response.json()
                    matching_tasks = [
                        task for task in tasks
                        if task.get("session_id") == session_id and task.get("step_key") == "postproduction"
                    ]
                    final_task_status = str(matching_tasks[-1].get("status") if matching_tasks else "")
                    state = final_session.get("state", {})
                    if state.get("final_video_path") and state.get("cover_path") and final_task_status == "completed":
                        break
                    await asyncio.sleep(0.5)
                if not final_session.get("state", {}).get("final_video_path"):
                    raise RuntimeError("desktop render task did not produce final_video_path")
                render_elapsed_ms = round((time.monotonic() - render_started) * 1000)
                # The task auto-advances to Publish after completion; return to
                # the postproduction panel through the normal reload/recovery
                # path so React reads the completed session state.
                await page.reload(wait_until="networkidle")
                await page.locator("li.ant-menu-item").filter(has_text="口播剪辑").first.evaluate("(element) => element.click()")
                await page.locator(".step-workspace").wait_for(timeout=15000)
                await page.locator(".ant-steps-item").nth(3).click()
                await page.locator(".postproduction-step-layout").wait_for(timeout=15000)
                await page.get_by_text("最终视频已生成，请确认画面和字幕。", exact=True).wait_for(timeout=15000)
                render_screenshot = output_dir / "uxc-production-rendered-mp4.png"
                await page.screenshot(path=str(render_screenshot), full_page=True)
                await context.close()
                await browser.close()

            final_session = request_json(base_api, "GET", f"/api/ip-broadcast/sessions/{session_id}")
            usage = request_json(base_api, "GET", f"/api/v2/sessions/{session_id}/resource-usage")
            snapshots = request_json(base_api, "GET", f"/api/v2/sessions/{session_id}/resource-snapshots")
            voice_projection = request_json(base_api, "GET", "/api/v2/library/items?kind=voice&limit=50")
            audio_projection = request_json(base_api, "GET", "/api/v2/library/items?kind=audio&limit=50")
            final_path = Path(str(final_session.get("state", {}).get("final_video_path") or ""))
            if not final_path.is_file():
                raise RuntimeError(f"final video missing: {final_path}")
            artifact_request = urllib.request.Request(f"{base_api}/api/ip-broadcast/sessions/{session_id}/artifacts/final_video")
            with urllib.request.urlopen(artifact_request, timeout=60) as artifact_response:
                artifact_status = artifact_response.status
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", str(final_path)],
                check=True,
                capture_output=True,
                text=True,
            )
            dimensions = probe.stdout.strip().splitlines()[0] if probe.stdout.strip() else ""
            usage_items = usage.get("items", [])
            usage_keys = {(item.get("resource_kind"), item.get("resource_id")) for item in usage_items}
            voice_items = voice_projection.get("items", [])
            audio_items = audio_projection.get("items", [])
            voice_resource_ids = {str(item.get("resource_id")) for item in voice_items}
            audio_resource_ids = {str(item.get("resource_id")) for item in audio_items}
            voice_profile_in_voice_facet = str(seeded["voice_profile_id"]) in voice_resource_ids
            uploaded_voice_in_voice_facet = uploaded_voice_id in voice_resource_ids
            bgm_not_in_voice_facet = str(seeded["bgm_asset_id"]) not in voice_resource_ids
            bgm_in_audio_facet = str(seeded["bgm_asset_id"]) in audio_resource_ids
            rendered_voice_id = uploaded_voice_id or str(seeded["voice_profile_id"])
            expected_usage = {
                ("voice", rendered_voice_id),
                ("image", seeded["image_asset_id"]),
                ("video", seeded["video_asset_id"]),
                ("digital_human", seeded["person_id"]),
                ("digital_human_scene", seeded["scene_id"]),
                ("brand", seeded["brand_id"]),
                ("template", seeded["template_id"]),
            }
            reports = sorted(path.name for path in video_dir.glob("*"))
            report = {
                "schema_version": "asset-center-uxc-production-desktop-e2e-v1",
                "status": "pass" if dimensions == "1080,1920" and artifact_status == 200 and expected_usage.issubset(usage_keys) and snapshots.get("items") and voice_profile_in_voice_facet and uploaded_voice_in_voice_facet and bgm_not_in_voice_facet and bgm_in_audio_facet and existing_voice_selected and voice_upload_selected and digital_human_scene_selected else "fail",
                "environment": {
                    "surface": "real Vite + FastAPI desktop web surface",
                    "isolated_data_root": True,
                    "viewport": "1440x1000",
                    "target_user_study": False,
                    "release_device_signoff": False,
                },
                "picker": {
                    "image_selected_same_slot": True,
                    "video_selected_same_slot": True,
                    "screenshot": picker_screenshot.name,
                    "visual_groups": final_session.get("state", {}).get("visual_groups", []),
                },
                "voice_picker": {
                    "existing_voice_audition_control_visible": True,
                    "existing_voice_confirmed": existing_voice_selected,
                    "uploaded_voice_confirmed": voice_upload_selected,
                    "uploaded_voice_resource_id": uploaded_voice_id,
                    "screenshot": voice_screenshot.name,
                    "synthetic_audio_fixture_rebound_after_voice_selection": True,
                },
                "digital_human_picker": {
                    "scene_selected": digital_human_scene_selected,
                    "person_id": seeded["person_id"],
                    "scene_id": seeded["scene_id"],
                    "screenshot": scene_screenshot.name,
                    "synthetic_video_fixture_rebound_after_scene_selection": True,
                },
                "render": {
                    "clicked_one_click_render": True,
                    "task_status": final_task_status,
                    "elapsed_ms": render_elapsed_ms,
                    "final_video_path": str(final_path),
                    "ffprobe_dimensions": dimensions,
                    "artifact_http_status": artifact_status,
                    "screenshot": render_screenshot.name,
                },
                "usage": {
                    "expected_resource_keys": sorted([list(item) for item in expected_usage]),
                    "observed_resource_keys": sorted([list(item) for item in usage_keys]),
                    "expected_present": expected_usage.issubset(usage_keys),
                    "snapshot_count": len(snapshots.get("items", [])),
                },
                "facet_isolation": {
                    "voice_profile_in_voice_facet": voice_profile_in_voice_facet,
                    "uploaded_voice_in_voice_facet": uploaded_voice_in_voice_facet,
                    "bgm_asset_not_in_voice_facet": bgm_not_in_voice_facet,
                    "bgm_asset_in_audio_facet": bgm_in_audio_facet,
                    "voice_resource_ids": sorted(voice_resource_ids),
                    "audio_resource_ids": sorted(audio_resource_ids),
                },
                "recordings": reports,
                "notes": [
                    "The picker flow uses stable V2 IDs and only writes usage at the render boundary.",
                    "This is a technical desktop E2E evidence run; it does not satisfy the five-person UX-E study or release-device visual sign-off.",
                ],
            }
        finally:
            stop_process(vite)
            stop_process(api)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/migrations/asset-center-uxc-production-desktop-e2e-2026-07-18"))
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    report = asyncio.run(run_scenario(args.output_dir, headed=args.headed))
    print(f"UX-C production desktop E2E: {report['status']} ({report['render']['ffprobe_dimensions']})")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
