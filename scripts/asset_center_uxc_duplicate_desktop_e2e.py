#!/usr/bin/env python3
"""Run the real desktop duplicate-policy and finalize-idempotence gate."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.async_api import BrowserContext, Page, async_playwright

from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from scripts.asset_center_uxe_desktop_gate import ROOT, start_process, stop_process, wait_for_url


def request_json(base_url: str, method: str, path: str, payload: dict[str, object] | None = None) -> dict[str, object]:
    body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def seed_duplicate_asset(root: Path) -> tuple[Path, str]:
    fixture = root / "duplicate-fixture.png"
    Image.new("RGBA", (96, 96), (109, 93, 246, 180)).save(fixture, format="PNG")
    repository = AssetLibraryRepository(root / "data")
    payload = fixture.read_bytes()
    upload = repository.create_upload_session(fixture.name, len(payload), "image")
    repository.append_upload_chunk(upload["upload_id"], payload)
    asset = repository.finalize_upload(upload["upload_id"])
    return fixture, str(asset["asset_id"])


async def open_upload_queue(page: Page) -> object:
    await page.get_by_role("button", name="添加资产").click()
    dialog = page.get_by_role("dialog", name="批量添加资产")
    await dialog.wait_for(timeout=10000)
    return dialog


async def run_policy(page: Page, fixture: Path, policy_label: str) -> None:
    dialog = await open_upload_queue(page)
    await dialog.locator('input[type="file"]').set_input_files(str(fixture))
    await dialog.get_by_role("button", name="开始上传").click()
    await dialog.get_by_role("button", name=policy_label).wait_for(timeout=15000)
    await dialog.get_by_role("button", name=policy_label).click()
    await dialog.locator("footer").get_by_text("1/1 已入库").wait_for(timeout=15000)
    await dialog.get_by_role("button", name="关闭", exact=True).click()
    await dialog.wait_for(state="hidden", timeout=10000)


def latest_deferred_session(repository: AssetLibraryRepository) -> dict[str, object]:
    with repository._connect() as connection:  # noqa: SLF001 - gate evidence inspection
        row = connection.execute(
            "SELECT * FROM upload_sessions WHERE decision_mode = 'deferred' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
    if not row:
        raise AssertionError("no deferred upload session was recorded")
    return dict(row)


async def run_scenario(output_dir: Path) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    api_port = "8122"
    web_port = "1434"
    api_url = f"http://127.0.0.1:{api_port}"
    web_url = f"http://127.0.0.1:{web_port}/"
    with tempfile.TemporaryDirectory(prefix="asset-center-uxc-duplicate-root-") as root_name:
        isolated_root = Path(root_name)
        fixture, original_asset_id = seed_duplicate_asset(isolated_root)
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
                await page.goto(web_url, wait_until="networkidle")
                await page.locator("li.ant-menu-item").filter(has_text="企业资产库").first.evaluate("(element) => element.click()")
                await page.locator(".asset-center-v2").wait_for(timeout=15000)
                await page.locator(".asset-center-v2-card").first.wait_for(timeout=15000)

                await run_policy(page, fixture, "使用已有资产")
                repository = AssetLibraryRepository(isolated_root / "data")
                after_reuse = {
                    "asset_count": repository.list_library_page(kind="image", page_size=100)["total"],
                    "revision_count": len(repository.list_revisions(original_asset_id)),
                    "latest_status": latest_deferred_session(repository)["status"],
                }

                await run_policy(page, fixture, "作为新版本")
                after_revision = {
                    "asset_count": repository.list_library_page(kind="image", page_size=100)["total"],
                    "revision_count": len(repository.list_revisions(original_asset_id)),
                    "latest_status": latest_deferred_session(repository)["status"],
                }

                await run_policy(page, fixture, "创建独立资产")
                latest = latest_deferred_session(repository)
                after_separate = {
                    "asset_count": repository.list_library_page(kind="image", page_size=100)["total"],
                    "revision_count": len(repository.list_revisions(original_asset_id)),
                    "latest_status": latest["status"],
                }
                await context.close()
                await browser.close()

            policy_sessions = []
            with repository._connect() as connection:  # noqa: SLF001 - gate evidence inspection
                rows = connection.execute(
                    "SELECT upload_id, duplicate_policy, duplicate_asset_id, asset_id, status "
                    "FROM upload_sessions WHERE decision_mode = 'deferred' ORDER BY created_at"
                ).fetchall()
            for row in rows:
                policy_sessions.append(dict(row))
            if len(policy_sessions) != 3:
                raise AssertionError(f"expected 3 policy sessions, got {len(policy_sessions)}")

            idempotent_results = []
            for row in policy_sessions:
                policy = str(row["duplicate_policy"])
                payload: dict[str, object] = {"duplicate_policy": policy}
                if policy == "attach_revision":
                    payload["target_asset_id"] = original_asset_id
                repeated = request_json(api_url, "POST", f"/api/v2/uploads/{row['upload_id']}/finalize", payload)
                repeated_upload = repeated.get("upload", {})
                idempotent_results.append(
                    {
                        "policy": policy,
                        "upload_id": row["upload_id"],
                        "same_asset_id": str(repeated_upload.get("asset_id") or repeated_upload.get("duplicate_asset_id") or "")
                        == str(row["asset_id"] or row["duplicate_asset_id"] or ""),
                        "status": repeated_upload.get("status"),
                    }
                )

            status = (
                after_reuse == {"asset_count": 1, "revision_count": 1, "latest_status": "ready"}
                and after_revision == {"asset_count": 1, "revision_count": 2, "latest_status": "finalized"}
                and after_separate["asset_count"] == 2
                and after_separate["revision_count"] == 2
                and all(result["same_asset_id"] for result in idempotent_results)
            )
            report = {
                "schema_version": "asset-center-uxc-duplicate-desktop-e2e-v1",
                "status": "pass" if status else "fail",
                "environment": {
                    "surface": "real Vite + FastAPI desktop web surface",
                    "isolated_data_root": True,
                    "viewport": "1440x900",
                    "target_user_study": False,
                    "release_device_signoff": False,
                },
                "policies": {
                    "reuse_existing": after_reuse,
                    "attach_revision": after_revision,
                    "create_separate": after_separate,
                },
                "idempotence": idempotent_results,
                "notes": [
                    "Each policy was selected through the real desktop AssetUploadQueue duplicate decision UI.",
                    "Repeated finalize calls were sent through the real API route and did not create additional assets or revisions.",
                    "This is technical UX-C evidence and does not replace target-user or release-device sign-off.",
                ],
            }
        finally:
            stop_process(web)
            stop_process(api)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/migrations/asset-center-uxc-duplicate-desktop-e2e-2026-07-18"))
    args = parser.parse_args()
    report = asyncio.run(run_scenario(args.output_dir))
    print(f"UX-C duplicate desktop E2E: {report['status']}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
