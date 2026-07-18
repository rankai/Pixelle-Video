#!/usr/bin/env python3
"""Run a real desktop UX-B reachability gate over 1,000 asset rows."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

from playwright.async_api import BrowserContext, async_playwright

from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from scripts.asset_center_uxe_desktop_gate import ROOT, start_process, stop_process, wait_for_url
from scripts.assets_ux4_performance import benchmark


def seed_browse_kinds(root: Path) -> None:
    repository = AssetLibraryRepository(root / "data")
    timestamp = "2026-07-18T00:00:00+00:00"
    with repository._lock, repository._connect() as connection:  # noqa: SLF001 - isolated gate fixture
        for asset_id, kind, name in (
            ("uxb-video", "video", "UX-B 视频素材"),
            ("uxb-audio", "audio", "UX-B 音频素材"),
        ):
            connection.execute(
                "INSERT INTO media_assets(asset_id, media_kind, name, description, source, status, created_at, updated_at) VALUES (?, ?, ?, '', 'imported', 'ready', ?, ?)",
                (asset_id, kind, name, timestamp, timestamp),
            )
    repository.create_voice_profile({"voice_id": "uxb-voice", "name": "UX-B 音色", "audio_asset_id": "uxb-audio", "language": "中文", "style": "自然"})
    repository.create_digital_human_profile({"profile_id": "uxb-digital-human", "name": "UX-B 数字人", "scene_name": "门店场景"})
    repository.create_brand_kit({"brand_id": "uxb-brand", "brand_name": "UX-B 品牌", "primary_color": "#6D5DF6", "secondary_color": "#F05A47"})
    repository.create_template_revision({"template_id": "uxb-template", "display_name": "UX-B 模板", "short_description": "固定 fixture"})


async def run_scenario(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="asset-center-uxb-root-") as root_name:
        isolated_root = Path(root_name)
        benchmark(isolated_root / "data", 1000)
        seed_browse_kinds(isolated_root)
        api_port = "8121"
        web_port = "1433"
        api_url = f"http://127.0.0.1:{api_port}"
        web_url = f"http://127.0.0.1:{web_port}/"
        env = os.environ.copy() | {
            "PIXELLE_VIDEO_ROOT": str(isolated_root),
            "PIXELLE_ASSET_CENTER_V2": "true",
            "PIXELLE_ASSET_CENTER_SMB_UX": "true",
            "VITE_API_BASE_URL": api_url,
            "VITE_ASSET_CENTER_V2": "true",
            "VITE_ASSET_CENTER_SMB_UX": "true",
        }
        api = start_process(
            [sys.executable, "api/app.py", "--host", "127.0.0.1", "--port", api_port],
            ROOT,
            env,
            output_dir / "api.log",
        )
        web = start_process(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", web_port],
            ROOT / "desktop",
            env,
            output_dir / "vite.log",
        )
        try:
            wait_for_url(f"{api_url}/health")
            wait_for_url(web_url)
            async with async_playwright() as playwright:
                browser = await playwright.chromium.launch()
                context: BrowserContext = await browser.new_context(viewport={"width": 1440, "height": 900})
                page = await context.new_page()
                started = time.monotonic()
                await page.goto(web_url, wait_until="networkidle")
                await page.locator("li.ant-menu-item").filter(has_text="企业资产库").first.evaluate("(element) => element.click()")
                await page.locator(".asset-center-v2").wait_for(timeout=15000)
                await page.locator(".asset-center-v2-card").first.wait_for(timeout=15000)
                first_interactive_ms = round((time.monotonic() - started) * 1000)

                facet_checks: dict[str, dict[str, object]] = {}
                for facet_key, facet_label in (
                    ("video", "视频"),
                    ("image", "图片"),
                    ("digital_human", "数字人"),
                    ("voice", "音色"),
                    ("audio", "音频"),
                    ("template", "模板"),
                    ("brand", "品牌"),
                ):
                    facet = page.locator(".asset-center-v2-filters button").filter(has_text=facet_label).first
                    await facet.click()
                    await page.wait_for_function(
                        """(label) => {
                            const active = document.querySelector('.asset-center-v2-filters button[aria-pressed="true"]');
                            return active?.textContent?.includes(label) === true;
                        }""",
                        arg=facet_label,
                        timeout=10000,
                    )
                    if facet_key == "digital_human":
                        await page.wait_for_function(
                            """() => document.querySelector('.digital-human-card-grid strong')?.textContent?.includes('UX-B 数字人') === true
                                && document.querySelector('.digital-human-preview-panel') !== null""",
                            timeout=10000,
                        )
                        facet_checks[facet_key] = {
                            "filter_text": " ".join((await facet.inner_text()).split()),
                            "browse_count": await page.locator(".digital-human-list button").count(),
                            "preview_opened": True,
                        }
                    else:
                        await page.wait_for_function(
                            """(label) => {
                                const active = document.querySelector('.asset-center-v2-filters button[aria-pressed="true"]');
                                const grid = document.querySelector('.asset-center-v2-grid');
                                const cards = Array.from(document.querySelectorAll('.asset-center-v2-card'));
                                return active?.textContent?.includes(label) === true
                                    && grid?.getAttribute('aria-busy') !== 'true'
                                    && cards.length > 0
                                    && cards.every((card) => (card.getAttribute('aria-label') || '').includes(`，${label}，`));
                            }""",
                            arg=facet_label,
                            timeout=10000,
                        )
                        await page.locator(".asset-center-v2-card").first.click()
                        await page.locator(".asset-center-v2-detail").wait_for(timeout=10000)
                        facet_checks[facet_key] = {
                            "filter_text": " ".join((await facet.inner_text()).split()),
                            "browse_count": await page.locator(".asset-center-v2-card").count(),
                            "preview_opened": await page.locator(".asset-center-v2-detail-preview").count() == 1,
                        }
                        await page.get_by_role("button", name="关闭详情").click()

                image_filter = page.locator(".asset-center-v2-filters button").filter(has_text="图片").first
                image_filter_text = " ".join((await image_filter.inner_text()).split())
                await image_filter.click()
                await page.wait_for_function(
                    """() => {
                        const activeFilter = document.querySelector('.asset-center-v2-filters button[aria-pressed="true"]');
                        const grid = document.querySelector('.asset-center-v2-grid');
                        const cards = Array.from(document.querySelectorAll('.asset-center-v2-card'));
                        return Boolean(
                            activeFilter?.textContent?.includes('图片')
                            && grid?.getAttribute('aria-busy') !== 'true'
                            && cards.length > 0
                            && cards.every((card) => (card.getAttribute('aria-label') || '').includes('，图片，')),
                        );
                    }""",
                    timeout=15000,
                )
                total_cards = 0
                load_more_clicks = 0
                while True:
                    total_cards = await page.locator(".asset-center-v2-card").count()
                    load_more = page.locator(".asset-center-v2-load-more button")
                    if not await load_more.count():
                        break
                    if await load_more.is_disabled():
                        await page.wait_for_function(
                            "() => { const button = document.querySelector('.asset-center-v2-load-more button'); return !button || !button.disabled; }",
                            timeout=10000,
                        )
                        load_more = page.locator(".asset-center-v2-load-more button")
                        if not await load_more.count():
                            break
                    load_more_clicks += 1
                    await load_more.click()
                    await page.wait_for_function(
                        """(previous) => {
                            const grid = document.querySelector('.asset-center-v2-grid');
                            return grid?.getAttribute('aria-busy') !== 'true'
                                && document.querySelectorAll('.asset-center-v2-card').length > previous;
                        }""",
                        arg=total_cards,
                        timeout=15000,
                    )
                total_cards = await page.locator(".asset-center-v2-card").count()
                card_labels = await page.locator(".asset-center-v2-card").evaluate_all(
                    "(cards) => cards.map((card) => card.getAttribute('aria-label') || '')"
                )
                unique_card_labels = len(set(card_labels))

                search = page.locator("input[aria-label='搜索企业资产']")
                await search.fill("性能素材 00999")
                await page.wait_for_timeout(350)
                await page.locator(".asset-center-v2-card").first.wait_for(timeout=10000)
                search_cards = await page.locator(".asset-center-v2-card").count()
                search_label = await page.locator(".asset-center-v2-card").first.get_attribute("aria-label")
                await context.close()
                await browser.close()

            report = {
                "schema_version": "asset-center-uxb-desktop-gate-v1",
                "status": "technical_pass" if all(
                    check["browse_count"] > 0 and check["preview_opened"]
                    for check in facet_checks.values()
                ) and "图片 1000" in image_filter_text and total_cards == 1000 and unique_card_labels == 1000 and search_cards == 1 and "性能素材 00999" in str(search_label) else "fail",
                "environment": {
                    "surface": "real Vite + FastAPI desktop web surface",
                    "isolated_data_root": True,
                    "viewport": "1440x900",
                    "fixed_asset_count": 1000,
                    "target_user_study": False,
                    "release_device_signoff": False,
                },
                "reachability": {
                    "facet_checks": facet_checks,
                    "image_filter_text": image_filter_text,
                    "first_interactive_ms": first_interactive_ms,
                    "loaded_card_count": total_cards,
                    "unique_card_label_count": unique_card_labels,
                    "load_more_clicks": load_more_clicks,
                    "search_result_count": search_cards,
                    "search_result_label": search_label,
                },
                "notes": [
                    "The 1,000 rows are a fixed isolated fixture and are loaded through the real cursor-backed desktop surface.",
                    "This is a technical UX-B gate; it does not replace target-user or release-device sign-off.",
                ],
            }
        finally:
            stop_process(web)
            stop_process(api)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/migrations/asset-center-uxb-desktop-gate-2026-07-18"))
    args = parser.parse_args()
    report = asyncio.run(run_scenario(args.output_dir))
    print(f"UX-B desktop gate: {report['status']} ({report['reachability']['loaded_card_count']} cards)")
    return 0 if report["status"] == "technical_pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
