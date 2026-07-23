from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import publish as publish_router_module
from api.tasks import task_manager
from pixelle_video.services.publish.browser_runtime import (
    DEFAULT_BROWSER_RUNTIME,
    SUPPORTED_BROWSER_RUNTIMES,
    BrowserRuntime,
)
from pixelle_video.services.publish.models import PublishPackage, PublishStatus
from pixelle_video.services.publish.platforms.douyin import DouyinPublisher
from pixelle_video.services.publish.platforms.multiplatform import XiaohongshuPublisher
from pixelle_video.utils.chromium import playwright_chromium_launch_options


def _publish_client() -> TestClient:
    app = FastAPI()
    app.include_router(publish_router_module.router, prefix="/api")
    return TestClient(app)


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


def test_publish_package_model_accepts_all_supported_platforms():
    for platform in ["douyin", "xiaohongshu", "shipinhao", "kuaishou"]:
        package = PublishPackage(
            session_id="s1",
            platform=platform,
            video_path="/tmp/final.mp4",
            title="夏季新品",
        )
        assert package.platform == platform


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


def test_playwright_can_use_system_chromium_from_environment(monkeypatch):
    monkeypatch.setenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH", "/usr/bin/chromium")

    assert playwright_chromium_launch_options() == {"executable_path": "/usr/bin/chromium"}


async def test_douyin_publisher_returns_login_required_when_not_logged_in():
    class FakeRuntime:
        async def launch_persistent_context(self, platform: str):
            assert platform == "douyin"
            return self

        async def open_creator_page(self):
            return None

        async def is_logged_in(self):
            return False

    package = PublishPackage(
        session_id="s1",
        platform="douyin",
        video_path="/tmp/final.mp4",
        title="火锅套餐",
    )

    result = await DouyinPublisher(FakeRuntime()).prepare_draft(package)

    assert result.status is PublishStatus.LOGIN_REQUIRED
    assert result.platform == "douyin"


async def test_douyin_publisher_prepares_draft_with_fake_runtime():
    class FakeRuntime:
        def __init__(self):
            self.steps = []

        async def launch_persistent_context(self, platform: str):
            self.steps.append(("launch", platform))
            return self

        async def open_creator_page(self):
            self.steps.append(("open_creator_page",))

        async def is_logged_in(self):
            self.steps.append(("is_logged_in",))
            return True

        async def upload_video(self, video_path: str):
            self.steps.append(("upload_video", video_path))

        async def fill_title(self, title: str):
            self.steps.append(("fill_title", title))

        async def fill_description(self, description: str):
            self.steps.append(("fill_description", description))

        async def fill_hashtags(self, hashtags: list[str]):
            self.steps.append(("fill_hashtags", hashtags))

        async def upload_cover(self, cover_path: str):
            self.steps.append(("upload_cover", cover_path))

        async def wait_until_draft_ready(self):
            self.steps.append(("wait_until_draft_ready",))

    runtime = FakeRuntime()
    package = PublishPackage(
        session_id="s1",
        platform="douyin",
        video_path="/tmp/final.mp4",
        title="火锅套餐",
        description="下班两个人来吃",
        hashtags=["火锅", "团购套餐"],
        cover_path="/tmp/cover.png",
    )

    result = await DouyinPublisher(runtime).prepare_draft(package)

    assert result.status is PublishStatus.DRAFT_READY
    assert runtime.steps == [
        ("launch", "douyin"),
        ("open_creator_page",),
        ("is_logged_in",),
        ("upload_video", "/tmp/final.mp4"),
        ("fill_title", "火锅套餐"),
        ("fill_description", "下班两个人来吃"),
        ("fill_hashtags", ["火锅", "团购套餐"]),
        ("upload_cover", "/tmp/cover.png"),
        ("wait_until_draft_ready",),
    ]


async def test_multiplatform_publisher_always_requires_human_confirmation():
    Path("/tmp/final.mp4").write_bytes(b"video-fixture")
    Path("/tmp/cover.png").write_bytes(b"cover-fixture")
    class FakeRuntime:
        async def launch_persistent_context(self, platform: str):
            self.platform = platform
            return self

        async def open_creator_page(self):
            return None

        async def is_logged_in(self):
            return True

        async def upload_video(self, _path: str):
            return True

        async def upload_cover(self, _path: str):
            return True

        async def fill_title(self, _title: str):
            return True

        async def fill_description(self, _description: str):
            return True

        async def fill_hashtags(self, _hashtags: list[str]):
            return True

        async def wait_until_draft_ready(self):
            return None

        async def wait_for_interactive_state(self):
            return "editor_ready"

        async def page_fingerprint(self):
            return "sha256:" + "a" * 64

        async def task_space_identity(self):
            return {"id": 1, "name": "xiaohongshu:editor"}

        async def verify_field(self, _field: str, _expected):
            return True

        async def request_final_action(self):
            return False

        async def final_action_guard_armed(self):
            return True

        async def platform_fallback_boundaries(self):
            return ["HASHTAGS_TEXT_FALLBACK"]

        async def read_cover_receipt(self, _path: str):
            return {"accepted_url": "https://cdn.example/cover.png", "before_urls": [], "task_space_id": 1}

        async def current_url(self):
            return "https://creator.xiaohongshu.com/publish/publish"

    package = PublishPackage(
        session_id="s1",
        platform="xiaohongshu",
        video_path="/tmp/final.mp4",
        title="夏季新品",
        description="今天到店",
        hashtags=["新品"],
        cover_path="/tmp/cover.png",
    )
    result = await XiaohongshuPublisher(FakeRuntime()).prepare_draft(package)

    assert result.status is PublishStatus.DRAFT_READY
    assert result.requires_human_confirmation is True
    assert result.filled_fields == ["video", "title", "description", "hashtags", "cover"]
    assert "亲自点击最终发布" in result.message


def test_prepare_douyin_publish_endpoint_returns_publish_result(monkeypatch):
    class FakePublisher:
        async def prepare_draft(self, package: PublishPackage):
            assert package.platform == "douyin"
            assert package.video_path == "/tmp/final.mp4"
            return {
                "status": "draft_ready",
                "platform": "douyin",
                "message": "草稿已准备好",
            }

    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "true")
    monkeypatch.setattr(publish_router_module, "get_douyin_publisher", lambda: FakePublisher())

    response = _publish_client().post(
        "/api/publish/douyin/prepare",
        json={
            "session_id": "s1",
            "platform": "douyin",
            "video_path": "/tmp/final.mp4",
            "title": "火锅套餐",
            "description": "下班两个人来吃",
            "hashtags": ["火锅", "团购套餐"],
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "draft_ready"
    task = task_manager.get_task(response.json()["task_id"])
    assert task is not None
    assert task.display_name == "抖音发布助手"
    assert task.flow_name == "短视频发布"
    assert task.status == "completed"


def test_legacy_prepare_route_blocks_non_douyin_platforms(monkeypatch):
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "true")
    response = _publish_client().post(
        "/api/publish/xiaohongshu/prepare",
        json={
            "session_id": "s1",
            "platform": "xiaohongshu",
            "video_path": "/tmp/final.mp4",
            "title": "夏季新品",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "PLATFORM_RELEASE_NOT_READY"


def test_prepare_douyin_publish_rejects_untrusted_local_paths(monkeypatch):
    class FakePublisher:
        async def prepare_draft(self, package: PublishPackage):
            raise AssertionError("publisher must not run for unsafe paths")

    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "true")
    monkeypatch.setattr(publish_router_module, "get_douyin_publisher", lambda: FakePublisher())

    response = _publish_client().post(
        "/api/publish/douyin/prepare",
        json={
            "session_id": "s1",
            "platform": "douyin",
            "video_path": "/etc/passwd",
            "title": "火锅套餐",
        },
    )

    assert response.status_code == 403
    assert "不允许发布该文件路径" in response.json()["detail"]


def test_prepare_douyin_publish_maps_technical_errors_to_user_message(monkeypatch):
    class FakePublisher:
        async def prepare_draft(self, package: PublishPackage):
            raise RuntimeError(
                "Timeout 30000ms exceeded while waiting for locator input[type='file']"
            )

    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "true")
    monkeypatch.setattr(publish_router_module, "get_douyin_publisher", lambda: FakePublisher())

    response = _publish_client().post(
        "/api/publish/douyin/prepare",
        json={
            "session_id": "s1",
            "platform": "douyin",
            "video_path": "/tmp/final.mp4",
            "title": "火锅套餐",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "failed"
    assert response.json()["message"] == "发布页面响应超时，请确认网络正常并重新打开发布助手。"


def test_prepare_douyin_publish_is_disabled_outside_desktop_mode(monkeypatch):
    class FakePublisher:
        async def prepare_draft(self, package: PublishPackage):
            raise AssertionError("publisher must not run on server")

    monkeypatch.delenv("PIXELLE_DESKTOP_MODE", raising=False)
    monkeypatch.setattr(publish_router_module, "get_douyin_publisher", lambda: FakePublisher())

    response = _publish_client().post(
        "/api/publish/douyin/prepare",
        json={
            "session_id": "s1",
            "platform": "douyin",
            "video_path": "/tmp/final.mp4",
            "title": "火锅套餐",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "发布助手仅支持桌面端本地运行，服务器端不执行自动发布。"
