"""Shared conservative publisher that stops before the final submit action."""

import inspect
from typing import Any

from pixelle_video.services.publish.browser_runtime import BrowserRuntime
from pixelle_video.services.publish.models import PublishPackage, PublishResult, PublishStatus

PLATFORM_LABELS = {
    "douyin": "抖音",
    "xiaohongshu": "小红书",
    "shipinhao": "视频号",
    "kuaishou": "快手",
}


class HumanConfirmedPublisher:
    """Fill a creator draft without exposing a final-publish browser action."""

    platform: str

    def __init__(self, runtime: BrowserRuntime, platform: str):
        if platform not in PLATFORM_LABELS:
            raise ValueError(f"Unsupported publish platform: {platform}")
        self.runtime = runtime
        self.platform = platform

    async def prepare_draft(self, package: PublishPackage) -> PublishResult:
        if package.platform != self.platform:
            raise ValueError(
                f"Publish package platform mismatch: {package.platform} != {self.platform}"
            )

        context = await self.runtime.launch_persistent_context(self.platform)
        await call_if_available(context, "open_creator_page")

        logged_in = await call_if_available(context, "is_logged_in", default=False)
        label = PLATFORM_LABELS[self.platform]
        if not logged_in:
            return PublishResult(
                status=PublishStatus.LOGIN_REQUIRED,
                platform=self.platform,
                message=f"请先在发布助手浏览器中登录{label}创作平台。登录后重新打开发布助手即可自动填充。",
            )

        filled_fields: list[str] = []
        uploaded_video = await call_if_available(context, "upload_video", package.video_path)
        if uploaded_video is not False:
            filled_fields.append("video")

        if package.title:
            title_filled = await call_if_available(context, "fill_title", package.title)
            if title_filled is not False:
                filled_fields.append("title")
        if package.description:
            description_filled = await call_if_available(
                context, "fill_description", package.description
            )
            if description_filled is not False:
                filled_fields.append("description")
        if package.hashtags:
            hashtags_filled = await call_if_available(context, "fill_hashtags", package.hashtags)
            if hashtags_filled is not False:
                filled_fields.append("hashtags")
        if package.cover_path:
            cover_uploaded = await call_if_available(context, "upload_cover", package.cover_path)
            if cover_uploaded is not False:
                filled_fields.append("cover")

        await call_if_available(context, "wait_until_draft_ready")
        draft_url = await call_if_available(context, "current_url", default="")
        return PublishResult(
            status=PublishStatus.DRAFT_READY,
            platform=self.platform,
            message=f"{label}发布信息已自动填充，请在浏览器中检查预览，并由你亲自点击最终发布。",
            draft_url=str(draft_url or ""),
            requires_human_confirmation=True,
            filled_fields=filled_fields,
        )


async def call_if_available(target: Any, method_name: str, *args: Any, default: Any = None) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        return default
    result = method(*args)
    if inspect.isawaitable(result):
        return await result
    return result
