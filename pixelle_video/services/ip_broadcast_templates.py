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
    cover_template_path: str
    preview_image_path: str
    subtitle_style: SubtitleStyle


_TEMPLATE_ROOT = Path("templates/ip_broadcast/1080x1920")

_TEMPLATES = [
    IPBroadcastTemplate(
        template_id="boss_clean",
        display_name="干净商务风",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_clean_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_clean_preview.png"),
        subtitle_style=SubtitleStyle(font_size=46, outline=2, margin_v=155),
    ),
    IPBroadcastTemplate(
        template_id="boss_authority",
        display_name="强观点标题风",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_authority_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_authority_preview.png"),
        subtitle_style=SubtitleStyle(font_size=54, outline=4, shadow=0, margin_v=135),
    ),
    IPBroadcastTemplate(
        template_id="boss_premium",
        display_name="高级深色访谈风",
        cover_template_path=str(_TEMPLATE_ROOT / "boss_premium_cover.html"),
        preview_image_path=str(_TEMPLATE_ROOT / "boss_premium_preview.png"),
        subtitle_style=SubtitleStyle(
            font_size=48,
            primary_colour="&H00F7E7B2",
            outline_colour="&HAA101010",
            back_colour="&H77101010",
            outline=3,
            margin_v=165,
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
