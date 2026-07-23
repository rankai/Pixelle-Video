"""Platform adapter factory used by legacy and V2 publishing paths."""

from pathlib import Path
from typing import Any

from pixelle_video.services.publish.browser_runtime import BrowserRuntime
from pixelle_video.services.publish.platform_profiles import canonical_platform
from pixelle_video.services.publish.platforms.base import HumanConfirmedPublisher
from pixelle_video.services.publish.platforms.douyin import DouyinPublisher
from pixelle_video.services.publish.platforms.multiplatform import (
    KuaishouPublisher,
    ShipinhaoPublisher,
    XiaohongshuPublisher,
)


def create_platform_publisher(
    platform: str,
    runtime: BrowserRuntime,
    *,
    profile_path: str | Path | None = None,
    account_id: str | None = None,
    **douyin_options: Any,
) -> HumanConfirmedPublisher:
    canonical = canonical_platform(platform)
    if canonical == "douyin":
        return DouyinPublisher(
            runtime,
            profile_path=profile_path,
            account_id=account_id,
            **douyin_options,
        )
    publisher_type = {
        "kuaishou": KuaishouPublisher,
        "shipinhao": ShipinhaoPublisher,
        "xiaohongshu": XiaohongshuPublisher,
    }.get(canonical)
    if publisher_type is None:
        raise ValueError(f"Unsupported publish platform: {platform}")
    return publisher_type(
        runtime,
        profile_path=profile_path,
        account_id=account_id,
        profile_ref=douyin_options.get("profile_ref"),
        checkpoint=douyin_options.get("checkpoint"),
        checkpoint_callback=douyin_options.get("checkpoint_callback"),
    )
