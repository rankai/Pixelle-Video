"""Browser runtime abstraction for desktop publishing automation."""

from pathlib import Path
from typing import Any, Protocol

DEFAULT_BROWSER_RUNTIME = "playwright"
SUPPORTED_BROWSER_RUNTIMES = {"playwright", "cloakbrowser"}
DOUYIN_CREATOR_UPLOAD_URL = "https://creator.douyin.com/creator-micro/content/upload"


class BrowserRuntime(Protocol):
    """Protocol implemented by browser automation runtimes."""

    async def launch_persistent_context(self, platform: str) -> Any:
        """Open or reuse a persistent browser context for a platform."""

    async def close(self) -> None:
        """Close browser resources owned by this runtime."""


class PlaywrightBrowserRuntime:
    """Default visible browser runtime for desktop publishing."""

    def __init__(self, user_data_root: str | Path = "data/publish_browser"):
        self.user_data_root = Path(user_data_root)
        self._playwright: Any = None
        self._context: Any = None

    async def launch_persistent_context(self, platform: str) -> "PlaywrightPublishContext":
        from playwright.async_api import async_playwright

        self.user_data_root.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(self.user_data_root / platform),
            headless=False,
            viewport={"width": 1440, "height": 1000},
        )
        return PlaywrightPublishContext(self._context, platform)

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


class PlaywrightPublishContext:
    """Conservative page operations used by platform adapters."""

    def __init__(self, context: Any, platform: str):
        self.context = context
        self.platform = platform
        self.page: Any = None
        self._description_text = ""

    async def open_creator_page(self) -> None:
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.goto(DOUYIN_CREATOR_UPLOAD_URL, wait_until="domcontentloaded")

    async def is_logged_in(self) -> bool:
        if not self.page:
            return False
        await self.page.wait_for_timeout(1500)
        url = self.page.url
        if "login" in url:
            return False
        content = await self.page.content()
        login_words = ["扫码登录", "登录后", "请登录", "验证码"]
        if any(word in content for word in login_words):
            return False
        return True

    async def upload_video(self, video_path: str) -> None:
        file_input = self.page.locator("input[type='file']").first
        await file_input.set_input_files(video_path)

    async def fill_title(self, title: str) -> None:
        await _fill_first_available(
            self.page,
            ["input[placeholder*='标题']", "textarea[placeholder*='标题']"],
            title,
        )

    async def fill_description(self, description: str) -> None:
        if not description:
            return
        self._description_text = description
        await _fill_first_available(
            self.page,
            ["textarea[placeholder*='简介']", "textarea[placeholder*='描述']", "textarea"],
            description,
        )

    async def fill_hashtags(self, hashtags: list[str]) -> None:
        if not hashtags:
            return
        text = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags if tag)
        if text:
            combined = "\n".join(item for item in [self._description_text, text] if item)
            await self.fill_description(combined)

    async def upload_cover(self, cover_path: str) -> None:
        # Cover upload controls differ across Douyin UI versions. Keep this optional.
        if not cover_path:
            return

    async def wait_until_draft_ready(self) -> None:
        await self.page.wait_for_timeout(1000)


async def _fill_first_available(page: Any, selectors: list[str], value: str) -> None:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count():
                await locator.fill(value)
                return
        except Exception:
            continue
