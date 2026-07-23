import asyncio
from pathlib import Path

from pixelle_video.services.publish.execution_protocol import (
    PublishExecutionCheckpoint,
    PublishStage,
)
from pixelle_video.services.publish.models import PublishPackage, PublishStatus
from pixelle_video.services.publish.platform_profiles import get_platform_profile
from pixelle_video.services.publish.platforms.factory import create_platform_publisher
from pixelle_video.services.publish.platforms.multiplatform import (
    KuaishouPublisher,
    ShipinhaoPublisher,
    XiaohongshuPublisher,
)


def _package(platform: str) -> PublishPackage:
    Path("/tmp/platform-expansion-final.mp4").write_bytes(b"valid-video-fixture")
    Path("/tmp/platform-expansion-cover.png").write_bytes(b"valid-cover-fixture")
    return PublishPackage(
        session_id="platform-expansion-session",
        platform=platform,
        video_path="/tmp/platform-expansion-final.mp4",
        title="门店老板实测",
        description="今天到店体验",
        hashtags=["门店营销", "短视频运营"],
        cover_path="/tmp/platform-expansion-cover.png",
    )


class _SafeRuntime:
    def __init__(self, *, state="editor_ready", final_action_result=False, guard_armed=True, upload_result=True, cover_receipt=True, fallback=True):
        self.steps: list[tuple[str, object]] = []
        self.state = state
        self.final_action_result = final_action_result
        self.guard_armed = guard_armed
        self.upload_result = upload_result
        self.cover_receipt = cover_receipt
        self.fallback = fallback

    async def launch_persistent_context(self, platform: str):
        self.steps.append(("launch", platform))
        self.platform = platform
        return self

    async def open_creator_page(self):
        self.steps.append(("open", None))

    async def wait_for_interactive_state(self):
        return self.state

    async def page_fingerprint(self):
        return "sha256:" + "a" * 64

    async def task_space_identity(self):
        return {"id": 1, "name": f"{self.platform}:editor"}

    async def is_logged_in(self):
        self.steps.append(("login_probe", None))
        return self.state not in {"signed_out", "login_required", "captcha", "unknown", "window_closed"}

    async def upload_video(self, path: str):
        self.steps.append(("video", path))
        return self.upload_result

    async def fill_title(self, value: str):
        self.steps.append(("title", value))
        return True

    async def fill_description(self, value: str):
        self.steps.append(("description", value))
        return True

    async def fill_hashtags(self, values: list[str]):
        self.steps.append(("hashtags", values))
        return True

    async def upload_cover(self, path: str):
        self.steps.append(("cover", path))
        return True

    async def wait_until_draft_ready(self):
        self.steps.append(("wait", None))

    async def verify_field(self, field: str, _expected):
        self.steps.append(("verify", field))
        return True

    async def request_final_action(self):
        self.steps.append(("final_action_probe", None))
        return self.final_action_result

    async def final_action_guard_armed(self):
        self.steps.append(("guard", None))
        return self.guard_armed

    async def platform_fallback_boundaries(self):
        return ["HASHTAGS_TEXT_FALLBACK"] if self.fallback else []

    async def read_cover_receipt(self, _path: str):
        if not self.cover_receipt:
            return None
        return {
            "accepted_url": "https://cdn.example/cover.png",
            "before_urls": [],
            "task_space_id": 1,
        }

    async def read_remote_media_identity(self):
        return "kuaishou-media-1"

    async def current_url(self):
        return get_platform_profile(self.platform).entry_url


class _ShipinhaoNoRemoteIdentityRuntime(_SafeRuntime):
    async def read_remote_media_identity(self):
        return None


def test_three_platform_adapters_fill_once_and_stop_for_human():
    for publisher_type, platform, adapter_version in (
        (KuaishouPublisher, "kuaishou", "kuaishou-video@1"),
        (ShipinhaoPublisher, "shipinhao", "shipinhao-video@1"),
        (XiaohongshuPublisher, "xiaohongshu", "xiaohongshu-video@1"),
    ):
        runtime = _SafeRuntime()
        result = asyncio.run(publisher_type(runtime).prepare_draft(_package(platform)))
        assert result.status is PublishStatus.DRAFT_READY
        assert result.adapter_state == "waiting_for_human"
        assert result.adapter_version == adapter_version
        assert result.requires_human_confirmation is True
        assert result.filled_fields == list(get_platform_profile(platform).required_fields)
        assert sum(step[0] == "video" for step in runtime.steps) == 1
        assert sum(step[0] == "final_action_probe" for step in runtime.steps) == 1


def test_platform_adapter_rejects_a_runtime_that_attempts_final_publish():
    runtime = _SafeRuntime(final_action_result=True)
    result = asyncio.run(KuaishouPublisher(runtime).prepare_draft(_package("kuaishou")))
    assert result.status is PublishStatus.FAILED
    assert result.message == "FINAL_ACTION_BLOCKED"
    assert result.adapter_state == "needs_attention"


def test_platform_adapter_rejects_missing_final_action_guard():
    runtime = _SafeRuntime(guard_armed=False)
    result = asyncio.run(ShipinhaoPublisher(runtime).prepare_draft(_package("shipinhao")))
    assert result.status is PublishStatus.FAILED
    assert result.message == "FINAL_ACTION_GUARD_NOT_ARMED"
    assert result.adapter_state == "needs_attention"


def test_platform_adapter_maps_login_challenge_and_transitional_states_without_mutation():
    for state, expected in (
        ("signed_out", PublishStatus.LOGIN_REQUIRED),
        ("captcha", PublishStatus.FAILED),
        ("unknown", PublishStatus.FAILED),
        ("window_closed", PublishStatus.FAILED),
        ("loading", PublishStatus.FAILED),
        ("processing", PublishStatus.FAILED),
    ):
        runtime = _SafeRuntime(state=state)
        result = asyncio.run(KuaishouPublisher(runtime).prepare_draft(_package("kuaishou")))
        assert result.status is expected
        assert not any(step[0] in {"video", "title", "description", "hashtags", "cover", "final_action_probe"} for step in runtime.steps)


def test_v2_factory_maps_video_channel_account_to_shipinhao_without_douyin():
    publisher = create_platform_publisher("video_channel", _SafeRuntime())
    assert publisher.platform == "shipinhao"
    assert publisher.adapter_version == "shipinhao-video@1"


def test_shipinhao_accepts_video_channel_checkpoint_alias():
    callbacks = []
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "d" * 64,
        account_id="acct_shipinhao_1",
        platform="video_channel",
        attempt=1,
        runtime_kind="playwright",
    )
    runtime = _SafeRuntime()
    result = asyncio.run(
        ShipinhaoPublisher(
            runtime,
            account_id="acct_shipinhao_1",
            checkpoint=checkpoint,
            checkpoint_callback=lambda updated, stage, blocker: callbacks.append(
                (updated, stage, blocker)
            ),
        ).prepare_draft(_package("shipinhao"))
    )
    assert result.status is PublishStatus.DRAFT_READY
    assert callbacks


def test_shipinhao_checkpoint_allows_explicit_missing_remote_media_identity_boundary():
    callbacks = []
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "f" * 64,
        account_id="acct_shipinhao_2",
        platform="shipinhao",
        attempt=1,
        runtime_kind="playwright",
    )
    runtime = _ShipinhaoNoRemoteIdentityRuntime()
    result = asyncio.run(
        ShipinhaoPublisher(
            runtime,
            account_id="acct_shipinhao_2",
            checkpoint=checkpoint,
            checkpoint_callback=lambda updated, stage, blocker: callbacks.append(
                (updated, stage, blocker)
            ),
        ).prepare_draft(_package("shipinhao"))
    )
    assert result.status is PublishStatus.DRAFT_READY
    assert result.media_readback is True
    assert result.cover_readback is True
    assert "SHIPINHAO_NO_STABLE_REMOTE_MEDIA_ID" in result.platform_fallback_boundaries
    assert result.final_publish_click_count == 0
    assert callbacks[-1][0].draft_identity is not None
    assert callbacks[-1][0].draft_identity.remote_media_identity is None


def test_shipinhao_checkpointed_local_blob_cover_fails_closed_without_https_receipt():
    runtime = _ShipinhaoNoRemoteIdentityRuntime()

    async def local_blob_receipt(_path: str):
        return {
            "accepted_url": "blob:accepted-preview",
            "before_urls": [],
            "task_space_id": 1,
        }

    runtime.read_cover_receipt = local_blob_receipt
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "0" * 64,
        account_id="acct_shipinhao_3",
        platform="shipinhao",
        attempt=1,
        runtime_kind="playwright",
    )
    result = asyncio.run(
        ShipinhaoPublisher(
            runtime,
            account_id="acct_shipinhao_3",
            checkpoint=checkpoint,
            checkpoint_callback=lambda *_args: None,
        ).prepare_draft(_package("shipinhao"))
    )
    assert result.status is PublishStatus.FAILED
    assert result.message == "COVER_RECEIPT_READBACK_FAILED"
    assert result.final_publish_click_count == 0


def test_shipinhao_without_checkpoint_projects_missing_remote_media_boundary():
    result = asyncio.run(
        ShipinhaoPublisher(_ShipinhaoNoRemoteIdentityRuntime()).prepare_draft(
            _package("shipinhao")
        )
    )
    assert result.status is PublishStatus.DRAFT_READY
    assert "SHIPINHAO_NO_STABLE_REMOTE_MEDIA_ID" in result.platform_fallback_boundaries


def test_platform_adapter_failures_are_fail_closed_and_do_not_reach_final_action():
    for runtime, expected in (
        (_SafeRuntime(upload_result=False), "VIDEO_UPLOAD_FAILED"),
        (_SafeRuntime(cover_receipt=False), "COVER_RECEIPT_READBACK_FAILED"),
        (_SafeRuntime(fallback=False), "HASHTAGS_FALLBACK_BOUNDARY_MISSING"),
    ):
        result = asyncio.run(KuaishouPublisher(runtime).prepare_draft(_package("kuaishou")))
        assert result.status is PublishStatus.FAILED
        assert result.message == expected
        assert not any(step[0] == "final_action_probe" for step in runtime.steps)


def test_kuaishou_local_blob_cover_is_explicit_boundary_not_fake_remote_receipt():
    runtime = _SafeRuntime()

    async def local_blob_receipt(_path: str):
        return {
            "accepted_url": "blob:accepted-preview",
            "before_urls": ["blob:accepted-preview"],
            "task_space_id": 1,
        }

    runtime.read_cover_receipt = local_blob_receipt
    result = asyncio.run(KuaishouPublisher(runtime).prepare_draft(_package("kuaishou")))
    assert result.status is PublishStatus.DRAFT_READY
    assert result.cover_readback is True
    assert result.cover_receipt_present is False
    assert "KUAISHOU_LOCAL_BLOB_PREVIEW_ONLY" in result.platform_fallback_boundaries
    assert result.final_publish_click_count == 0


def test_kuaishou_checkpointed_local_blob_cover_fails_closed():
    runtime = _SafeRuntime()

    async def local_blob_receipt(_path: str):
        return {
            "accepted_url": "blob:accepted-preview",
            "before_urls": ["blob:accepted-preview"],
            "task_space_id": 1,
        }

    runtime.read_cover_receipt = local_blob_receipt
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_kuaishou_1",
        platform="kuaishou",
        attempt=1,
        runtime_kind="playwright",
    )
    result = asyncio.run(
        KuaishouPublisher(
            runtime,
            account_id="acct_kuaishou_1",
            checkpoint=checkpoint,
            checkpoint_callback=lambda *_args: None,
        ).prepare_draft(_package("kuaishou"))
    )
    assert result.status is PublishStatus.FAILED
    assert result.message == "COVER_RECEIPT_READBACK_FAILED"
    assert result.final_publish_click_count == 0


def test_platform_adapter_checkpoint_records_ordered_stages_and_remote_media_evidence():
    callbacks = []
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "b" * 64,
        account_id="acct_kuaishou_1",
        platform="kuaishou",
        attempt=1,
        runtime_kind="playwright",
    )
    runtime = _SafeRuntime()
    publisher = KuaishouPublisher(
        runtime,
        account_id="acct_kuaishou_1",
        checkpoint=checkpoint,
        checkpoint_callback=lambda updated, stage, blocker: callbacks.append((updated, stage, blocker)),
    )
    result = asyncio.run(publisher.prepare_draft(_package("kuaishou")))
    assert result.status is PublishStatus.DRAFT_READY
    assert [stage for _, stage, _ in callbacks] == list(PublishStage)
    assert publisher.checkpoint is not None
    assert publisher.checkpoint.last_stage is PublishStage.VERIFY
    assert publisher.checkpoint.final_action_guard_armed is True
    assert publisher.checkpoint.cover_receipts
    assert publisher.checkpoint.draft_identity is not None
    assert publisher.checkpoint.draft_identity.remote_media_identity
    assert result.final_publish_click_count == 0


def test_platform_adapter_same_attempt_resume_does_not_move_checkpoint_backwards():
    callbacks = []
    first = KuaishouPublisher(
        _SafeRuntime(),
        account_id="acct_kuaishou_1",
        checkpoint=PublishExecutionCheckpoint(
            package_fingerprint="sha256:" + "c" * 64,
            account_id="acct_kuaishou_1",
            platform="kuaishou",
            attempt=1,
            runtime_kind="playwright",
        ),
        checkpoint_callback=lambda updated, stage, blocker: callbacks.append((updated, stage, blocker)),
    )
    assert asyncio.run(first.prepare_draft(_package("kuaishou"))).status is PublishStatus.DRAFT_READY
    resumed_callbacks = []
    resumed = KuaishouPublisher(
        _SafeRuntime(fallback=False),
        account_id="acct_kuaishou_1",
        checkpoint=first.checkpoint,
        checkpoint_callback=lambda updated, stage, blocker: resumed_callbacks.append((updated, stage, blocker)),
    )
    result = asyncio.run(resumed.prepare_draft(_package("kuaishou")))
    assert result.status is PublishStatus.DRAFT_READY
    assert resumed_callbacks == []
    assert resumed.checkpoint is not None
    assert resumed.checkpoint.last_stage is PublishStage.VERIFY
