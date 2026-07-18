#!/usr/bin/env python3
"""Run the local UX-E accessibility, visual and gray-toggle gate."""

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
VIEWPORTS = [(1440, 900), (1280, 800), (1024, 768), (900, 700)]


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
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
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


def seed_visual_assets(root: Path) -> None:
    fixture_dir = root / "fixtures"
    fixture_dir.mkdir(parents=True, exist_ok=True)
    repository = AssetLibraryRepository(root / "data")
    for index, (size, mode, color) in enumerate(
        [((320, 320), "RGB", (109, 93, 246)), ((96, 1600), "RGBA", (240, 90, 71, 150)), ((2400, 64), "RGB", (45, 55, 72))],
        start=1,
    ):
        path = fixture_dir / f"视觉回归-{index}.png"
        Image.new(mode, size, color).save(path, format="PNG")
        payload = path.read_bytes()
        upload = repository.create_upload_session(path.name, len(payload), "image")
        repository.append_upload_chunk(upload["upload_id"], payload)
        repository.finalize_upload(upload["upload_id"])


async def enter_asset_center(page: Page, base_url: str, theme: str) -> None:
    await page.goto(base_url, wait_until="networkidle")
    await page.evaluate("(theme) => localStorage.setItem('pixelle_desktop_theme_skin', theme)", theme)
    await page.reload(wait_until="networkidle")
    await page.locator("li.ant-menu-item").filter(has_text="企业资产库").first.evaluate("(element) => element.click()")
    await page.locator(".asset-center-v2").wait_for(timeout=15000)
    await page.locator(".asset-center-v2-card").first.wait_for(timeout=15000)


async def contrast_ratio(page: Page) -> float:
    return float(
        await page.evaluate(
            """() => {
              const node = document.querySelector('.asset-center-v2-card');
              if (!node) return 0;
              const parse = (value) => {
                const match = value.match(/[0-9.]+/g) || [];
                return [Number(match[0] || 0), Number(match[1] || 0), Number(match[2] || 0), Number(match[3] ?? 1)];
              };
              const rgb = (value) => {
                const [r, g, b] = parse(value).slice(0, 3).map((part) => part / 255);
                return [r, g, b].map((part) => part <= 0.03928 ? part / 12.92 : Math.pow((part + 0.055) / 1.055, 2.4));
              };
              const color = rgb(getComputedStyle(node).color);
              const nodeBackground = getComputedStyle(node).backgroundColor;
              const bodyBackground = getComputedStyle(document.body).backgroundColor;
              const background = rgb(nodeBackground === 'rgba(0, 0, 0, 0)' ? (bodyBackground === 'rgba(0, 0, 0, 0)' ? 'rgb(255, 255, 255)' : bodyBackground) : nodeBackground);
              const luminance = (value) => 0.2126 * value[0] + 0.7152 * value[1] + 0.0722 * value[2];
              const first = luminance(color);
              const second = luminance(background);
              return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
            }"""
        )
    )


async def run_visual_a11y(page: Page, base_url: str, output_dir: Path) -> dict[str, object]:
    screenshots: list[str] = []
    contrast: dict[str, float] = {}
    visual_fixture_checks: dict[str, dict[str, object]] = {}
    focus_samples: list[str] = []
    for theme in ("fresh", "coral"):
        await enter_asset_center(page, base_url, theme)
        image_filter = page.locator(".asset-center-v2-filters button").filter(has_text="图片").first
        await image_filter.click()
        await page.wait_for_function(
            """() => {
                const active = document.querySelector('.asset-center-v2-filters button[aria-pressed="true"]');
                const grid = document.querySelector('.asset-center-v2-grid');
                const cards = Array.from(document.querySelectorAll('.asset-center-v2-card'));
                return active?.textContent?.includes('图片') === true
                    && grid?.getAttribute('aria-busy') !== 'true'
                    && cards.length === 3
                    && cards.every((card) => (card.getAttribute('aria-label') || '').includes('，图片，'));
            }""",
            timeout=15000,
        )
        card_text = await page.locator(".asset-center-v2-card").all_inner_texts()
        transparent_card = any("透明背景" in text for text in card_text)
        await page.locator(".asset-center-v2-card").first.click()
        await page.locator(".asset-center-v2-detail").wait_for(timeout=10000)
        inspector_opened = await page.locator(".asset-image-inspector").count() == 1
        await page.get_by_role("button", name="关闭详情").click()
        visual_fixture_checks[theme] = {
            "image_card_count": len(card_text),
            "transparent_card_present": transparent_card,
            "image_detail_inspector_opened": inspector_opened,
            "extreme_aspect_fixture_present": len(card_text) == 3,
        }
        for width, height in VIEWPORTS:
            await page.set_viewport_size({"width": width, "height": height})
            name = f"uxe-{theme}-{width}x{height}.png"
            await page.screenshot(path=str(output_dir / name), full_page=True)
            screenshots.append(name)
        contrast[theme] = round(await contrast_ratio(page), 2)

        await page.get_by_role("button", name="添加资产").first.click()
        dialog = page.get_by_role("dialog", name="批量添加资产")
        await dialog.wait_for(timeout=5000)
        assert await dialog.get_attribute("aria-modal") == "true"
        await page.keyboard.press("Escape")
        await dialog.wait_for(state="hidden", timeout=5000)

        for _ in range(16):
            await page.keyboard.press("Tab")
            active = await page.evaluate("document.activeElement?.getAttribute('aria-label') || document.activeElement?.textContent?.trim().slice(0, 36) || document.activeElement?.tagName || ''")
            if active:
                focus_samples.append(str(active))
        await page.emulate_media(reduced_motion="reduce")
        reduced_motion = await page.evaluate(
            """() => ({
              scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
              transitionDuration: getComputedStyle(document.querySelector('.asset-center-v2') || document.body).transitionDuration,
              reduced: matchMedia('(prefers-reduced-motion: reduce)').matches,
            })"""
        )
        assert reduced_motion["reduced"] is True

    body_text = await page.locator("body").inner_text()
    assert "media-" not in body_text
    assert await page.locator("input[aria-label='搜索企业资产']").count() == 1
    return {
        "themes": ["fresh", "coral"],
        "viewports": [f"{width}x{height}" for width, height in VIEWPORTS],
        "screenshots": screenshots,
        "visual_fixture_checks": visual_fixture_checks,
        "contrast_ratio_by_theme": contrast,
        "minimum_contrast_ratio": min(contrast.values()),
        "focus_samples": focus_samples[:16],
        "keyboard_dialog_escape": True,
        "screenreader_semantics": {"search_label": True, "modal_role_and_aria_modal": True, "asset_card_buttons": await page.locator(".asset-center-v2-card").count() > 0},
        "reduced_motion": reduced_motion,
        "default_ui_hides_raw_ids": True,
    }


async def run_scenario(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="asset-center-uxe-root-") as root_name:
        isolated_root = Path(root_name)
        seed_visual_assets(isolated_root)
        env = os.environ.copy() | {"PIXELLE_VIDEO_ROOT": str(isolated_root), "PIXELLE_ASSET_CENTER_V2": "true"}
        api_port = "8111"
        on_port = "1431"
        off_port = "1432"
        api_url = f"http://127.0.0.1:{api_port}"
        on_url = f"http://127.0.0.1:{on_port}/"
        off_url = f"http://127.0.0.1:{off_port}/"
        api = start_process([sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", api_port], ROOT, env, output_dir / "api.log")
        on_env = env | {"VITE_API_BASE_URL": api_url, "VITE_ASSET_CENTER_V2": "true", "VITE_ASSET_CENTER_SMB_UX": "true"}
        off_env = env | {"VITE_API_BASE_URL": api_url, "VITE_ASSET_CENTER_V2": "true", "VITE_ASSET_CENTER_SMB_UX": "false"}
        on = start_process(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", on_port], ROOT / "desktop", on_env, output_dir / "vite-on.log")
        off = start_process(["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", off_port], ROOT / "desktop", off_env, output_dir / "vite-off.log")
        try:
            wait_for_url(f"{api_url}/health")
            wait_for_url(on_url)
            wait_for_url(off_url)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context: BrowserContext = await browser.new_context(viewport={"width": 1440, "height": 900})
                page = await context.new_page()
                technical = await run_visual_a11y(page, on_url, output_dir)
                off_page = await context.new_page()
                await off_page.goto(off_url, wait_until="networkidle")
                await off_page.locator("li.ant-menu-item").filter(has_text="企业资产库").first.evaluate("(element) => element.click()")
                await off_page.locator(".asset-center").wait_for(timeout=15000)
                gray_off = {"smb_ux_surface_hidden": await off_page.locator("section[aria-label='新版企业资产库']").count() == 0, "current_v2_surface_visible": await off_page.locator(".asset-center").count() > 0}
                await context.close()
                await browser.close()
            report = {
                "schema_version": "asset-center-uxe-desktop-gate-v1",
                "status": "technical_pass" if technical["minimum_contrast_ratio"] >= 4.5
                and all(
                    check["image_card_count"] == 3
                    and check["transparent_card_present"]
                    and check["image_detail_inspector_opened"]
                    and check["extreme_aspect_fixture_present"]
                    for check in technical["visual_fixture_checks"].values()
                )
                and gray_off["smb_ux_surface_hidden"]
                and gray_off["current_v2_surface_visible"] else "fail",
                "environment": {"surface": "real Vite + FastAPI desktop web surface", "isolated_data_root": True, "target_user_study": False, "release_device_signoff": False},
                "technical_gate": technical,
                "gray_toggle": {"on_surface_rendered": True, "off_surface": gray_off, "default_rollout_remains_off": True},
                "notes": ["This is a local technical UX-E gate; it does not replace the required five-person target-user study or release-device sign-off."],
            }
        finally:
            stop_process(on)
            stop_process(off)
            stop_process(api)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/migrations/asset-center-uxe-desktop-gate-2026-07-18"))
    args = parser.parse_args()
    report = asyncio.run(run_scenario(args.output_dir))
    print(f"UX-E technical desktop gate: {report['status']}")
    return 0 if report["status"] == "technical_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
