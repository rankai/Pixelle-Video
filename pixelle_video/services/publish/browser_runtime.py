"""Browser runtime abstraction for desktop publishing automation."""

import hashlib
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from pixelle_video.utils.chromium import playwright_chromium_launch_options
from pixelle_video.utils.os_util import get_data_path

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
            "div[contenteditable='true'][data-testid='description-editor']",
            "div[contenteditable='true'][data-placeholder*='简介']",
            "div[contenteditable='true']",
            "textarea[placeholder*='简介']",
            "textarea[placeholder*='描述']",
            "textarea",
        ],
        "hashtags": [
            "[data-testid='hashtag-editor']",
            "input[placeholder*='话题']",
            "textarea[placeholder*='话题']",
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


def _canonical_editor_url(platform: str, value: str) -> str:
    """Collapse known Douyin entry/editor routes to one draft identity."""

    parsed = urlsplit(str(value).split("?", 1)[0])
    path = parsed.path.rstrip("/") or "/"
    if platform == "douyin" and path in {
        "/creator-micro/content/upload",
        "/creator-micro/content/post/video",
    }:
        path = "/creator-micro/content/editor"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


class BrowserRuntime(Protocol):
    """Protocol implemented by browser automation runtimes."""

    async def launch_persistent_context(
        self,
        platform: str,
        *,
        profile_path: str | Path | None = None,
        account_id: str | None = None,
    ) -> Any:
        """Open or reuse a persistent browser context for a platform."""

    async def close(self) -> None:
        """Close browser resources owned by this runtime."""


class PlaywrightBrowserRuntime:
    """Default visible browser runtime for desktop publishing."""

    def __init__(self, user_data_root: str | Path | None = None):
        self.user_data_root = Path(user_data_root or get_data_path("publish_browser", "accounts"))
        self._playwright: Any = None
        self._context: Any = None

    async def launch_persistent_context(
        self,
        platform: str,
        *,
        profile_path: str | Path | None = None,
        account_id: str | None = None,
    ) -> "PlaywrightPublishContext":
        from playwright.async_api import async_playwright

        self.user_data_root.mkdir(parents=True, exist_ok=True)
        self._playwright = await async_playwright().start()
        target_path = Path(profile_path) if profile_path else self.user_data_root / platform
        target_path.mkdir(parents=True, exist_ok=True)
        self._context = await self._playwright.chromium.launch_persistent_context(
            str(target_path),
            headless=False,
            viewport={"width": 1440, "height": 1000},
            **playwright_chromium_launch_options(),
        )
        return PlaywrightPublishContext(self._context, platform, account_id=account_id)

    async def close(self) -> None:
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


class PlaywrightPublishContext:
    """Conservative page operations used by platform adapters."""

    def __init__(self, context: Any, platform: str, *, account_id: str | None = None):
        self.context = context
        self.platform = platform
        self.account_id = account_id
        self.page: Any = None
        self._description_text = ""
        self._last_page_fingerprint = ""
        self._final_action_guard_armed = False
        self._cover_before_urls: list[str] = []
        self._cover_candidate_urls: list[str] = []
        # Douyin renders the selected topic as a semantic ``data-mention``
        # node but does not expose the remote challenge id in that DOM node.
        # The live suggestion response is the authoritative source for the
        # id; keep the short-lived label -> id binding for readback.
        self._topic_entity_ids: dict[str, str] = {}

    async def open_creator_page(self) -> None:
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.goto(CREATOR_UPLOAD_URLS[self.platform], wait_until="domcontentloaded")

    async def detect_state(self) -> str:
        """Return a conservative semantic page state for adapter decisions."""

        if not self.page:
            return "window_closed"
        try:
            if getattr(self.page, "is_closed", lambda: False)():
                return "window_closed"
            body = self.page.locator("body").first
            state = await body.get_attribute("data-state")
            auth_state = await body.get_attribute("data-auth-state")
            if state:
                return str(state)
            if auth_state:
                return str(auth_state)
            url = str(self.page.url)
            if "login" in url:
                return "signed_out"
            # The live Douyin creator page does not currently expose the
            # fixture-only ``data-state`` attributes. Prefer stable semantic
            # controls over broad body-text guesses so an authenticated
            # upload entry is not mistaken for ``unknown``.
            if await self.page.locator(
                "video, [data-testid='video-preview'], [data-testid='platform-processing'], "
                "[contenteditable='true'], input[placeholder*='标题'], textarea[placeholder*='标题']"
            ).count():
                return "editor_ready"
            if await self.page.locator("input[type='file']").count():
                return "upload_entry"
            content = (await self.page.content()).lower()
            if any(word in content for word in ("验证码", "captcha", "human-check")):
                return "captcha"
            if any(word in content for word in ("登录", "扫码", "sign in")):
                return "signed_out"
            return "unknown"
        except Exception:
            return "window_closed"

    async def page_fingerprint(self) -> str:
        """Hash stable editor identity markers, never raw page content.

        The URL/task-space identity is deliberately included so this is not
        merely a selector-count fingerprint.  Volatile upload progress and
        editor text are excluded, allowing a same-draft restart to reconcile
        while a different creator page fails closed.
        """

        if not self.page:
            return "sha256:window_closed"
        try:
            if await self.detect_state() == "window_closed":
                return "sha256:window_closed"
            task_space = await self.task_space_identity()
            markers = [
                _canonical_editor_url(self.platform, str(self.page.url)),
                str(task_space.get("name") or ""),
            ]
            if task_space.get("id"):
                markers.append(str(task_space["id"]))
            for selector in (
                "input[type='file']",
                "[contenteditable='true']",
                "button[data-guard]",
            ):
                markers.append(f"{selector}:{await self.page.locator(selector).count()}")
            try:
                stable_root = self.page.locator(
                    "[data-task-space-id], [data-task-id], [data-draft-id], main, form"
                ).first
                for attribute in ("data-task-space-id", "data-task-id", "data-draft-id", "id"):
                    try:
                        value = await stable_root.get_attribute(attribute, timeout=750)
                    except Exception:
                        value = None
                    if value:
                        markers.append(f"{attribute}:{value}")
            except Exception:
                pass
            digest = hashlib.sha256("|".join([self.platform, *markers]).encode()).hexdigest()
            fingerprint = f"sha256:{digest}"
            self._last_page_fingerprint = fingerprint
            return fingerprint
        except Exception:
            return "sha256:window_closed"

    async def task_space_identity(self) -> dict[str, Any]:
        """Return a stable, non-secret task-space name/id when exposed."""

        if not self.page:
            return {}
        task_id: int | None = None
        task_name = f"{self.platform}:{_canonical_editor_url(self.platform, str(self.page.url))}"
        locator = self.page.locator(
            "[data-task-space-id], [data-task-id], [data-draft-id]"
        ).first
        for attribute in ("data-task-space-id", "data-task-id", "data-draft-id"):
            try:
                value = await locator.get_attribute(attribute, timeout=750)
            except Exception:
                value = None
            if value and str(value).isdigit() and int(value) > 0:
                task_id = int(value)
                break
        if task_id is None:
            # Playwright pages do not expose Ego's numeric task-space id. Use
            # a deterministic local id paired with the canonical name so a
            # restart can reconcile the same profile/page without pretending
            # to have a platform-owned identifier.
            task_id = int(hashlib.sha256(task_name.encode()).hexdigest()[:12], 16)
        return {"id": task_id, "name": task_name}

    async def guard_action(self, action_id: str) -> bool:
        allowed = {"upload_media", "fill_title", "fill_description", "select_topic", "save_cover"}
        if action_id not in allowed:
            raise RuntimeError("FINAL_ACTION_BLOCKED")
        state = await self.detect_state()
        fingerprint = await self.page_fingerprint()
        if not fingerprint.startswith("sha256:") or fingerprint == "sha256:window_closed":
            raise RuntimeError("DOUYIN_PAGE_FINGERPRINT_REQUIRED")
        ready_states = {
            "upload_media": {"signed_in", "upload_entry", "ready_for_upload"},
            "fill_title": {"editor_ready"},
            "fill_description": {"editor_ready"},
            "select_topic": {"editor_ready"},
            "save_cover": {"editor_ready", "cover_modal"},
        }
        if state not in ready_states[action_id]:
            raise RuntimeError(f"DOUYIN_UNSAFE_STATE:{state}")
        return True

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
        if self.platform == "douyin":
            await self.guard_action("upload_media")
        for selector in ["input[type='file'][accept*='video']", "input[type='file']"]:
            file_input = self.page.locator(selector).first
            if await file_input.count():
                await file_input.set_input_files(video_path)
                return True
        return False

    async def uploaded_media_metadata(self) -> dict[str, Any] | None:
        """Read safe file metadata from the selected video input only."""

        if not self.page:
            return None
        inputs = self.page.locator("input[type='file'][accept*='video'], input[type='file']")
        for index in range(await inputs.count()):
            candidate = inputs.nth(index)
            try:
                metadata = await candidate.evaluate(
                    "node => { const f = node.files && node.files[0]; return f ? {name: f.name, size: f.size, type: f.type} : null; }"
                )
            except Exception:
                continue
            if isinstance(metadata, dict) and metadata.get("name") and isinstance(metadata.get("size"), int):
                return {
                    "name": str(metadata["name"]),
                    "size": int(metadata["size"]),
                    "type": str(metadata.get("type") or ""),
                }
        return None

    async def read_remote_media_identity(self) -> str | None:
        """Read a stable platform media id, excluding volatile signed URLs."""

        if not self.page:
            return None
        locator = self.page.locator(
            "[data-media-id], [data-video-id], video[data-id], [data-testid='video-preview']"
        )
        for index in range(min(await locator.count(), 8)):
            node = locator.nth(index)
            for attribute in ("data-media-id", "data-video-id", "data-id"):
                try:
                    value = await node.get_attribute(attribute)
                except Exception:
                    value = None
                if value and str(value).strip():
                    return str(value).strip()
        return None

    async def fill_title(self, title: str) -> bool:
        if self.platform == "douyin":
            await self.guard_action("fill_title")
        return await _fill_first_available(
            self.page,
            PLATFORM_FIELD_SELECTORS[self.platform]["title"],
            title,
        )

    async def fill_description(self, description: str) -> bool:
        if not description:
            return False
        if self.platform == "douyin":
            await self.guard_action("fill_description")
        self._description_text = description
        return await _fill_first_available(
            self.page,
            PLATFORM_FIELD_SELECTORS[self.platform]["description"],
            description,
        )

    async def fill_hashtags(self, hashtags: list[str]) -> bool:
        if not hashtags:
            return False
        if self.platform == "douyin":
            await self.guard_action("select_topic")
        text = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags if tag)
        if text:
            if self.platform == "douyin":
                # Douyin topics must be selected as platform entities.  A
                # plain text hashtag is deliberately not treated as success;
                # the adapter performs a strict entity readback afterwards.
                return await self._fill_douyin_topics(hashtags)
            combined = "\n".join(item for item in [self._description_text, text] if item)
            return await self.fill_description(combined)
        return False

    async def _fill_douyin_topics(self, hashtags: list[str]) -> bool:
        """Use the live ``#添加话题`` editor when no dedicated input exists."""

        trigger_locator = self.page.get_by_text("#添加话题", exact=True)
        editor_locator = self.page.locator("[contenteditable='true']")
        if await trigger_locator.count() != 1 or await editor_locator.count() != 1:
            return False
        trigger = trigger_locator.first
        editor = editor_locator.first
        for raw_tag in hashtags:
            tag = str(raw_tag).lstrip("#").strip()
            if not tag:
                continue
            await trigger.click()
            # The platform toolbar action itself opens the topic composer and
            # inserts the topic marker.  Typing another marker here produces
            # ``##tag`` in the live Slate editor (the marker is sometimes not
            # visible through ``inner_text`` immediately after the click),
            # which prevents the platform suggestion request from resolving.
            # Keep the action fail-closed: type only the label and require a
            # real entity readback after the suggestion is selected.
            await editor.press("End")
            responses: list[Any] = []

            def on_response(response: Any) -> None:
                if "/aweme/v1/search/challengesug/" in str(response.url):
                    responses.append(response)

            self.page.on("response", on_response)
            try:
                await editor.type(tag)
                await self.page.wait_for_timeout(1200)
                for response in responses[-20:]:
                    try:
                        payload = await response.json()
                    except Exception:
                        continue
                    for item in (payload.get("sug_list", []) if isinstance(payload, dict) else []):
                        if not isinstance(item, dict):
                            continue
                        label = str(item.get("cha_name") or "").strip()
                        entity_id = str(item.get("cid") or "").strip()
                        if label and entity_id:
                            self._topic_entity_ids[_normalize_topic_label(label).casefold()] = entity_id
            except Exception:
                # The typed label remains in the editor; the strict semantic
                # readback below will reject it if the platform did not return
                # an entity suggestion. Never type the label a second time.
                pass
            finally:
                self.page.remove_listener("response", on_response)
            # Prefer a visible suggestion row (the platform entity action),
            # falling back to Enter only when the editor exposes no row.  The
            # subsequent readback rejects a plain-text false positive.
            await self.page.wait_for_timeout(400)
            suggestion = self.page.locator(
                "[class*='mention-suggest-mount'] [class*='tag-hash-view-name']"
            ).filter(has_text=tag).first
            if await suggestion.count():
                # The text span is nested two levels below the clickable row.
                suggestion = suggestion.locator("xpath=../..")
            else:
                suggestion = self.page.locator(
                    "[role='option'], [data-testid*='topic'], [data-topic-id], li"
                ).filter(has_text=tag).first
            if await suggestion.count():
                await suggestion.click()
            else:
                await editor.press("Enter")
        return True

    async def upload_cover(self, cover_path: str) -> bool:
        if not cover_path:
            return False
        if self.platform == "douyin":
            await self.guard_action("save_cover")
        self._cover_before_urls = await self._read_cover_urls()
        self._cover_candidate_urls = []
        # Creator pages usually reveal this control after the video begins processing.
        # We only target image-only file inputs so the video upload control cannot be reused.
        for selector in [
            "input[type='file'][accept*='image']",
            "input[type='file'][accept*='.jpg']",
            "input[type='file'][accept*='.png']",
        ]:
            locator = self.page.locator(selector).last
            if await locator.count():
                cover_responses: list[Any] = []

                def on_response(response: Any) -> None:
                    path = urlsplit(str(response.url)).path.lower()
                    if path.startswith("/tos-cn-i-") and "~tplv" in path:
                        cover_responses.append(response)

                self.page.on("response", on_response)
                try:
                    await locator.set_input_files(cover_path)
                    # Douyin opens a crop modal after the image input changes;
                    # the asset is not part of the draft until its own
                    # modal-level ``保存`` action completes. Scope the click
                    # to the dialog so the fixed bottom ``发布`` button can
                    # never be selected.
                    dialog = self.page.locator("[role='modal']")
                    save = dialog.get_by_role("button", name="保存", exact=True)
                    elapsed = 0
                    while elapsed <= 3000 and (await dialog.count() != 1 or await save.count() != 1):
                        await self.page.wait_for_timeout(200)
                        elapsed += 200
                    if await dialog.count() != 1 or await save.count() != 1:
                        return False
                    await save.click()
                    elapsed = 0
                    while elapsed <= 3000:
                        if await self.page.locator("[role='modal']").count() == 0:
                            await self.page.wait_for_timeout(800)
                            for response in cover_responses:
                                try:
                                    content_type = (await response.header_value("content-type") or "").lower()
                                except Exception:
                                    continue
                                if not content_type.startswith("image/"):
                                    continue
                                url = str(response.url).split("?", 1)[0]
                                if url.startswith("https://") and url not in self._cover_candidate_urls:
                                    self._cover_candidate_urls.append(url)
                            return True
                        await self.page.wait_for_timeout(200)
                        elapsed += 200
                    return False
                finally:
                    self.page.remove_listener("response", on_response)
        return False

    async def read_topic_entities(self) -> list[dict[str, str]]:
        """Return only topic nodes with a platform entity id.

        Text in a contenteditable is intentionally excluded.  This keeps a
        successful checkpoint tied to the platform's resolved topic entity,
        not merely to the characters ``#foo`` rendered by the editor.
        """

        if not self.page or self.platform != "douyin":
            return []
        locator = self.page.locator(
            "[data-mention], [data-mention-id], [data-topic-id], [data-topic-id]"
        )
        entities: list[dict[str, str]] = []
        for index in range(min(await locator.count(), 30)):
            node = locator.nth(index)
            try:
                entity_id = (
                    await node.get_attribute("data-mention-id")
                    or await node.get_attribute("data-topic-id")
                    or await node.get_attribute("data-id")
                    or ""
                ).strip()
                mention_type = (await node.get_attribute("data-mention") or "#").strip()
                if mention_type not in {"#", "activity"}:
                    continue
                label = str(await node.inner_text()).strip()
                if not label:
                    label = (await node.get_attribute("aria-label") or "").strip()
                if not label:
                    continue
                if not entity_id:
                    entity_id = self._topic_entity_ids.get(
                        _normalize_topic_label(label).casefold(),
                        "",
                    )
                if not entity_id:
                    continue
                entities.append(
                    {
                        "label": label,
                        "normalized_label": _normalize_topic_label(label),
                        "mention_type": mention_type,
                        "entity_id": entity_id,
                    }
                )
            except Exception:
                continue
        return entities

    async def seed_topic_entity_ids(self, entities: list[dict[str, str]]) -> None:
        """Restore accepted ids when a same-draft restart hides them from DOM."""

        for entity in entities or []:
            if not isinstance(entity, dict):
                continue
            label = str(entity.get("normalized_label") or entity.get("label") or "").strip()
            entity_id = str(entity.get("entity_id") or "").strip()
            if label and entity_id:
                self._topic_entity_ids.setdefault(
                    _normalize_topic_label(label).casefold(), entity_id
                )

    async def _read_cover_urls(self) -> list[str]:
        if not self.page:
            return []
        locator = self.page.locator(
            "[data-testid='cover-preview'] img, [data-testid='cover-preview'] source, "
            "[data-testid='cover-modal'] img, [data-testid='cover-modal'] source, "
            "[data-cover-url], img[data-cover-url]"
        )
        urls: list[str] = []
        for index in range(min(await locator.count(), 12)):
            node = locator.nth(index)
            try:
                value = (
                    await node.get_attribute("data-cover-url")
                    or await node.get_attribute("src")
                    or await node.get_attribute("currentSrc")
                    or ""
                ).strip()
                if value.startswith("https://") and value not in urls:
                    urls.append(value)
            except Exception:
                continue
        for value in self._cover_candidate_urls:
            if value not in urls:
                urls.append(value)
        return urls

    async def read_cover_receipt(self, _cover_path: str) -> dict[str, Any] | None:
        """Read the accepted cover URL from the visible cover preview."""

        if not self.page or self.platform != "douyin":
            return None
        elapsed = 0
        while elapsed <= 5_000:
            urls = await self._read_cover_urls()
            accepted = next((url for url in urls if url not in self._cover_before_urls), None)
            if accepted:
                task_space = await self.task_space_identity()
                return {
                    "before_urls": list(self._cover_before_urls),
                    "accepted_url": accepted,
                    "task_space_id": task_space.get("id"),
                    "task_space_name": task_space.get("name"),
                }
            if await self.page.locator("body").count() == 0:
                return None
            await self.page.wait_for_timeout(250)
            elapsed += 250
        return None

    async def wait_until_draft_ready(self) -> None:
        await self.page.wait_for_timeout(1000)

    async def wait_for_state(self, expected_state: str, *, timeout_ms: int = 30_000) -> bool:
        """Poll a known semantic state; unknown/challenge states stop immediately."""

        if not self.page:
            return False
        elapsed = 0
        while elapsed <= timeout_ms:
            state = await self.detect_state()
            if state == expected_state:
                return True
            if state in {"signed_out", "captcha", "unknown", "network_error", "window_closed"}:
                return False
            await self.page.wait_for_timeout(500)
            elapsed += 500
        return False

    async def wait_for_interactive_state(self, *, timeout_ms: int = 12_000) -> str:
        """Wait through the initial client-rendering gap without broad retries."""

        if not self.page:
            return "window_closed"
        elapsed = 0
        while elapsed <= timeout_ms:
            state = await self.detect_state()
            if state != "unknown":
                return state
            await self.page.wait_for_timeout(500)
            elapsed += 500
        return "unknown"

    async def wait_for_editor_ready(self, *, timeout_ms: int = 30_000) -> bool:
        """Poll editor readiness while the platform finishes media processing."""

        if not self.page:
            return False
        elapsed = 0
        while elapsed <= timeout_ms:
            state = await self.detect_state()
            if state == "editor_ready":
                return True
            if state in {"signed_out", "captcha", "window_closed", "network_error"}:
                return False
            await self.page.wait_for_timeout(500)
            elapsed += 500
        return False

    async def wait_for_video_readback(self, *, timeout_ms: int = 30_000) -> bool:
        """Wait until the uploaded media has a semantic preview marker."""

        if not self.page:
            return False
        elapsed = 0
        while elapsed <= timeout_ms:
            if await self.page.locator(
                "[data-testid='video-preview'], [data-testid='platform-processing'], video"
            ).count():
                return True
            if await self.page.locator("body").count() == 0:
                return False
            await self.page.wait_for_timeout(500)
            elapsed += 500
        return False

    async def wait_for_field(self, field_name: str, expected: Any, *, timeout_ms: int = 5_000) -> bool:
        """Allow client-side editor state a short, bounded readback window."""

        elapsed = 0
        while elapsed <= timeout_ms:
            if await self.verify_field(field_name, expected):
                return True
            if not self.page or await self.page.locator("body").count() == 0:
                return False
            await self.page.wait_for_timeout(250)
            elapsed += 250
        return False

    async def verify_field(self, field_name: str, expected: Any) -> bool:
        """Perform semantic readback without returning page HTML to callers."""

        if not self.page:
            return False
        if field_name == "video":
            if await self.page.locator(
                "[data-testid='video-preview'], [data-testid='platform-processing'], video"
            ).count():
                return True
            return await _file_input_selected(self.page, "video")
        if field_name == "cover":
            receipt = await self.read_cover_receipt(str(expected))
            return receipt is not None
        if field_name == "title":
            selectors = PLATFORM_FIELD_SELECTORS[self.platform]["title"]
            value = await _read_first_available(self.page, selectors)
            return value == str(expected)
        if field_name == "description":
            selectors = PLATFORM_FIELD_SELECTORS[self.platform]["description"]
            value = await _read_first_available(self.page, selectors)
            expected_normalized = " ".join(str(expected).split())
            actual_normalized = " ".join(value.split())
            return expected_normalized in actual_normalized
        if field_name == "hashtags":
            entities = await self.read_topic_entities()
            actual = {item["normalized_label"] for item in entities}
            return all(_normalize_topic_label(tag) in actual for tag in expected if tag)
        return False

    async def request_final_action(self) -> bool:
        """FinalActionGuard: this adapter never exposes a submit/publish click."""

        self._final_action_guard_armed = bool(self.page and not self.page.is_closed())
        return False

    async def final_action_guard_armed(self) -> bool:
        """Report that the runtime reached its local no-click safety gate."""

        return self._final_action_guard_armed

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


async def _read_first_available(page: Any, selectors: list[str]) -> str:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if not await locator.count():
                continue
            if "contenteditable" in selector:
                return str(await locator.inner_text())
            return str(await locator.input_value())
        except Exception:
            continue
    return ""


async def _file_input_selected(page: Any, kind: str) -> bool:
    accept = "video" if kind == "video" else "image"
    inputs = page.locator(f"input[type='file'][accept*='{accept}']")
    for index in range(await inputs.count()):
        candidate = inputs.nth(index)
        try:
            if await candidate.evaluate("node => Boolean(node.files && node.files.length)"):
                return True
        except Exception:
            continue
    return False


def _normalize_topic_label(value: Any) -> str:
    return str(value or "").strip().lstrip("#").strip().casefold()
