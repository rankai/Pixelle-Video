from pixelle_video.services.publish.browser_runtime import (
    DEFAULT_BROWSER_RUNTIME,
    SUPPORTED_BROWSER_RUNTIMES,
    BrowserRuntime,
)
from pixelle_video.services.publish.models import PublishPackage, PublishStatus


def test_publish_package_model_accepts_douyin_payload():
    package = PublishPackage(
        session_id="s1",
        platform="douyin",
        video_path="/tmp/final.mp4",
        title="火锅套餐",
        description="下班两个人来吃",
        hashtags=["火锅", "团购套餐"],
    )

    assert package.platform == "douyin"
    assert package.hashtags == ["火锅", "团购套餐"]


def test_publish_statuses_cover_desktop_assistant_flow():
    assert {status.value for status in PublishStatus} == {
        "login_required",
        "uploading",
        "draft_ready",
        "failed",
        "cancelled",
    }


def test_browser_runtime_keeps_cloakbrowser_optional():
    assert DEFAULT_BROWSER_RUNTIME == "playwright"
    assert SUPPORTED_BROWSER_RUNTIMES == {"playwright", "cloakbrowser"}
    assert hasattr(BrowserRuntime, "launch_persistent_context")
    assert hasattr(BrowserRuntime, "close")
