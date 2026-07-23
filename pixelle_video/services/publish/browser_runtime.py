"""Browser runtime abstraction for desktop publishing automation."""

import hashlib
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from pixelle_video.services.publish.platform_profiles import PLATFORM_ADAPTER_PROFILES
from pixelle_video.utils.chromium import playwright_chromium_launch_options
from pixelle_video.utils.os_util import get_data_path

DEFAULT_BROWSER_RUNTIME = "playwright"
SUPPORTED_BROWSER_RUNTIMES = {"playwright", "cloakbrowser"}
CREATOR_UPLOAD_URLS = {
    "douyin": "https://creator.douyin.com/creator-micro/content/upload",
    **{platform: profile.entry_url for platform, profile in PLATFORM_ADAPTER_PROFILES.items()},
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
            "div[contenteditable='true'][role='textbox']",
            "textarea[placeholder*='正文']",
            "textarea",
        ],
    },
    "shipinhao": {
        "title": ["input[placeholder*='标题']", "textarea[placeholder*='标题']"],
        "description": [
            "div[contenteditable][data-placeholder*='描述']",
            "div.post-desc-box .input-editor",
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
        self._platform_fallback_boundaries: list[str] = []
        # Douyin renders the selected topic as a semantic ``data-mention``
        # node but does not expose the remote challenge id in that DOM node.
        # The live suggestion response is the authoritative source for the
        # id; keep the short-lived label -> id binding for readback.
        self._topic_entity_ids: dict[str, str] = {}

    async def open_creator_page(self) -> None:
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.page.goto(CREATOR_UPLOAD_URLS[self.platform], wait_until="domcontentloaded")
        # Some creator login shells close the navigation tab and hand the
        # route to a newly-created tab. Rebind the context to the live page so
        # a legitimate redirect is not reported as ``window_closed``.
        if self.page.is_closed() and self.context.pages:
            self.page = self.context.pages[-1]

    async def _content_root(self) -> Any:
        """Return the platform editor root, including Wujie Shadow DOM."""

        if not self.page:
            return None
        if self.platform == "shipinhao":
            root = self.page.locator("wujie-app").first
            if await root.count():
                return root
        return self.page

    async def detect_state(self) -> str:
        """Return a conservative semantic page state for adapter decisions."""

        if not self.page:
            return "window_closed"
        try:
            if getattr(self.page, "is_closed", lambda: False)():
                return "window_closed"
            body = self.page.locator("body").first
            if await _has_visible_challenge(self.page):
                return "captcha"
            content = (await self.page.content()).lower()
            state = await body.get_attribute("data-state")
            auth_state = await body.get_attribute("data-auth-state")
            if state:
                return str(state)
            if auth_state:
                return str(auth_state)
            url = str(self.page.url)
            if "login" in url:
                return "signed_out"
            profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
            root = await self._content_root()
            if profile:
                for marker in (*profile.signed_out_markers, *profile.login_markers):
                    if await self.page.get_by_text(marker, exact=False).count():
                        return "signed_out"
            # The live Douyin creator page does not currently expose the
            # fixture-only ``data-state`` attributes. Prefer stable semantic
            # controls over broad body-text guesses so an authenticated
            # upload entry is not mistaken for ``unknown``.
            if await root.locator(
                "video, [data-testid='video-preview'], [data-testid='platform-processing'], "
                "[contenteditable='true'], input[placeholder*='标题'], textarea[placeholder*='标题']"
            ).count():
                return "editor_ready"
            profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
            if profile:
                for marker in profile.editor_markers:
                    if await root.get_by_text(marker, exact=False).count():
                        return "editor_ready"
            if await root.locator("input[type='file']").count():
                return "upload_entry"
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
            root = await self._content_root()
            for selector in (
                "input[type='file']",
                "[contenteditable='true']",
                "button[data-guard]",
            ):
                markers.append(f"{selector}:{await root.locator(selector).count()}")
            try:
                stable_root = root.locator(
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
        root = await self._content_root()
        locator = root.locator(
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
        # Kuaishou renders the authenticated creator shell in a second
        # client-side pass; probing during that gap briefly exposes the
        # public landing page's "立即登录" marker even for a valid session.
        await self.page.wait_for_timeout(2_500 if self.platform == "kuaishou" else 1_500)
        url = self.page.url
        if "login" in url:
            return False
        profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
        content = await self.page.content()
        login_words = ["扫码登录", "登录后", "请登录", "验证码"]
        if profile:
            login_words.extend(profile.signed_out_markers)
        if any(word in content for word in login_words):
            return False
        return True

    async def _has_uploaded_media_preview(self) -> bool:
        """Detect the current draft's media preview without broad DOM counts.

        A creator page can contain unrelated ``<video>`` elements (tutorials,
        ads, or hidden preloads).  Treat only a known preview/processing marker
        or a visible media element with a loaded source and non-zero geometry
        as evidence that this draft already owns an uploaded video.
        """

        if not self.page:
            return False
        profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
        root = await self._content_root()
        selectors = (
            list(profile.media_identity_selectors)
            if profile
            else []
        )
        selectors.extend(
            [
                "[data-testid='video-preview']",
                "[data-testid='platform-processing']",
                "main video",
                "[role='main'] video",
                "[class*='preview'] video",
                "[class*='upload'] video",
                "[class*='editor'] video",
            ]
        )
        for selector in dict.fromkeys(selectors):
            locator = root.locator(selector)
            for index in range(min(await locator.count(), 8)):
                candidate = locator.nth(index)
                try:
                    if await candidate.is_visible():
                        return True
                except Exception:
                    continue

        # For a known platform, do not fall back to every visible video on
        # the page: tutorials, ads, and preloads must not suppress the
        # one-time upload. The scoped selectors above are the only preview
        # candidates. Keep the generic fallback only for an unknown platform
        # where no platform contract exists yet.
        if profile:
            return False
        videos = root.locator("video")
        for index in range(min(await videos.count(), 8)):
            candidate = videos.nth(index)
            try:
                if not await candidate.is_visible():
                    continue
                metadata = await candidate.evaluate(
                    """node => {
                        const rect = node.getBoundingClientRect();
                        return {
                            src: node.currentSrc || node.src || '',
                            poster: node.poster || '',
                            width: rect.width,
                            height: rect.height,
                        };
                    }"""
                )
                if (
                    isinstance(metadata, dict)
                    and (metadata.get("src") or metadata.get("poster"))
                    and float(metadata.get("width") or 0) > 0
                    and float(metadata.get("height") or 0) > 0
                ):
                    return True
            except Exception:
                continue
        return False

    async def upload_video(self, video_path: str) -> bool:
        if self.platform == "kuaishou":
            # The Kuaishou page has two hidden video inputs and only the
            # visible upload control dispatches the client-side upload event.
            # Reuse an already-open draft preview instead of injecting the
            # same media a second time after a restart.
            resume = self.page.get_by_role("button", name="继续编辑", exact=True)
            if await resume.count() == 1:
                await resume.click()
                await self.page.wait_for_timeout(1_200)
            if await self._has_uploaded_media_preview():
                return True
            button = self.page.get_by_role("button", name="上传视频", exact=True)
            visible: list[int] = []
            for index in range(await button.count()):
                try:
                    if await button.nth(index).is_visible():
                        visible.append(index)
                except Exception:
                    continue
            if len(visible) != 1:
                return False
            try:
                async with self.page.expect_file_chooser(timeout=10_000) as info:
                    await button.nth(visible[0]).click()
                chooser = await info.value
                await chooser.set_files(video_path)
            except Exception:
                return False
            return await self.wait_for_video_readback(timeout_ms=30_000)
        if self.platform == "douyin":
            await self.guard_action("upload_media")
        profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
        selectors = list(profile.video_input_selectors) if profile else ["input[type='file'][accept*='video']", "input[type='file']"]
        if self.platform == "shipinhao":
            selectors.append("input[type='file']")
        root = await self._content_root()
        for selector in selectors:
            file_input = root.locator(selector).first
            if await file_input.count():
                await file_input.set_input_files(video_path)
                # Xiaohongshu (and similar client-side editors) replaces the
                # selected input while it creates a blob preview. Returning
                # immediately makes the publisher perform its semantic
                # readback before that preview exists and falsely report
                # VIDEO_READBACK_FAILED. Keep the wait bounded and let the
                # same scoped preview probe be the source of truth.
                if self.platform == "xiaohongshu":
                    return await self.wait_for_video_readback(timeout_ms=30_000)
                return True
        return False

    async def uploaded_media_metadata(self) -> dict[str, Any] | None:
        """Read safe file metadata from the selected video input only."""

        if not self.page:
            return None
        root = await self._content_root()
        inputs = root.locator("input[type='file'][accept*='video'], input[type='file']")
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
        profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
        root = await self._content_root()
        selectors = (
            list(profile.media_identity_selectors)
            if profile
            else ["[data-media-id]", "[data-video-id]", "video[data-id]"]
        )
        locator = root.locator(", ".join(selectors))
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
        root = await self._content_root()
        return await _fill_first_available(
            root,
            _platform_field_selectors(self.platform, "title"),
            title,
        )

    async def fill_description(self, description: str) -> bool:
        if not description:
            return False
        if self.platform == "douyin":
            await self.guard_action("fill_description")
        self._description_text = description
        root = await self._content_root()
        return await _fill_first_available(
            root,
            _platform_field_selectors(self.platform, "description"),
            description,
        )

    async def fill_hashtags(self, hashtags: list[str]) -> bool:
        if not hashtags:
            return False
        if self.platform == "douyin":
            await self.guard_action("select_topic")
        text = " ".join(f"#{tag.lstrip('#')}" for tag in hashtags if tag)
        if text:
            profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
            if self.platform == "douyin" or (profile and profile.supports_topic_entities):
                # Douyin topics must be selected as platform entities.  A
                # plain text hashtag is deliberately not treated as success;
                # the adapter performs a strict entity readback afterwards.
                return await self._fill_douyin_topics(hashtags)
            self._platform_fallback_boundaries.append("HASHTAGS_TEXT_FALLBACK")
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
        if self.platform == "xiaohongshu":
            # Xiaohongshu exposes the image input only after the visible
            # ``设置封面`` tile opens its cover editor.  The input is hidden
            # inside the modal, so setting the initial video input (or
            # looking for an image input before opening the modal) is a
            # no-op.  Confirm the modal before treating the local preview as
            # accepted; the platform does not expose a durable HTTPS receipt.
            self._cover_before_urls = await self._read_cover_urls()
            root = await self._content_root()
            trigger = root.locator(".upload-cover")
            visible_triggers: list[int] = []
            for index in range(await trigger.count()):
                try:
                    if await trigger.nth(index).is_visible():
                        visible_triggers.append(index)
                except Exception:
                    continue
            if len(visible_triggers) != 1:
                return False
            try:
                await trigger.nth(visible_triggers[0]).click(timeout=10_000)
            except Exception:
                # The recommendation panel can replace the tile between the
                # visibility probe and click. Re-acquire it once after this
                # observed DOM-detach race; never broaden to an arbitrary
                # text click or retry the media upload.
                refreshed = root.locator(".upload-cover")
                fresh_visible: list[int] = []
                for index in range(await refreshed.count()):
                    try:
                        if await refreshed.nth(index).is_visible():
                            fresh_visible.append(index)
                    except Exception:
                        continue
                if len(fresh_visible) != 1:
                    return False
                try:
                    await refreshed.nth(fresh_visible[0]).click(timeout=10_000)
                except Exception:
                    return False
            image_input = root.locator("input[type='file'][accept*='image']").first
            elapsed = 0
            while elapsed <= 3_000 and await image_input.count() != 1:
                await self.page.wait_for_timeout(200)
                elapsed += 200
            if await image_input.count() != 1:
                return False
            try:
                await image_input.set_input_files(cover_path)
            except Exception:
                return False
            confirm = self.page.get_by_role("button", name="确定", exact=True)
            elapsed = 0
            while elapsed <= 3_000 and await confirm.count() != 1:
                await self.page.wait_for_timeout(200)
                elapsed += 200
            if await confirm.count() != 1:
                return False
            await confirm.click()
            elapsed = 0
            while elapsed <= 5_000 and await root.locator(".cover-modal").count() != 0:
                await self.page.wait_for_timeout(200)
                elapsed += 200
            if await root.locator(".cover-modal").count() != 0:
                return False
            self._cover_candidate_urls = ["blob:accepted-preview"]
            return True
        if self.platform == "kuaishou":
            # Kuaishou exposes a cover input only after opening the cover
            # editor and switching from frame capture to custom upload.
            # Follow that visible flow so the platform commits the cover;
            # setting the hidden input directly only creates a local file
            # selection and produces no accepted preview receipt.
            self._cover_before_urls = await self._read_cover_urls()
            cover_labels = self.page.get_by_text("封面设置", exact=True)
            if await cover_labels.count() < 2:
                return False
            await cover_labels.nth(1).click()
            dialog = self.page.get_by_role("dialog")
            elapsed = 0
            while elapsed <= 3_000 and await dialog.count() != 1:
                await self.page.wait_for_timeout(200)
                elapsed += 200
            if await dialog.count() != 1:
                return False
            upload_tab = dialog.get_by_text("上传封面", exact=True)
            if await upload_tab.count() != 1:
                return False
            upload_button = dialog.get_by_role("button", name="上传图片", exact=True)
            # Reopening a draft that already has a custom cover lands on the
            # upload tab. Only switch tabs when the upload control is absent;
            # clicking an already-active tab toggles back to frame capture.
            if await upload_button.count() != 1:
                dialog_text = await dialog.inner_text()
                if "清空上传" in dialog_text:
                    # The draft already has a confirmed custom cover. Keep it
                    # idempotent across restart instead of forcing a second
                    # upload of the same image.
                    existing_urls = await self._read_cover_urls()
                    if "blob:accepted-preview" in existing_urls:
                        self._cover_candidate_urls = ["blob:accepted-preview"]
                    elif existing_urls:
                        self._cover_candidate_urls = [existing_urls[0]]
                    confirm_existing = dialog.get_by_role("button", name="确认", exact=True)
                    if await confirm_existing.count() != 1:
                        return False
                    await confirm_existing.click()
                    elapsed = 0
                    while elapsed <= 3_000 and await self.page.get_by_role("dialog").count() != 0:
                        await self.page.wait_for_timeout(200)
                        elapsed += 200
                    after_urls = await self._read_cover_urls()
                    if "blob:accepted-preview" in after_urls:
                        self._cover_candidate_urls = ["blob:accepted-preview"]
                    elif after_urls and not self._cover_candidate_urls:
                        self._cover_candidate_urls = [after_urls[0]]
                    return bool(after_urls or self._cover_candidate_urls)
                await upload_tab.click()
            elapsed = 0
            while elapsed <= 3_000 and await upload_button.count() != 1:
                await self.page.wait_for_timeout(200)
                elapsed += 200
            if await upload_button.count() != 1:
                return False
            try:
                async with self.page.expect_file_chooser(timeout=10_000) as info:
                    await upload_button.click()
                chooser = await info.value
                await chooser.set_files(cover_path)
            except Exception:
                return False
            await self.page.wait_for_timeout(500)
            # The cover upload replaces the dialog subtree; reacquire the
            # live dialog before resolving the post-upload confirmation.
            confirm_dialog = self.page.get_by_role("dialog")
            confirm = confirm_dialog.get_by_role("button", name="确认", exact=True)
            elapsed = 0
            while elapsed <= 3_000 and await confirm.count() != 1:
                await self.page.wait_for_timeout(200)
                elapsed += 200
            if await confirm.count() != 1:
                return False
            await confirm.click()
            elapsed = 0
            while elapsed <= 5_000:
                if await self.page.get_by_role("dialog").count() == 0:
                    await self.page.wait_for_timeout(500)
                    after_urls = await self._read_cover_urls()
                    if "blob:accepted-preview" in after_urls:
                        self._cover_candidate_urls = ["blob:accepted-preview"]
                    elif after_urls:
                        # Some Kuaishou builds expose only the CDN preview
                        # after confirmation; retain the first stable URL as
                        # the accepted candidate even when it matches the
                        # pre-generated frame list.
                        self._cover_candidate_urls = [after_urls[0]]
                    return bool(after_urls)
                await self.page.wait_for_timeout(200)
                elapsed += 200
            return False
        self._cover_before_urls = await self._read_cover_urls()
        self._cover_candidate_urls = []
        root = await self._content_root()
        # Creator pages usually reveal this control after the video begins processing.
        # We only target image-only file inputs so the video upload control cannot be reused.
        profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
        selectors = list(profile.cover_input_selectors) if profile else [
            "input[type='file'][accept*='image']",
            "input[type='file'][accept*='.jpg']",
            "input[type='file'][accept*='.png']",
        ]
        for selector in selectors:
            locator = root.locator(selector).last
            if await locator.count():
                cover_responses: list[Any] = []

                def on_response(response: Any) -> None:
                    path = urlsplit(str(response.url)).path.lower()
                    if path.startswith("/tos-cn-i-") and "~tplv" in path:
                        cover_responses.append(response)

                self.page.on("response", on_response)
                try:
                    await locator.set_input_files(cover_path)
                    if self.platform != "douyin":
                        elapsed = 0
                        while elapsed <= 3_000:
                            if await _file_input_selected(root, "image"):
                                return True
                            # The Channels editor replaces the hidden image
                            # input after accepting the file. A preview is a
                            # valid local readback even when that replacement
                            # clears the original input's FileList.
                            if await self._read_cover_urls():
                                return True
                            await self.page.wait_for_timeout(250)
                            elapsed += 250
                        return False
                    # Douyin opens a crop modal after the image input changes;
                    # the asset is not part of the draft until its own
                    # modal-level ``保存`` action completes. Scope the click
                    # to the dialog so the fixed bottom ``发布`` button can
                    # never be selected.
                    dialog = root.locator("[role='modal']")
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
                        if await root.locator("[role='modal']").count() == 0:
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

        if not self.page:
            return []
        root = await self._content_root()
        locator = root.locator(
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
        profile = PLATFORM_ADAPTER_PROFILES.get(self.platform)
        root = await self._content_root()
        selectors = (
            list(profile.cover_preview_selectors)
            if profile
            else [
                "[data-testid='cover-preview'] img",
                "[data-testid='cover-preview'] source",
                "[data-testid='cover-modal'] img",
                "[data-testid='cover-modal'] source",
                "[data-cover-url]",
                "img[data-cover-url]",
            ]
        )
        locator = root.locator(", ".join(selectors))
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
                elif self.platform in {"kuaishou", "shipinhao"} and value.startswith("blob:"):
                    # These editors can keep an accepted custom cover as a
                    # local blob preview; the volatile URL is not a durable
                    # receipt, so expose only a stable scheme token and let
                    # the adapter record the platform-specific boundary.
                    stable_blob = "blob:accepted-preview"
                    if stable_blob not in urls:
                        urls.append(stable_blob)
            except Exception:
                continue
        for value in self._cover_candidate_urls:
            if value not in urls:
                urls.append(value)
        return urls

    async def read_cover_receipt(self, _cover_path: str) -> dict[str, Any] | None:
        """Read the accepted cover URL from the visible cover preview."""

        if not self.page:
            return None
        if self.platform != "douyin":
            elapsed = 0
            while elapsed <= 3_000:
                urls = await self._read_cover_urls()
                accepted = next((url for url in urls if url not in self._cover_before_urls), None)
                if (
                    not accepted
                    and self.platform in {"kuaishou", "xiaohongshu"}
                    and self._cover_candidate_urls
                ):
                    # A Kuaishou custom cover is confirmed in the UI but is
                    # represented by the same stable blob token as the
                    # pre-generated preview. The candidate is authoritative
                    # because it is recorded only after the modal confirms.
                    accepted = self._cover_candidate_urls[-1]
                if accepted:
                    task_space = await self.task_space_identity()
                    return {
                        "before_urls": list(self._cover_before_urls),
                        "accepted_url": accepted,
                        "task_space_id": task_space.get("id"),
                        "task_space_name": task_space.get("name"),
                    }
                # A Wujie app is an open ShadowRoot, not a document; it has
                # no nested <body>. Use the host page as the lifecycle probe
                # while keeping all editor selectors scoped to the app root.
                if await self.page.locator("body").count() == 0:
                    return None
                await self.page.wait_for_timeout(250)
                elapsed += 250
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
        # Kuaishou briefly renders its public shell (including "立即登录")
        # before hydrating the authenticated creator editor. Do not turn
        # that transient shell into a false login-required result.
        elapsed = 0
        if self.platform == "kuaishou":
            await self.page.wait_for_timeout(3_000)
            elapsed = 3_000
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
            if await self._has_uploaded_media_preview():
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
        root = await self._content_root()
        if field_name == "video":
            if await self._has_uploaded_media_preview():
                return True
            return await _file_input_selected(root, "video")
        if field_name == "cover":
            receipt = await self.read_cover_receipt(str(expected))
            return receipt is not None
        if field_name == "title":
            selectors = _platform_field_selectors(self.platform, "title")
            value = await _read_first_available(root, selectors)
            return value == str(expected)
        if field_name == "description":
            selectors = _platform_field_selectors(self.platform, "description")
            value = await _read_first_available(root, selectors)
            expected_normalized = " ".join(str(expected).split())
            actual_normalized = " ".join(value.split())
            return expected_normalized in actual_normalized
        if field_name == "hashtags":
            entities = await self.read_topic_entities()
            actual = {item["normalized_label"] for item in entities}
            if all(_normalize_topic_label(tag) in actual for tag in expected if tag):
                return True
            if self.platform != "douyin":
                description = await _read_first_available(
                    root, _platform_field_selectors(self.platform, "description")
                )
                normalized_description = " ".join(description.split()).casefold()
                return all(
                    f"#{_normalize_topic_label(tag)}" in normalized_description
                    for tag in expected
                    if tag
                )
            return False
        return False

    async def platform_fallback_boundaries(self) -> list[str]:
        return list(dict.fromkeys(self._platform_fallback_boundaries))

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


def _platform_field_selectors(platform: str, field_name: str) -> list[str]:
    profile = PLATFORM_ADAPTER_PROFILES.get(platform)
    if profile:
        if field_name == "title":
            return list(profile.title_selectors)
        if field_name == "description":
            return list(profile.description_selectors)
    return list(PLATFORM_FIELD_SELECTORS.get(platform, {}).get(field_name, []))


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
    # Platforms such as Xiaohongshu advertise video inputs as an extension
    # list (``.mp4,.mov,...``) instead of a MIME accept value. Inspect every
    # file input's selected File metadata and classify by MIME/extension.
    inputs = page.locator("input[type='file']")
    for index in range(await inputs.count()):
        candidate = inputs.nth(index)
        try:
            selected = await candidate.evaluate(
                """node => {
                    const file = node.files && node.files[0];
                    return file ? {name: file.name || '', type: file.type || ''} : null;
                }"""
            )
            if selected is True:
                return True
            if not isinstance(selected, dict):
                continue
            name = str(selected.get("name") or "").lower()
            mime = str(selected.get("type") or "").lower()
            if kind == "video":
                if mime.startswith("video/") or name.endswith((".mp4", ".mov", ".flv", ".f4v", ".mkv", ".rm", ".rmvb", ".m4v", ".mpg", ".mpeg", ".ts")):
                    return True
            elif mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp")):
                return True
        except Exception:
            continue
    return False


async def _has_visible_challenge(page: Any) -> bool:
    """Detect an actual visible challenge, not hidden creator-page copy."""

    selectors = (
        "[data-testid='human-check']",
        "[data-state='captcha']",
        "[class*='captcha']",
        "[class*='risk']",
        "[class*='verify']",
    )
    for selector in selectors:
        try:
            locator = page.locator(selector)
            for index in range(min(await locator.count(), 8)):
                if await locator.nth(index).is_visible():
                    return True
        except Exception:
            continue
    for marker in ("验证码", "captcha", "human-check", "安全验证", "风险验证"):
        try:
            locator = page.get_by_text(marker, exact=False)
            for index in range(min(await locator.count(), 8)):
                if await locator.nth(index).is_visible():
                    return True
        except Exception:
            continue
    return False


def _normalize_topic_label(value: Any) -> str:
    return str(value or "").strip().lstrip("#").strip().casefold()
