"""Versioned, non-secret creator-platform adapter profiles.

Kept outside the ``platforms`` package so the browser runtime can import the
profiles without triggering the adapter package's public re-exports.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformAdapterProfile:
    platform: str
    label: str
    adapter_version: str
    entry_url: str
    login_markers: tuple[str, ...]
    signed_out_markers: tuple[str, ...]
    editor_markers: tuple[str, ...]
    title_selectors: tuple[str, ...]
    description_selectors: tuple[str, ...]
    video_input_selectors: tuple[str, ...]
    cover_input_selectors: tuple[str, ...]
    media_identity_selectors: tuple[str, ...]
    cover_preview_selectors: tuple[str, ...]
    supports_topic_entities: bool
    required_fields: tuple[str, ...]
    unsupported_fields: tuple[str, ...] = ()
    cover_receipt_boundary: str | None = None
    media_identity_required: bool = True
    media_identity_boundary: str | None = None


PLATFORM_ADAPTER_PROFILES: dict[str, PlatformAdapterProfile] = {
    "kuaishou": PlatformAdapterProfile(
        platform="kuaishou",
        label="快手",
        adapter_version="kuaishou-video@1",
        # tabType=1 is the regular video editor. tabType=3 opens the VR360
        # panorama editor and would silently change the draft mode on restart.
        entry_url="https://cp.kuaishou.com/article/publish/video?tabType=1",
        login_markers=("扫码登录", "手机号登录", "请登录", "立即登录"),
        signed_out_markers=("扫码登录", "手机号登录", "请登录", "立即登录"),
        editor_markers=("作品描述", "上传视频", "发布视频"),
        title_selectors=("input[placeholder*='标题']", "textarea[placeholder*='标题']"),
        description_selectors=(
            "textarea[placeholder*='作品描述']",
            "textarea[placeholder*='描述']",
            "div[contenteditable='true']",
            "textarea",
        ),
        video_input_selectors=("input[type='file'][accept*='video']", "input[type='file'][accept*='.mp4']"),
        cover_input_selectors=("input[type='file'][accept*='image']", "input[type='file'][accept*='.jpg']", "input[type='file'][accept*='.png']"),
        media_identity_selectors=(
            "[data-media-id]",
            "[data-video-id]",
            "video[data-id]",
            "[data-testid='video-preview'][data-id]",
        ),
        cover_preview_selectors=(
            "[data-testid='cover-preview'] img",
            "[data-cover-url]",
            "[data-testid*='cover'] img",
            "div[class*='default-cover'] img",
        ),
        supports_topic_entities=False,
        # Kuaishou's current regular-video editor exposes only 作品描述; it
        # has no independent title input. Keep this as an explicit capability
        # boundary instead of reporting a fabricated title readback.
        required_fields=("video", "description", "hashtags", "cover"),
        unsupported_fields=("title",),
        cover_receipt_boundary="KUAISHOU_LOCAL_BLOB_PREVIEW_ONLY",
    ),
    "shipinhao": PlatformAdapterProfile(
        platform="shipinhao",
        label="视频号",
        adapter_version="shipinhao-video@1",
        entry_url="https://channels.weixin.qq.com/platform/post/create",
        login_markers=("扫码登录", "微信登录", "请登录"),
        signed_out_markers=("扫码登录", "微信登录", "请登录"),
        editor_markers=("发表视频", "上传视频", "视频号助手"),
        title_selectors=("input[placeholder*='标题']", "textarea[placeholder*='标题']"),
        description_selectors=(
            "div[contenteditable][data-placeholder*='描述']",
            "div.post-desc-box .input-editor",
            "textarea[placeholder*='描述']",
            "textarea[placeholder*='文案']",
            "div[contenteditable='true']",
            "textarea",
        ),
        video_input_selectors=("input[type='file'][accept*='video']", "input[type='file'][accept*='.mp4']"),
        cover_input_selectors=("input[type='file'][accept*='image']", "input[type='file'][accept*='.jpg']", "input[type='file'][accept*='.png']"),
        media_identity_selectors=(
            "[data-media-id]",
            "[data-video-id]",
            "video[data-id]",
            "[data-testid='video-preview'][data-id]",
        ),
        cover_preview_selectors=(
            "[data-testid='cover-preview'] img",
            "[data-cover-url]",
            "[data-testid*='cover'] img",
            ".cover-preview-wrap img",
            "img.cover-img-vertical",
        ),
        supports_topic_entities=False,
        required_fields=("video", "title", "description", "cover"),
        media_identity_required=False,
        media_identity_boundary="SHIPINHAO_NO_STABLE_REMOTE_MEDIA_ID",
    ),
    "xiaohongshu": PlatformAdapterProfile(
        platform="xiaohongshu",
        label="小红书",
        adapter_version="xiaohongshu-video@1",
        entry_url="https://creator.xiaohongshu.com/publish/publish?source=official",
        login_markers=("扫码登录", "手机号登录", "请登录"),
        signed_out_markers=("扫码登录", "手机号登录", "请登录"),
        editor_markers=("发布笔记", "上传视频", "标题"),
        title_selectors=("input[placeholder*='标题']", "textarea[placeholder*='标题']"),
        description_selectors=(
            "div[contenteditable='true'][data-placeholder*='正文']",
            "div[contenteditable='true'][data-placeholder*='描述']",
            "div[contenteditable='true'][role='textbox']",
            "textarea[placeholder*='正文']",
            "textarea",
        ),
        video_input_selectors=("input[type='file'][accept*='video']", "input[type='file'][accept*='.mp4']"),
        cover_input_selectors=("input[type='file'][accept*='image']", "input[type='file'][accept*='.jpg']", "input[type='file'][accept*='.png']"),
        media_identity_selectors=(
            "[data-media-id]",
            "[data-video-id]",
            "video[data-id]",
            "[data-testid='video-preview'][data-id]",
        ),
        cover_preview_selectors=(
            "[data-testid='cover-preview'] img",
            "[data-cover-url]",
            "[data-testid*='cover'] img",
        ),
        supports_topic_entities=False,
        required_fields=("video", "title", "description", "hashtags", "cover"),
        cover_receipt_boundary="XIAOHONGSHU_LOCAL_BLOB_PREVIEW_ONLY",
        media_identity_required=False,
        media_identity_boundary="XIAOHONGSHU_NO_STABLE_REMOTE_MEDIA_ID",
    ),
}

PLATFORM_ADAPTER_ALIASES = {"video_channel": "shipinhao"}


def canonical_platform(platform: str) -> str:
    return PLATFORM_ADAPTER_ALIASES.get(platform, platform)


def get_platform_profile(platform: str) -> PlatformAdapterProfile:
    try:
        return PLATFORM_ADAPTER_PROFILES[canonical_platform(platform)]
    except KeyError as exc:
        raise ValueError(f"Unsupported platform adapter profile: {platform}") from exc
