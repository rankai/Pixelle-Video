from pathlib import Path

from pixelle_video.services.ip_broadcast_templates import (
    build_ass_force_style,
    get_ip_broadcast_template,
    list_ip_broadcast_templates,
)


def test_ip_broadcast_template_registry_contains_three_templates():
    templates = list_ip_broadcast_templates()

    assert [template.template_id for template in templates] == [
        "boss_clean",
        "boss_authority",
        "boss_premium",
    ]


def test_ip_broadcast_template_cover_files_exist():
    for template in list_ip_broadcast_templates():
        assert Path(template.cover_template_path).exists()


def test_ip_broadcast_template_preview_files_exist():
    for template in list_ip_broadcast_templates():
        assert Path(template.preview_image_path).exists()


def test_build_ass_force_style_uses_selected_template_subtitle_style():
    template = get_ip_broadcast_template("boss_authority")

    force_style = build_ass_force_style(template)

    assert "Fontsize=54" in force_style
    assert "Alignment=2" in force_style
    assert "Outline=4" in force_style
