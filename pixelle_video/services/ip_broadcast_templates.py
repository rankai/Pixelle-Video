"""IP broadcast visual template registry and rendering helpers."""

import json
import logging
import os
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PIL import Image, ImageDraw, ImageFont, ImageOps

from pixelle_video.services.font_registry import resolve_font_path, resolve_registered_font
from pixelle_video.services.frame_html import HTMLFrameGenerator
from pixelle_video.utils.os_util import get_temp_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubtitleStyle:
    # The bundled registry font is used by Chromium, PIL and libass.
    font_name: str = "Noto Sans CJK SC"
    font_size: int = 48
    primary_colour: str = "&H00FFFFFF"
    outline_colour: str = "&H99000000"
    back_colour: str = "&H66000000"
    bold: int = 0
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
    layout_contract: dict[str, Any] | None = None


_TEMPLATE_ROOT = Path("templates/ip_broadcast/1080x1920")
IP_BROADCAST_CANVAS_WIDTH = 1080
IP_BROADCAST_CANVAS_HEIGHT = 1920

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


def get_ip_broadcast_template_for_render(template_id: str | None) -> IPBroadcastTemplate:
    """Resolve built-in or SQLite-backed template contracts for rendering.

    Custom V2 templates intentionally reuse a registered HTML base template;
    their versioned subtitle contract is applied on top.  This keeps preview
    and final ASS rendering on one canvas while refusing to silently invent a
    renderer for arbitrary user data.
    """
    template = get_ip_broadcast_template(template_id)
    if not template_id or template.template_id == template_id:
        return template
    try:
        from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

        row = AssetLibraryRepository().get_template_revision(str(template_id))
        if not row:
            return template
        cover_contract = json.loads(row.get("cover_contract_json") or "{}")
        subtitle_contract = json.loads(row.get("subtitle_contract_json") or "{}")
        layout_contract = json.loads(row.get("layout_contract_json") or "{}")
        base = get_ip_broadcast_template(
            str(cover_contract.get("base_template_id") or "boss_clean")
        )
        base_style = get_template_subtitle_style(base)
        if layout_contract.get("video_subtitle"):
            layout_style = layout_contract["video_subtitle"]
            font_token = str(layout_style.get("font_token") or "")
            font = next(
                (item for item in layout_contract.get("fonts", []) if item.get("token") == font_token),
                {},
            )
            subtitle_contract = {
                **subtitle_contract,
                "font_size": layout_style.get("font_size"),
                "margin_l": layout_style.get("margin_l"),
                "margin_r": layout_style.get("margin_r"),
                "margin_v": layout_style.get("margin_v"),
                "outline": layout_style.get("outline"),
                "shadow": layout_style.get("shadow"),
                "font_name": font.get("family"),
            }
        style_updates = {
            key: value
            for key, value in subtitle_contract.items()
            if key in SubtitleStyle.__dataclass_fields__
        }
        style = replace(base_style, **style_updates) if style_updates else base_style
        return replace(
            base,
            template_id=str(template_id),
            display_name=str(row.get("display_name") or base.display_name),
            short_description=str(row.get("short_description") or base.short_description),
            full_description=str(row.get("full_description") or base.full_description),
            subtitle_style=style,
            layout_contract=layout_contract or None,
        )
    except (OSError, RuntimeError, ValueError, TypeError, json.JSONDecodeError):
        return template


def resolve_ip_broadcast_fonts_dir() -> str | None:
    """Return a font directory visible to both Chromium and libass."""
    bundled = resolve_font_path("noto-sans-sc-bold")
    if bundled:
        return str(bundled.parent)
    configured = str(os.getenv("PIXELLE_VIDEO_FONT_DIR") or "").strip()
    candidates = [
        configured,
        "/System/Library/Fonts",
        "/Library/Fonts",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/noto",
        "/usr/local/share/fonts",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return str(Path(candidate).resolve())
    return None


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
        _css_px(subtitle_block, "bottom") or _css_px(panel_block, "bottom") or fallback.margin_v
    )
    primary_colour = (
        _css_color_to_ass(_css_value(subtitle_block, "color")) or fallback.primary_colour
    )
    return replace(
        fallback,
        font_size=_scale_template_px(font_size, template_height, video_height),
        primary_colour=primary_colour,
        margin_v=_scale_template_px(bottom, template_height, video_height),
    )


def build_ass_force_style(
    template: IPBroadcastTemplate,
    overrides: dict[str, Any] | None = None,
    video_width: int | None = None,
    video_height: int | None = None,
) -> str:
    built_in_ids = {item.template_id for item in _TEMPLATES}
    if template.template_id in built_in_ids:
        resolved_style = get_template_subtitle_style(template, video_height)
    else:
        resolved_style = template.subtitle_style
        if video_height:
            resolved_style = replace(
                resolved_style,
                font_size=_scale_template_px(
                    resolved_style.font_size, IP_BROADCAST_CANVAS_HEIGHT, video_height
                ),
                margin_v=_scale_template_px(
                    resolved_style.margin_v, IP_BROADCAST_CANVAS_HEIGHT, video_height
                ),
            )
    if video_width and video_width != IP_BROADCAST_CANVAS_WIDTH:
        resolved_style = replace(
            resolved_style,
            margin_l=_scale_template_px(resolved_style.margin_l, IP_BROADCAST_CANVAS_WIDTH, video_width),
            margin_r=_scale_template_px(resolved_style.margin_r, IP_BROADCAST_CANVAS_WIDTH, video_width),
        )
    style = _merge_subtitle_style(resolved_style, overrides)
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


def _css_rgba(value: str, fallback: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    """Parse the small CSS colour subset used by the built-in cover contracts."""
    value = value.strip().lower()
    named = {"white": "#ffffff", "black": "#000000"}
    value = named.get(value, value)
    rgba = re.fullmatch(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)(?:\s*,\s*([\d.]+))?\s*\)",
        value,
    )
    if rgba:
        alpha = float(rgba.group(4) or 1)
        return (
            int(rgba.group(1)),
            int(rgba.group(2)),
            int(rgba.group(3)),
            round(max(0, min(1, alpha)) * 255),
        )
    if re.fullmatch(r"#[0-9a-f]{3,8}", value):
        raw = value[1:]
        if len(raw) in {3, 4}:
            raw = "".join(ch * 2 for ch in raw)
        if len(raw) == 6:
            raw += "ff"
        return tuple(int(raw[index : index + 2], 16) for index in range(0, 8, 2))  # type: ignore[return-value]
    return fallback


def _font_candidates(bold: bool = False) -> list[str]:
    bundled = resolve_font_path("noto-sans-sc-bold")
    configured_dir = resolve_ip_broadcast_fonts_dir()
    names = (
        ["PingFang.ttc", "Hiragino Sans GB.ttc", "STHeiti Light.ttc"]
        if not bold
        else ["PingFang.ttc", "Hiragino Sans GB.ttc", "STHeiti Medium.ttc", "STHeiti Light.ttc"]
    )
    roots = [
        configured_dir,
        "/System/Library/Fonts",
        "/Library/Fonts",
        "/usr/share/fonts/opentype/noto",
        "/usr/share/fonts/truetype/noto",
    ]
    candidates = ([str(bundled)] if bundled else []) + [str(Path(root) / name) for root in roots if root for name in names]
    candidates.extend(
        [
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        ]
    )
    return candidates


def _load_cover_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in _font_candidates(bold):
        try:
            if Path(candidate).is_file():
                return ImageFont.truetype(candidate, size=size)
        except (OSError, ValueError):
            continue
    return ImageFont.load_default()


def _wrap_cover_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int | None = None,
) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text or "").splitlines() or [""]:
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and draw.textlength(candidate, font=font) > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        if lines and len(lines[-1]) > 1:
            lines[-1] = lines[-1][:-1] + "…"
    return lines


def _draw_cover_text(
    draw: ImageDraw.ImageDraw,
    lines: list[str],
    xy: tuple[int, int],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int],
    line_height: int,
    shadow: bool = True,
    stroke_width: int = 0,
) -> None:
    x, y = xy
    for line in lines:
        if shadow:
            draw.text(
                (x + 3, y + 5),
                line,
                font=font,
                fill=(0, 0, 0, 150),
                stroke_width=stroke_width,
                stroke_fill=(0, 0, 0, 100),
            )
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
            stroke_width=stroke_width,
            stroke_fill=(0, 0, 0, 120),
        )
        y += line_height


def _local_background_path(background: str, template: IPBroadcastTemplate) -> Path | None:
    candidates: list[str] = []
    if background.startswith("file://"):
        candidates.append(unquote(urlparse(background).path))
    elif background and not background.startswith(("http://", "https://", "data:")):
        candidates.append(background)
    candidates.extend([template.default_background_path, template.preview_image_path])
    for candidate in candidates:
        path = Path(candidate)
        if path.is_file():
            return path
    return None


def _render_cover_fallback(
    template: IPBroadcastTemplate,
    title: str,
    subtitle: str,
    background: str,
    output_path: str,
) -> str:
    """Render a self-contained cover when packaged Playwright has no browser.

    The fallback intentionally reads the same HTML contract as the browser
    renderer (canvas, positions, padding and font sizes). This keeps the
    cover usable in a frozen desktop build without silently changing the
    subtitle/cover coordinate system.
    """
    html = Path(template.cover_template_path).read_text(encoding="utf-8")
    width = _css_px(_css_block(html, "body"), "width") or IP_BROADCAST_CANVAS_WIDTH
    height = _css_px(_css_block(html, "body"), "height") or IP_BROADCAST_CANVAS_HEIGHT
    source = _local_background_path(background, template)
    try:
        image = (
            Image.open(source).convert("RGB")
            if source
            else Image.new("RGB", (width, height), "#111827")
        )
    except (OSError, ValueError):
        image = Image.new("RGB", (width, height), "#111827")
    canvas = ImageOps.fit(
        image, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5)
    ).convert("RGBA")

    # Match the vertical darkening in the built-in .bg contracts.
    darkness = {
        "boss_clean": (10, 112),
        "boss_authority": (50, 174),
        "boss_premium": (50, 198),
    }.get(template.template_id, (24, 128))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    for row in range(height):
        alpha = round(darkness[0] + (darkness[1] - darkness[0]) * row / max(1, height - 1))
        overlay_draw.line((0, row, width, row), fill=(0, 0, 0, alpha))
    canvas = Image.alpha_composite(canvas, overlay)

    draw = ImageDraw.Draw(canvas, "RGBA")
    title_block = _css_block(html, ".title")
    subtitle_block = _css_block(html, ".subtitle")
    panel_block = _css_block(html, ".panel")

    def box_edges(block: str, default_left: int = 72) -> tuple[int, int]:
        left = _css_px(block, "left") or default_left
        right = _css_px(block, "right") or default_left
        return left, right

    title_left, title_right = box_edges(title_block, 72)
    title_top = _css_px(title_block, "top")
    title_padding_x = _css_px(title_block, "padding") or 0
    title_font_size = _css_px(title_block, "font-size") or 44
    title_font = _load_cover_font(title_font_size, bold=True)
    title_line_height = round(
        title_font_size
        * (
            float((_css_value(title_block, "line-height") or "1.18").replace("px", ""))
            if "px" in _css_value(title_block, "line-height")
            else float(_css_value(title_block, "line-height") or "1.18")
        )
    )
    title_max_height = _css_px(title_block, "max-height") or 420

    if panel_block:
        panel_left, panel_right = box_edges(panel_block, 72)
        panel_bottom = _css_px(panel_block, "bottom") or 340
        panel_height = _css_px(panel_block, "max-height") or 360
        panel_top = height - panel_bottom - panel_height
        panel_padding = _css_px(panel_block, "padding") or 38
        draw.rectangle(
            (panel_left, panel_top, width - panel_right, height - panel_bottom),
            fill=_css_rgba(_css_value(panel_block, "background"), (15, 17, 21, 200)),
            outline=(247, 231, 178, 110),
            width=2,
        )
        title_x = panel_left + panel_padding
        title_y = panel_top + panel_padding
        title_max_width = width - panel_left - panel_right - panel_padding * 2
    else:
        title_x = title_left + title_padding_x
        title_y = title_top or 230
        title_max_width = width - title_left - title_right - title_padding_x * 2
        title_background = _css_value(title_block, "background")
        if title_background:
            radius = _css_px(title_block, "border-radius") or 0
            title_bottom = min(height, title_y + title_max_height)
            draw.rounded_rectangle(
                (title_left, title_y, width - title_right, title_bottom),
                radius=radius,
                fill=_css_rgba(title_background, (17, 24, 39, 86)),
            )
        border = re.search(r"border-left:\s*(\d+)px\s+solid\s+([^;]+)", title_block)
        if border:
            draw.rectangle(
                (
                    title_left,
                    title_y,
                    title_left + int(border.group(1)),
                    min(height, title_y + title_max_height),
                ),
                fill=_css_rgba(border.group(2), (217, 164, 65, 255)),
            )

    title_lines = _wrap_cover_text(
        draw,
        title,
        title_font,
        max(1, title_max_width),
        max(1, title_max_height // max(1, title_line_height)),
    )
    _draw_cover_text(
        draw,
        title_lines,
        (title_x, title_y),
        title_font,
        _css_rgba(_css_value(title_block, "color"), (255, 255, 255, 255)),
        title_line_height,
        stroke_width=1,
    )

    if template.template_id == "boss_authority":
        tag_font = _load_cover_font(26, bold=True)
        draw.rectangle((72, 190, 72 + 156, 190 + 54), fill=(239, 68, 68, 255))
        draw.text((92, 202), "老板观点", font=tag_font, fill=(255, 255, 255, 255))

    if subtitle:
        subtitle_left, subtitle_right = box_edges(subtitle_block, 72)
        subtitle_padding = _css_px(subtitle_block, "padding") or 0
        subtitle_font_size = _css_px(subtitle_block, "font-size") or 26
        subtitle_font = _load_cover_font(subtitle_font_size)
        subtitle_line_height_value = _css_value(subtitle_block, "line-height") or "1.35"
        subtitle_line_height = round(
            subtitle_font_size
            * (
                float(subtitle_line_height_value.replace("px", ""))
                if "px" in subtitle_line_height_value
                else float(subtitle_line_height_value)
            )
        )
        subtitle_bottom = _css_px(subtitle_block, "bottom") or 340
        subtitle_x = subtitle_left + subtitle_padding
        subtitle_y = height - subtitle_bottom - subtitle_padding - subtitle_line_height * 2
        subtitle_max_width = width - subtitle_left - subtitle_right - subtitle_padding * 2
        subtitle_background = _css_value(subtitle_block, "background")
        if subtitle_background:
            subtitle_height = subtitle_line_height * 3 + subtitle_padding * 2
            radius = _css_px(subtitle_block, "border-radius") or 0
            draw.rounded_rectangle(
                (
                    subtitle_left,
                    height - subtitle_bottom - subtitle_height,
                    width - subtitle_right,
                    height - subtitle_bottom,
                ),
                radius=radius,
                fill=_css_rgba(subtitle_background, (17, 24, 39, 92)),
            )
        subtitle_lines = _wrap_cover_text(
            draw, subtitle, subtitle_font, max(1, subtitle_max_width), 3
        )
        if subtitle_lines:
            subtitle_y = (
                height
                - subtitle_bottom
                - subtitle_padding
                - subtitle_line_height * len(subtitle_lines)
            )
            _draw_cover_text(
                draw,
                subtitle_lines,
                (subtitle_x, subtitle_y),
                subtitle_font,
                _css_rgba(_css_value(subtitle_block, "color"), (255, 255, 255, 255)),
                subtitle_line_height,
                stroke_width=0,
            )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(output_path, format="PNG")
    return output_path


def _contract_line_height(font_size: int, value: Any, fallback: float = 1.2) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = fallback
    return max(font_size, round(font_size * numeric)) if numeric < 8 else max(font_size, round(numeric))


def _contract_box_lines(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    box: dict[str, Any],
) -> tuple[list[str], int]:
    line_height = _contract_line_height(int(box.get("font_size") or 32), box.get("line_height"))
    max_lines = int(box.get("max_lines") or 3)
    lines = _wrap_cover_text(draw, text, font, max(1, int(box.get("width") or 1)), max_lines)
    return lines, line_height


def _draw_contract_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: dict[str, Any],
    font: ImageFont.ImageFont,
    fill: tuple[int, int, int, int] = (255, 255, 255, 255),
) -> dict[str, Any]:
    x = int(box.get("x") or 0)
    y = int(box.get("y") or 0)
    width = int(box.get("width") or 1)
    height = int(box.get("height") or 1)
    lines, line_height = _contract_box_lines(draw, text, font, box)
    content_height = line_height * len(lines)
    vertical_align = str(box.get("vertical_align") or "top")
    if vertical_align == "middle":
        y += max(0, (height - content_height) // 2)
    elif vertical_align == "bottom":
        y += max(0, height - content_height)
    align = str(box.get("align") or "left")
    rendered: list[dict[str, int | str]] = []
    for line in lines:
        line_width = int(round(draw.textlength(line, font=font)))
        line_x = x
        if align == "center":
            line_x = x + max(0, (width - line_width) // 2)
        elif align == "right":
            line_x = x + max(0, width - line_width)
        draw.text((line_x, y), line, font=font, fill=fill, stroke_width=1, stroke_fill=(0, 0, 0, 140))
        rendered.append({"text": line, "x": line_x, "y": y, "width": line_width, "height": line_height})
        y += line_height
    return {"lines": rendered, "box": {"x": x, "y": int(box.get("y") or 0), "width": width, "height": height}}


def _render_contract_cover(
    template: IPBroadcastTemplate,
    title: str,
    subtitle: str,
    background: str,
    output_path: str,
) -> str:
    """Render a V2 layout contract with the same coordinates used by preview and cover output."""
    contract = template.layout_contract or {}
    canvas = contract.get("canvas") or {}
    width = int(canvas.get("width") or IP_BROADCAST_CANVAS_WIDTH)
    height = int(canvas.get("height") or IP_BROADCAST_CANVAS_HEIGHT)
    source = _local_background_path(background, template)
    try:
        image = Image.open(source).convert("RGB") if source else Image.new("RGB", (width, height), "#111827")
    except (OSError, ValueError):
        image = Image.new("RGB", (width, height), "#111827")
    canvas_image = ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS).convert("RGBA")
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 112))
    canvas_image = Image.alpha_composite(canvas_image, overlay)
    draw = ImageDraw.Draw(canvas_image, "RGBA")
    fonts = {str(item.get("token")): item for item in contract.get("fonts", []) if isinstance(item, dict)}
    cover = contract.get("cover") or {}
    for key, value in (("title", title), ("subtitle", subtitle)):
        box = cover.get(key) or {}
        font_token = str(box.get("font_token") or "")
        identity = resolve_registered_font(str(fonts.get(font_token, {}).get("font_id") or "noto-sans-sc-bold"))
        font_path = identity.get("font_path") if identity else None
        font_size = int(box.get("font_size") or 32)
        font = ImageFont.truetype(str(font_path), font_size) if font_path else _load_cover_font(font_size, bold=True)
        panel_color = (17, 24, 39, 105 if key == "title" else 92)
        x = int(box.get("x") or 0)
        y = int(box.get("y") or 0)
        box_width = int(box.get("width") or width)
        box_height = int(box.get("height") or 180)
        draw.rounded_rectangle((x - 10, y - 10, x + box_width + 10, y + box_height + 10), radius=22, fill=panel_color)
        _draw_contract_text(draw, value, box, font)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    canvas_image.convert("RGB").save(output_path, format="PNG")
    return output_path


def wrap_template_subtitle_text(
    text: str,
    template: IPBroadcastTemplate,
    video_width: int = IP_BROADCAST_CANVAS_WIDTH,
    video_height: int = IP_BROADCAST_CANVAS_HEIGHT,
) -> str:
    """Apply the contract's deterministic line wrapping before ASS/SRT generation."""
    contract = template.layout_contract
    if not contract:
        return text
    box = contract.get("video_subtitle") or {}
    font_token = str(box.get("font_token") or "")
    font_item = next((item for item in contract.get("fonts", []) if item.get("token") == font_token), {})
    identity = resolve_registered_font(str(font_item.get("font_id") or "noto-sans-sc-bold"))
    font_path = identity.get("font_path") if identity else None
    scaled_size = max(1, round(int(box.get("font_size") or 48) * video_height / IP_BROADCAST_CANVAS_HEIGHT))
    font = ImageFont.truetype(str(font_path), scaled_size) if font_path else _load_cover_font(scaled_size)
    margin_l = round(int(box.get("margin_l") or 0) * video_width / IP_BROADCAST_CANVAS_WIDTH)
    margin_r = round(int(box.get("margin_r") or 0) * video_width / IP_BROADCAST_CANVAS_WIDTH)
    draw = ImageDraw.Draw(Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0)))
    lines = _wrap_cover_text(
        draw,
        text,
        font,
        max(1, video_width - margin_l - margin_r),
        int(box.get("max_lines") or 2),
    )
    return "\n".join(lines)


async def render_ip_broadcast_cover(
    template_id: str | None,
    title: str,
    subtitle: str = "",
    background: str = "",
    output_path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    template = get_ip_broadcast_template_for_render(template_id)
    output_path = output_path or get_temp_path(f"ipb_cover_{template.template_id}.png")
    source_background = background or template.default_background_path
    if template.layout_contract:
        return _render_contract_cover(template, title, subtitle, source_background, output_path)
    generator = HTMLFrameGenerator(template.cover_template_path)
    resolved_font = resolve_registered_font("noto-sans-sc-bold")
    if resolved_font and resolved_font.get("font_path"):
        font_uri = Path(str(resolved_font["font_path"])).resolve().as_uri()
        family = str(resolved_font["family"])
        generator.template = (
            f"<style>@font-face{{font-family:'{family}';font-style:normal;"
            f"font-weight:{int(resolved_font['weight'])};src:url('{font_uri}') format('opentype');}}"
            f"body,.title,.subtitle,.panel{{font-family:'{family}',sans-serif !important;}}</style>"
            + generator.template
        )
    background = background or template.default_background_path
    if background and not background.startswith(("http://", "https://", "data:", "file://")):
        background_path = Path(background)
        if background_path.exists():
            background = background_path.resolve().as_uri()
    ext = {"subtitle": subtitle, "background": background}
    if extra:
        ext.update(extra)
    try:
        return await generator.generate_frame(
            title=title,
            text=subtitle,
            image=background,
            ext=ext,
            output_path=output_path,
        )
    except Exception as exc:  # pragma: no cover - browser availability is environment-specific
        logger.warning("HTML cover renderer unavailable; using deterministic PIL fallback: %s", exc)
        return _render_cover_fallback(template, title, subtitle, source_background, output_path)
