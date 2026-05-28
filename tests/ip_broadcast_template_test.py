from pathlib import Path

from pixelle_video.services.ip_broadcast_templates import (
    build_ass_force_style,
    get_ip_broadcast_template,
    list_ip_broadcast_templates,
)
from web.ip_broadcast.modules import m5_postproduction


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

    assert "Fontsize=46" in force_style
    assert "Alignment=2" in force_style
    assert "Outline=4" in force_style


def test_boss_clean_template_keeps_title_and_subtitles_in_safe_zones():
    template = get_ip_broadcast_template("boss_clean")
    cover_html = Path(template.cover_template_path).read_text()
    force_style = build_ass_force_style(template)

    assert "top: 220px" in cover_html
    assert "font-size: 62px" in cover_html
    assert "max-height: 360px" in cover_html
    assert "Fontsize=40" in force_style
    assert "MarginV=210" in force_style


def test_all_templates_keep_video_subtitles_below_cover_title_zone():
    expected = {
        "boss_clean": ("Fontsize=40", "MarginV=210"),
        "boss_authority": ("Fontsize=46", "MarginV=220"),
        "boss_premium": ("Fontsize=42", "MarginV=210"),
    }

    for template_id, (font_size, margin_v) in expected.items():
        force_style = build_ass_force_style(get_ip_broadcast_template(template_id))

        assert font_size in force_style
        assert margin_v in force_style
        assert "Alignment=2" in force_style


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
