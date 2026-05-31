"""Desktop publishing assistant endpoints."""

from fastapi import APIRouter

from pixelle_video.services.publish.browser_runtime import PlaywrightBrowserRuntime
from pixelle_video.services.publish.models import PublishPackage, PublishResult, PublishStatus
from pixelle_video.services.publish.platforms.douyin import DouyinPublisher

router = APIRouter(prefix="/publish", tags=["Publish"])


def get_douyin_publisher() -> DouyinPublisher:
    return DouyinPublisher(PlaywrightBrowserRuntime())


@router.post("/douyin/prepare", response_model=PublishResult)
async def prepare_douyin_publish(package: PublishPackage):
    publisher = get_douyin_publisher()
    try:
        result = await publisher.prepare_draft(package)
    except Exception as exc:
        return PublishResult(
            status=PublishStatus.FAILED,
            platform="douyin",
            message=f"发布助手启动失败：{exc}",
        )
    return result
