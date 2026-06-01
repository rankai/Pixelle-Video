"""Douyin publishing adapter skeleton.

The adapter prepares a draft and deliberately stops before final publishing.
"""

import inspect
from typing import Any

from pixelle_video.services.publish.browser_runtime import BrowserRuntime
from pixelle_video.services.publish.models import (
    PublishPackage,
    PublishResult,
    PublishStatus,
)

DOUYIN_CREATOR_PLATFORM = "douyin"


class DouyinPublisher:
    """Prepare Douyin drafts through an injected browser runtime."""

    def __init__(self, runtime: BrowserRuntime):
        self.runtime = runtime

    async def prepare_draft(self, package: PublishPackage) -> PublishResult:
        context = await self.runtime.launch_persistent_context(DOUYIN_CREATOR_PLATFORM)
        await _call_if_available(context, "open_creator_page")

        logged_in = await _call_if_available(context, "is_logged_in", default=False)
        if not logged_in:
            return PublishResult(
                status=PublishStatus.LOGIN_REQUIRED,
                platform=DOUYIN_CREATOR_PLATFORM,
                message="请先在发布助手浏览器中登录抖音创作者中心。",
            )

        await _call_if_available(context, "upload_video", package.video_path)
        await _call_if_available(context, "fill_title", package.title)
        await _call_if_available(context, "fill_description", package.description)
        await _call_if_available(context, "fill_hashtags", package.hashtags)
        if package.cover_path:
            await _call_if_available(context, "upload_cover", package.cover_path)
        await _call_if_available(context, "wait_until_draft_ready")

        return PublishResult(
            status=PublishStatus.DRAFT_READY,
            platform=DOUYIN_CREATOR_PLATFORM,
            message="抖音发布草稿已准备好，请在发布助手浏览器中最终确认并发布。",
        )


async def _call_if_available(target: Any, method_name: str, *args: Any, default: Any = None) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        return default
    result = method(*args)
    if inspect.isawaitable(result):
        return await result
    return result
