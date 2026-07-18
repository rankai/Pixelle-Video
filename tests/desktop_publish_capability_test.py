from pathlib import Path

SOURCE = Path("desktop/src/features/publishing/PublishWorkspace.tsx").read_text()


def test_publish_page_states_platform_capabilities_without_overpromising():
    assert "发布前安全停手" in SOURCE
    assert "系统不会执行这一步" in SOURCE
    assert "自动填充 · 人工发布" in SOURCE
    for platform in ["douyin", "xiaohongshu", "shipinhao", "kuaishou"]:
        assert f'"{platform}"' in SOURCE


def test_platform_card_copy_uses_complete_publish_materials():
    platform_text = SOURCE[SOURCE.index("function buildPlatformText(") :]

    assert "finalVideoPath" in platform_text
    assert "coverPath" in platform_text
    assert "视频：" in platform_text
    assert "封面：" in platform_text
    assert "自动填充后人工确认" in platform_text


def test_copy_button_has_feedback_states():
    copy_button = SOURCE[SOURCE.index("function CopyButton(") : SOURCE.index("function platformLabel")]

    assert "已复制" in copy_button
    assert "复制失败" in copy_button
    assert "navigator.clipboard.writeText" in copy_button
    assert "window.setTimeout" in copy_button
