"""IP broadcast visual template registry and rendering helpers."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pixelle_video.services.frame_html import HTMLFrameGenerator
from pixelle_video.utils.os_util import get_temp_path


@dataclass(frozen=True)
class SubtitleStyle:
    font_name: str = "Noto Sans CJK SC"
    font_size: int = 48
    primary_colour: str = "&H00FFFFFF"
    outline_colour: str = "&H99000000"
    back_colour: str = "&H66000000"
    bold: int = 1
    outline: int = 3
    shadow: int = 1
    alignment: int = 2
    margin_l: int = 70
    margin_r: int = 70
    margin_v: int = 170


@dataclass(frozen=True)
class IPBroadcastTemplate:
    template_id: str
    display_name: str
    short_description: str
    full_description: str
    cover_template_path: str
    preview_image_path: str
    subtitle_style: SubtitleStyle


_TEMPLATE_ROOT = Path("templates/ip_broadcast/1080x1920")

_TEMPLATES = [
    IPBroadcastTemplate(
        template_id="boss_clean",
        display_name="干净商务风",
        short_description="标题居中偏上，字幕清爽靠下。",
        full_description="封面标题居中偏上，整体留白更克制；字幕位于画面下方，描边较轻，适合日常知识分享、品牌介绍和稳重口播。",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_clean_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_clean_preview.png"),
        subtitle_style=SubtitleStyle(font_size=34, outline=2, margin_v=210),
    ),
    IPBroadcastTemplate(
        template_id="boss_authority",
        display_name="强观点标题风",
        short_description="顶部强标题，字幕突出观点节奏。",
        full_description="封面顶部大标题强化观点；字幕字号更大、描边更重，适合金句、观点输出和强转化口播。",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_authority_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_authority_preview.png"),
        subtitle_style=SubtitleStyle(font_size=36, outline=3, shadow=0, margin_v=220),
    ),
    IPBroadcastTemplate(
        template_id="boss_premium",
        display_name="高级深色访谈风",
        short_description="深色质感标题，暖色字幕更稳。",
        full_description="封面采用深色访谈质感和低调标题层级；字幕使用暖色主色，适合高客单、咨询服务和专业人设内容。",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_premium_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_premium_preview.png"),
        subtitle_style=SubtitleStyle(
            font_size=34,
            primary_colour="&H00F7E7B2",
            outline_colour="&HAA101010",
            back_colour="&H77101010",
            outline=2,
            margin_v=210,
        ),
    ),
]


def list_ip_broadcast_templates() -> list[IPBroadcastTemplate]:
    return list(_TEMPLATES)


def get_ip_broadcast_template(template_id: str | None) -> IPBroadcastTemplate:
    for template in _TEMPLATES:
        if template.template_id == template_id:
            return template
    return _TEMPLATES[0]


def build_ass_force_style(template: IPBroadcastTemplate) -> str:
    style = template.subtitle_style
    parts = {
        "FontName": style.font_name,
        "Fontsize": style.font_size,
        "PrimaryColour": style.primary_colour,
        "OutlineColour": style.outline_colour,
        "BackColour": style.back_colour,
        "Bold": style.bold,
        "Outline": style.outline,
        "Shadow": style.shadow,
        "Alignment": style.alignment,
        "MarginL": style.margin_l,
        "MarginR": style.margin_r,
        "MarginV": style.margin_v,
        "BorderStyle": 3,
    }
    return ",".join(f"{key}={value}" for key, value in parts.items())


async def render_ip_broadcast_cover(
    template_id: str | None,
    title: str,
    subtitle: str = "",
    background: str = "",
    output_path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    template = get_ip_broadcast_template(template_id)
    output_path = output_path or get_temp_path(f"ipb_cover_{template.template_id}.png")
    generator = HTMLFrameGenerator(template.cover_template_path)
    if background and not background.startswith(("http://", "https://", "data:", "file://")):
        background_path = Path(background)
        if background_path.exists():
            background = background_path.resolve().as_uri()
    ext = {"subtitle": subtitle, "background": background}
    if extra:
        ext.update(extra)
    return await generator.generate_frame(
        title=title,
        text=subtitle,
        image=background,
        ext=ext,
        output_path=output_path,
    )
