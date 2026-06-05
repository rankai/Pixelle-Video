import re
from pathlib import Path

from pixelle_video.services.ip_broadcast_templates import (
    build_ass_force_style,
    get_ip_broadcast_template,
    list_ip_broadcast_templates,
)
from web.ip_broadcast.modules import m5_postproduction

CANVAS_HEIGHT = 1920
COVER_TITLE_TOP_MIN = 220
COVER_TITLE_BOTTOM_MAX = 760
COVER_SUBTITLE_BOTTOM_MIN = 320
VIDEO_SUBTITLE_MARGIN_MIN = 200


def _css_px(html: str, selector: str, property_name: str) -> int:
    match = re.search(rf"\.{selector}\s*\{{(?P<body>.*?)\}}", html, re.S)
    assert match, f"Missing .{selector} CSS block"
    prop = re.search(rf"{property_name}:\s*(?P<value>\d+)px", match.group("body"))
    assert prop, f"Missing {property_name} in .{selector}"
    return int(prop.group("value"))


def _force_style_value(force_style: str, key: str) -> int:
    for part in force_style.split(","):
        name, _, value = part.partition("=")
        if name == key:
            return int(value)
    raise AssertionError(f"Missing {key} in force style: {force_style}")


def test_ip_broadcast_template_registry_contains_three_templates():
    templates = list_ip_broadcast_templates()

    assert [template.template_id for template in templates] == [
        "boss_clean",
        "boss_authority",
        "boss_premium",
    ]


def test_ip_broadcast_templates_have_distinct_card_descriptions():
    templates = list_ip_broadcast_templates()
    descriptions = [template.short_description for template in templates]

    assert len(set(descriptions)) == len(templates)
    assert all(template.full_description for template in templates)


def test_ip_broadcast_template_cover_files_exist():
    for template in list_ip_broadcast_templates():
        assert Path(template.cover_template_path).exists()


def test_ip_broadcast_template_preview_files_exist():
    for template in list_ip_broadcast_templates():
        assert Path(template.preview_image_path).exists()


def test_build_ass_force_style_uses_selected_template_subtitle_style():
    template = get_ip_broadcast_template("boss_authority")

    force_style = build_ass_force_style(template)

    assert "Fontsize=30" in force_style
    assert "Alignment=2" in force_style
    assert "Outline=3" in force_style


def test_boss_clean_template_keeps_title_and_subtitles_in_safe_zones():
    template = get_ip_broadcast_template("boss_clean")
    cover_html = Path(template.cover_template_path).read_text()
    force_style = build_ass_force_style(template)

    title_top = _css_px(cover_html, "title", "top")
    title_height = _css_px(cover_html, "title", "max-height")
    subtitle_bottom = _css_px(cover_html, "subtitle", "bottom")
    assert COVER_TITLE_TOP_MIN <= title_top
    assert title_top + title_height <= COVER_TITLE_BOTTOM_MAX
    assert subtitle_bottom >= COVER_SUBTITLE_BOTTOM_MIN
    assert "font-size: 44px" in cover_html
    assert "Fontsize=28" in force_style
    assert _force_style_value(force_style, "MarginV") >= 170


def test_all_templates_keep_video_subtitles_inside_platform_safe_area():
    expected = {
        "boss_clean": ("Fontsize=28", "MarginV=180"),
        "boss_authority": ("Fontsize=30", "MarginV=190"),
        "boss_premium": ("Fontsize=28", "MarginV=180"),
    }

    for template_id, (font_size, margin_v) in expected.items():
        force_style = build_ass_force_style(get_ip_broadcast_template(template_id))

        assert font_size in force_style
        assert margin_v in force_style
        assert "Alignment=2" in force_style


def test_all_cover_templates_keep_main_text_inside_safe_area():
    for template in list_ip_broadcast_templates():
        html = Path(template.cover_template_path).read_text()
        if template.template_id == "boss_premium":
            panel_bottom = _css_px(html, "panel", "bottom")
            panel_height = _css_px(html, "panel", "max-height")
            panel_top = CANVAS_HEIGHT - panel_bottom - panel_height
            assert 1080 <= panel_top <= 1220
            assert panel_bottom >= COVER_SUBTITLE_BOTTOM_MIN
        else:
            title_top = _css_px(html, "title", "top")
            title_height = _css_px(html, "title", "max-height")
            subtitle_bottom = _css_px(html, "subtitle", "bottom")
            assert COVER_TITLE_TOP_MIN <= title_top
            assert title_top + title_height <= COVER_TITLE_BOTTOM_MAX
            assert subtitle_bottom >= COVER_SUBTITLE_BOTTOM_MIN


def test_boss_clean_cover_keeps_background_visible():
    html = Path(get_ip_broadcast_template("boss_clean").cover_template_path).read_text()

    bg_line = next(line for line in html.splitlines() if "background-image:" in line)
    assert "rgba(255,255,255,.78)" not in bg_line
    assert "rgba(255,255,255,.92)" not in bg_line
    assert "rgba(255,255,255,.22)" in bg_line


def test_template_card_text_uses_fixed_title_and_description_heights():
    html = m5_postproduction._build_card_text_html(
        title="强观点标题风",
        subtitle="顶部强标题，下方字幕突出观点节奏。",
        tooltip="封面顶部大标题强化观点；字幕字号更大、描边更重，适合金句、观点输出和强转化口播。",
    )

    assert "min-height:20px" in html
    assert "min-height:34px" in html
    assert "padding:8px 2px 2px" in html
    assert "-webkit-line-clamp:2" in html
    assert 'title="封面顶部大标题强化观点；字幕字号更大、描边更重，适合金句、观点输出和强转化口播。"' in html


def test_template_preview_html_uses_fixed_height(tmp_path):
    preview = tmp_path / "preview.png"
    preview.write_bytes(b"image")

    html = m5_postproduction._build_template_preview_html(str(preview), height=180)

    assert "height:180px" in html
    assert "object-fit:contain" in html
    assert "data:image/png;base64" in html
