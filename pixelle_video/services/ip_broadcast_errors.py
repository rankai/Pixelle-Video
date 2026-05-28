"""Business-facing error messages for IP broadcast steps."""

from dataclasses import dataclass


@dataclass(frozen=True)
class BusinessError:
    user_message: str
    technical_message: str
    category: str
    retryable: bool
    next_action: str


def classify_ip_broadcast_error(error: Exception) -> BusinessError:
    technical = str(error)
    lower = technical.lower()
    if "401" in lower or "unauthorized" in lower:
        return BusinessError(
            user_message="RunningHub Key 无效或无权限，请到配置中心检查。",
            technical_message=technical,
            category="auth",
            retryable=False,
            next_action="打开配置中心，确认 RunningHub API Key 和工作流权限。",
        )
    if "403" in lower or "forbidden" in lower:
        return BusinessError(
            user_message="当前账号没有该工作流权限，请检查 RunningHub 权限。",
            technical_message=technical,
            category="auth",
            retryable=False,
            next_action="确认工作流已发布，并且当前 API Key 有调用权限。",
        )
    if "timeout" in lower or "timed out" in lower:
        return BusinessError(
            user_message="远程生成超时，可以稍后重试或检查 RunningHub 后台任务状态。",
            technical_message=technical,
            category="timeout",
            retryable=True,
            next_action="稍后重试当前步骤。",
        )
    if "workflow file does not exist" in lower or "workflow" in lower and "not found" in lower:
        return BusinessError(
            user_message="工作流配置不存在，请检查当前选择的工作流。",
            technical_message=technical,
            category="workflow",
            retryable=False,
            next_action="回到当前步骤选择可用工作流。",
        )
    if "只支持图片形象" in technical or "只支持视频形象" in technical:
        return BusinessError(
            user_message=technical,
            technical_message=technical,
            category="asset_type",
            retryable=False,
            next_action="请在形象库选择匹配类型的形象素材。",
        )
    if "ffmpeg" in lower or "subprocess" in lower:
        return BusinessError(
            user_message="视频合成失败，请检查素材格式或查看技术详情。",
            technical_message=technical,
            category="composition",
            retryable=True,
            next_action="更换素材后重试一键成片。",
        )
    return BusinessError(
        user_message=technical or "步骤执行失败。",
        technical_message=technical,
        category="unknown",
        retryable=True,
        next_action="检查输入后重试当前步骤。",
    )
