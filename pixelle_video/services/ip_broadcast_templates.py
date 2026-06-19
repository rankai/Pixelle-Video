"""IP broadcast visual template registry and rendering helpers."""

import re
from dataclasses import dataclass, replace
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
    default_background_path: str
    subtitle_style: SubtitleStyle


_TEMPLATE_ROOT = Path("templates/ip_broadcast/1080x1920")

_TEMPLATES = [
    IPBroadcastTemplate(
        template_id="boss_clean",
        display_name="干净商务风",
        short_description="标题居中偏上，字幕清爽靠下。",
        full_description="封面标题居中偏上，整体留白更克制；字幕位于画面下方，描边较轻，适合日常知识分享、品牌介绍和稳重口播。",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_clean_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_clean_preview.jpg"),
        default_background_path=str(_TEMPLATE_ROOT / "assets/boss_clean_bg.jpg"),
        subtitle_style=SubtitleStyle(font_size=28, outline=2, margin_v=180),
    ),
    IPBroadcastTemplate(
        template_id="boss_authority",
        display_name="强观点标题风",
        short_description="顶部强标题，字幕突出观点节奏。",
        full_description="封面顶部大标题强化观点；字幕字号更大、描边更重，适合金句、观点输出和强转化口播。",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_authority_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_authority_preview.jpg"),
        default_background_path=str(_TEMPLATE_ROOT / "assets/boss_authority_bg.jpg"),
        subtitle_style=SubtitleStyle(font_size=30, outline=3, shadow=0, margin_v=190),
    ),
    IPBroadcastTemplate(
        template_id="boss_premium",
        display_name="高级深色访谈风",
        short_description="深色质感标题，暖色字幕更稳。",
        full_description="封面采用深色访谈质感和低调标题层级；字幕使用暖色主色，适合高客单、咨询服务和专业人设内容。",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_premium_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_premium_preview.jpg"),
        default_background_path=str(_TEMPLATE_ROOT / "assets/boss_premium_bg.jpg"),
        subtitle_style=SubtitleStyle(
            font_size=28,
            primary_colour="&H00F7E7B2",
            outline_colour="&HAA101010",
            back_colour="&H77101010",
            outline=2,
            margin_v=180,
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


_SUBTITLE_STYLE_LIMITS = {
    "font_size": (16, 72),
    "margin_v": (0, 500),
}


def _merge_subtitle_style(
    style: SubtitleStyle,
    overrides: dict[str, Any] | None = None,
) -> SubtitleStyle:
    if not isinstance(overrides, dict):
        return style
    sanitized: dict[str, int] = {}
    for key, (minimum, maximum) in _SUBTITLE_STYLE_LIMITS.items():
        if key not in overrides:
            continue
        try:
            value = int(overrides[key])
        except (TypeError, ValueError):
            continue
        sanitized[key] = max(minimum, min(maximum, value))
    if not sanitized:
        return style
    return replace(style, **sanitized)


def _css_block(html: str, selector: str) -> str:
    match = re.search(rf"{re.escape(selector)}\s*\{{(?P<body>.*?)\}}", html, re.S)
    return match.group("body") if match else ""


def _css_px(block: str, property_name: str) -> int | None:
    match = re.search(rf"{property_name}\s*:\s*(?P<value>\d+(?:\.\d+)?)px", block)
    if not match:
        return None
    return round(float(match.group("value")))


def _css_value(block: str, property_name: str) -> str:
    match = re.search(rf"{property_name}\s*:\s*(?P<value>[^;]+)", block)
    return match.group("value").strip() if match else ""


def _css_color_to_ass(value: str) -> str | None:
    value = value.strip().lower()
    named = {
        "white": "#ffffff",
        "black": "#000000",
    }
    value = named.get(value, value)
    if re.fullmatch(r"#[0-9a-f]{3}", value):
        value = "#" + "".join(ch * 2 for ch in value[1:])
    if not re.fullmatch(r"#[0-9a-f]{6}", value):
        return None
    red = value[1:3].upper()
    green = value[3:5].upper()
    blue = value[5:7].upper()
    return f"&H00{blue}{green}{red}"


def _canvas_height_from_html(html: str) -> int:
    return _css_px(_css_block(html, "body"), "height") or 1920


def _scale_template_px(value: int, template_height: int, video_height: int | None) -> int:
    if not video_height or video_height == template_height:
        return value
    return max(1, round(value * video_height / template_height))


def get_template_subtitle_style(
    template: IPBroadcastTemplate,
    video_height: int | None = None,
) -> SubtitleStyle:
    fallback = template.subtitle_style
    html = Path(template.cover_template_path).read_text(encoding="utf-8")
    template_height = _canvas_height_from_html(html)
    subtitle_block = _css_block(html, ".subtitle")
    panel_block = _css_block(html, ".panel")
    font_size = _css_px(subtitle_block, "font-size") or fallback.font_size
    bottom = (
        _css_px(subtitle_block, "bottom")
        or _css_px(panel_block, "bottom")
        or fallback.margin_v
    )
    primary_colour = _css_color_to_ass(_css_value(subtitle_block, "color")) or fallback.primary_colour
    return replace(
        fallback,
        font_size=_scale_template_px(font_size, template_height, video_height),
        primary_colour=primary_colour,
        margin_v=_scale_template_px(bottom, template_height, video_height),
    )


def build_ass_force_style(
    template: IPBroadcastTemplate,
    overrides: dict[str, Any] | None = None,
    video_height: int | None = None,
) -> str:
    style = _merge_subtitle_style(
        get_template_subtitle_style(template, video_height),
        overrides,
    )
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
    background = background or template.default_background_path
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
