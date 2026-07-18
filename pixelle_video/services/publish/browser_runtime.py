"""Browser runtime abstraction for desktop publishing automation."""

from pathlib import Path
from typing import Any, Protocol

from pixelle_video.utils.chromium import playwright_chromium_launch_options

DEFAULT_BROWSER_RUNTIME = "playwright"
SUPPORTED_BROWSER_RUNTIMES = {"playwright", "cloakbrowser"}
CREATOR_UPLOAD_URLS = {
    "douyin": "https://creator.douyin.com/creator-micro/content/upload",
    "xiaohongshu": "https://creator.xiaohongshu.com/publish/publish?source=official",
    "shipinhao": "https://channels.weixin.qq.com/platform/post/create",
    "kuaishou": "https://cp.kuaishou.com/article/publish/video?tabType=3",
}

PLATFORM_FIELD_SELECTORS = {
    "douyin": {
        "title": ["input[placeholder*='标题']", "textarea[placeholder*='标题']"],
        "description": [
            "textarea[placeholder*='简介']",
            "textarea[placeholder*='描述']",
            "textarea",
        ],
    },
    "xiaohongshu": {
        "title": ["input[placeholder*='标题']", "textarea[placeholder*='标题']"],
        "description": [
            "div[contenteditable='true'][data-placeholder*='正文']",
            "div[contenteditable='true'][data-placeholder*='描述']",
            "textarea[placeholder*='正文']",
            "textarea",
        ],
    },
    "shipinhao": {
        "title": ["input[placeholder*='标题']", "textarea[placeholder*='标题']"],
        "description": [
            "div[contenteditable='true']",
            "textarea[placeholder*='描述']",
            "textarea[placeholder*='文案']",
            "textarea",
        ],
    },
    "kuaishou": {
        "title": ["input[placeholder*='标题']", "textarea[placeholder*='标题']"],
        "description": [
            "div[contenteditable='true']",
            "textarea[placeholder*='作品描述']",
            "textarea[placeholder*='描述']",
            "textarea",
        ],
    },
}


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
            **playwright_chromium_launch_options(),
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
        await self.page.goto(CREATOR_UPLOAD_URLS[self.platform], wait_until="domcontentloaded")

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

    async def upload_video(self, video_path: str) -> bool:
        for selector in ["input[type='file'][accept*='video']", "input[type='file']"]:
            file_input = self.page.locator(selector).first
            if await file_input.count():
                await file_input.set_input_files(video_path)
                return True
        return False

    async def fill_title(self, title: str) -> bool:
        return await _fill_first_available(
            self.page,
            PLATFORM_FIELD_SELECTORS[self.platform]["title"],
            title,
        )

    async def fill_description(self, description: str) -> bool:
        if not description:
            return False
        self._description_text = description
        return await _fill_first_available(
            self.page,
            PLATFORM_FIELD_SELECTORS[self.platform]["description"],
            description,
        )

    async def fill_hashtags(self, hashtags: list[str]) -> bool:
        if not hashtags:
            return False
        text = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags if tag)
        if text:
            combined = "\n".join(item for item in [self._description_text, text] if item)
            return await self.fill_description(combined)
        return False

    async def upload_cover(self, cover_path: str) -> bool:
        if not cover_path:
            return False
        # Creator pages usually reveal this control after the video begins processing.
        # We only target image-only file inputs so the video upload control cannot be reused.
        for selector in [
            "input[type='file'][accept*='image']",
            "input[type='file'][accept*='.jpg']",
            "input[type='file'][accept*='.png']",
        ]:
            locator = self.page.locator(selector).last
            if await locator.count():
                await locator.set_input_files(cover_path)
                return True
        return False

    async def wait_until_draft_ready(self) -> None:
        await self.page.wait_for_timeout(1000)

    async def current_url(self) -> str:
        return str(self.page.url) if self.page else ""


async def _fill_first_available(page: Any, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if await locator.count():
                if "contenteditable" in selector:
                    await locator.click()
                    await locator.press("ControlOrMeta+A")
                    await locator.fill(value)
                else:
                    await locator.fill(value)
                return True
        except Exception:
            continue
    return False
