from pathlib import Path


SOURCE = Path("desktop/src/App.tsx").read_text()


def test_publish_page_states_platform_capabilities_without_overpromising():
    publish_step = SOURCE[SOURCE.index("function PublishStep(") : SOURCE.index("function PublishField")]

    assert "抖音草稿助手" in publish_step
    assert "其他平台复制素材手动发布" in publish_step
    assert "不是全平台自动发布" in publish_step
    assert "publishCapabilityLabel" in SOURCE


def test_platform_card_copy_uses_complete_publish_materials():
    publish_step = SOURCE[SOURCE.index("function PublishStep(") : SOURCE.index("function PublishField")]

    assert "buildPlatformMaterialText" in publish_step
    assert "finalVideoPath" in publish_step
    assert "coverPath" in publish_step
    assert "最终视频路径" in publish_step
    assert "封面路径" in publish_step
    assert '`${String(value.title || "")}\\n${String(value.description || "")}`' not in publish_step


def test_copy_button_has_feedback_states():
    copy_button = SOURCE[SOURCE.index("function CopyButton(") : SOURCE.index("function platformLabel")]

    assert "已复制" in copy_button
    assert "复制失败" in copy_button
    assert "navigator.clipboard.writeText" in copy_button
    assert "window.setTimeout" in copy_button
