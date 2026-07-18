"""Desktop publishing assistant endpoints."""

from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.desktop_security import is_desktop_mode
from api.tasks import TaskType, task_manager
from pixelle_video.services.publish.browser_runtime import PlaywrightBrowserRuntime
from pixelle_video.services.publish.models import PublishPackage, PublishResult, PublishStatus
from pixelle_video.services.publish.platforms.base import PLATFORM_LABELS, HumanConfirmedPublisher
from pixelle_video.services.publish.platforms.douyin import DouyinPublisher
from pixelle_video.services.publish.platforms.multiplatform import (
    KuaishouPublisher,
    ShipinhaoPublisher,
    XiaohongshuPublisher,
)

router = APIRouter(prefix="/publish", tags=["Publish"])


def get_douyin_publisher() -> DouyinPublisher:
    return DouyinPublisher(PlaywrightBrowserRuntime())


def get_platform_publisher(platform: str) -> HumanConfirmedPublisher:
    publisher_types = {
        "douyin": DouyinPublisher,
        "xiaohongshu": XiaohongshuPublisher,
        "shipinhao": ShipinhaoPublisher,
        "kuaishou": KuaishouPublisher,
    }
    publisher_type = publisher_types.get(platform)
    if not publisher_type:
        raise HTTPException(status_code=404, detail="暂不支持该发布平台。")
    return publisher_type(PlaywrightBrowserRuntime())


@router.post("/douyin/prepare", response_model=PublishResult)
async def prepare_douyin_publish(package: PublishPackage):
    if package.platform != "douyin":
        raise HTTPException(status_code=400, detail="发布平台与接口不匹配。")
    return await _prepare_platform_publish(package, publisher=get_douyin_publisher())


@router.post("/{platform}/prepare", response_model=PublishResult)
async def prepare_platform_publish(platform: str, package: PublishPackage):
    if platform != package.platform:
        raise HTTPException(status_code=400, detail="发布平台与接口不匹配。")
    return await _prepare_platform_publish(package, publisher=get_platform_publisher(platform))


async def _prepare_platform_publish(package: PublishPackage, publisher: HumanConfirmedPublisher):
    if not is_desktop_mode():
        raise HTTPException(
            status_code=403, detail="发布助手仅支持桌面端本地运行，服务器端不执行自动发布。"
        )

    _validate_publish_file_path(package.video_path)
    if package.cover_path:
        _validate_publish_file_path(package.cover_path)

    platform_label = PLATFORM_LABELS[package.platform]
    task = task_manager.create_task(
        task_type=TaskType.PUBLISH_ASSISTANT,
        request_params=package.model_dump(),
        display_name=f"{platform_label}发布助手",
        flow_name="短视频发布",
        step_key="publish",
        session_id=package.session_id,
        artifact_keys=["final_video"],
        retry_payload={"kind": f"publish_{package.platform}", "package": package.model_dump()},
    )
    task_manager.update_progress(task.task_id, 1, 3, f"正在打开{platform_label}发布助手。")
    try:
        raw_result = await publisher.prepare_draft(package)
        result = (
            raw_result
            if isinstance(raw_result, PublishResult)
            else PublishResult.model_validate(raw_result)
        )
    except Exception as exc:
        result = PublishResult(
            status=PublishStatus.FAILED,
            platform=package.platform,
            message=_publish_error_message(exc),
            task_id=task.task_id,
        )
        task_manager.fail_task(task.task_id, result.message, result.model_dump(mode="json"))
        return result
    result.task_id = task.task_id
    result.requires_human_confirmation = True
    if result.status == PublishStatus.FAILED:
        task_manager.fail_task(task.task_id, result.message, result.model_dump(mode="json"))
    else:
        task_manager.update_progress(task.task_id, 3, 3, result.message or "发布助手任务完成。")
        task_manager.complete_task(task.task_id, result.model_dump(mode="json"))
    return result


def _validate_publish_file_path(path_value: str) -> None:
    path = Path(path_value).expanduser().resolve()
    allowed_roots = [
        Path.cwd() / "output",
        Path.cwd() / "temp",
        Path.cwd() / "data",
        Path("/tmp"),
        Path("/private/tmp"),
    ]
    for root in allowed_roots:
        try:
            path.relative_to(root.resolve())
            return
        except ValueError:
            continue
    raise HTTPException(
        status_code=403, detail="不允许发布该文件路径，请使用当前任务生成的视频或素材库文件。"
    )


def _publish_error_message(error: Exception) -> str:
    message = str(error)
    lowered = message.lower()
    if "timeout" in lowered or "exceeded" in lowered:
        return "发布页面响应超时，请确认网络正常并重新打开发布助手。"
    if "locator" in lowered or "selector" in lowered or "input[type='file']" in lowered:
        return "没有找到发布页面的上传入口，可能是平台页面已变化，请更新发布适配。"
    if "login" in lowered or "登录" in message:
        return "请先在发布助手浏览器中登录平台账号。"
    if "permission" in lowered or "denied" in lowered:
        return "发布助手没有读取该文件的权限，请检查文件位置或重新生成视频。"
    return "发布助手执行失败，请重新打开发布窗口后再试。"
