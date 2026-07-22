from pathlib import Path

THEME_SOURCE = Path("desktop/src/theme.ts").read_text()
STYLE_SOURCE = Path("desktop/src/styles.css").read_text()
WORKSPACE_SOURCE = Path("desktop/src/features/dashboard/DashboardView.tsx").read_text()


def test_desktop_keeps_purple_and_exposes_coral_theme_skins():
    assert 'ThemeSkin = "fresh" | "coral"' in THEME_SOURCE
    assert 'label: "清新紫创作版"' in THEME_SOURCE
    assert 'label: "高效珊瑚工作台"' in THEME_SOURCE
    assert '[data-theme="fresh"]' in STYLE_SOURCE
    assert '[data-theme="coral"]' in STYLE_SOURCE


def test_dashboard_progress_uses_active_theme_token():
    assert 'strokeColor="#F05A47"' not in WORKSPACE_SOURCE
