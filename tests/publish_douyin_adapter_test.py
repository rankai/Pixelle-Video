import hashlib

import pytest

from pixelle_video.services.publish.browser_runtime import (
    PlaywrightPublishContext,
    _canonical_editor_url,
)
from pixelle_video.services.publish.execution_protocol import (
    DraftIdentity,
    PublishBlockerCode,
    PublishExecutionCheckpoint,
    PublishStage,
    UploadMode,
)
from pixelle_video.services.publish.models import PublishPackage, PublishStatus
from pixelle_video.services.publish.platforms.douyin import DouyinPublisher


class FixtureDouyinContext:
    def __init__(self, state="signed_in", *, readback=True, transition_state=None, topic_entities=True, cover_receipt=True, fingerprint=None):
        self.state = state
        self.readback = readback
        self.transition_state = transition_state
        self.topic_entities = topic_entities
        self.cover_receipt = cover_receipt
        self.fingerprint = fingerprint or ("sha256:" + "a" * 64)
        self.actions = []

    async def open_creator_page(self):
        self.actions.append("open")

    async def detect_state(self):
        return self.state

    async def is_logged_in(self):
        self.actions.append("probe_login")
        return self.state not in {"signed_out", "captcha", "unknown", "window_closed"}

    async def upload_video(self, path):
        self.actions.append(("video", path))
        self.state = "processing"
        return True

    async def uploaded_media_metadata(self):
        return {"name": "video.mp4", "size": 0, "type": "video/mp4"}

    async def wait_for_state(self, expected):
        self.actions.append(("wait_for_state", expected))
        self.state = self.transition_state or expected
        return True

    async def fill_title(self, value):
        self.actions.append(("title", value))
        return True

    async def fill_description(self, value):
        self.actions.append(("description", value))
        return True

    async def fill_hashtags(self, values):
        self.actions.append(("hashtags", values))
        return True

    async def upload_cover(self, path):
        self.actions.append(("cover", path))
        return True

    async def page_fingerprint(self):
        return self.fingerprint

    async def task_space_identity(self):
        return {"id": 101, "name": "douyin:fixture-editor"}

    async def read_topic_entities(self):
        if not self.topic_entities:
            return []
        return [
            {"label": f"#{tag}", "normalized_label": tag, "mention_type": "#", "entity_id": f"topic_{tag}"}
            for tag in ("火锅", "团购")
        ]

    async def read_cover_receipt(self, _path):
        if not self.cover_receipt:
            return None
        return {
            "before_urls": ["https://cdn.example/old-cover.png"],
            "accepted_url": "https://cdn.example/new-cover.png",
            "task_space_id": 101,
        }

    async def verify_field(self, _field, _expected):
        return self.readback

    async def wait_until_draft_ready(self):
        self.actions.append("wait")

    async def request_final_action(self):
        self.actions.append("guard")
        return False

    async def final_action_guard_armed(self):
        return True

    async def current_url(self):
        return "fixture://douyin/editor"


class FixtureDouyinRuntime:
    def __init__(self, context):
        self.context = context

    async def launch_persistent_context(self, platform):
        assert platform == "douyin"
        return self.context


def _package():
    return PublishPackage(
        session_id="s1",
        platform="douyin",
        video_path="/tmp/video.mp4",
        title="火锅套餐",
        description="下班两个人来吃",
        hashtags=["火锅", "团购"],
        cover_path="/tmp/cover.png",
    )


def test_douyin_upload_and_post_routes_share_editor_identity():
    upload = _canonical_editor_url(
        "douyin",
        "https://creator.douyin.com/creator-micro/content/upload?from=publish",
    )
    post = _canonical_editor_url(
        "douyin",
        "https://creator.douyin.com/creator-micro/content/post/video?enter_from=publish_page",
    )
    assert upload == post == "https://creator.douyin.com/creator-micro/content/editor"


@pytest.mark.asyncio
async def test_douyin_adapter_maps_login_challenge_and_unknown_states():
    for state, expected_status, expected_message, expected_adapter_state in (
        ("signed_out", PublishStatus.LOGIN_REQUIRED, "DOUYIN_LOGIN_REQUIRED", "waiting_for_login"),
        ("captcha", PublishStatus.FAILED, "DOUYIN_CHALLENGE_REQUIRED", "waiting_for_human"),
        ("uploading", PublishStatus.UPLOADING, "DOUYIN_UPLOAD_IN_PROGRESS", "running"),
        ("processing", PublishStatus.UPLOADING, "DOUYIN_PROCESSING_IN_PROGRESS", "running"),
        ("waiting_for_human", PublishStatus.DRAFT_READY, "DOUYIN_WAITING_FOR_HUMAN", "waiting_for_human"),
        ("unknown", PublishStatus.FAILED, "DOUYIN_PAGE_CHANGED", "needs_attention"),
        ("window_closed", PublishStatus.FAILED, "DOUYIN_WINDOW_CLOSED", "needs_attention"),
    ):
        context = FixtureDouyinContext(state)
        result = await DouyinPublisher(FixtureDouyinRuntime(context)).prepare_draft(_package())
        assert result.status is expected_status
        assert result.message == expected_message
        assert result.adapter_state == expected_adapter_state
        assert result.requires_human_confirmation is True
        assert not any(isinstance(action, tuple) for action in context.actions)


@pytest.mark.asyncio
async def test_douyin_adapter_semantic_readback_and_final_guard():
    context = FixtureDouyinContext()
    publisher = DouyinPublisher(FixtureDouyinRuntime(context))
    result = await publisher.prepare_draft(_package())
    assert publisher.adapter_version == "douyin-entry@1"
    assert result.status is PublishStatus.DRAFT_READY
    assert result.filled_fields == ["video", "title", "description", "hashtags", "cover"]
    assert result.draft_url == "fixture://douyin/editor"
    assert result.requires_human_confirmation is True
    assert result.adapter_state == "waiting_for_human"
    assert "guard" in context.actions


@pytest.mark.asyncio
async def test_douyin_adapter_does_not_reupload_when_editor_is_ready():
    context = FixtureDouyinContext(state="editor_ready")
    result = await DouyinPublisher(FixtureDouyinRuntime(context)).prepare_draft(_package())
    assert result.status is PublishStatus.DRAFT_READY
    assert "video" in result.filled_fields
    assert not any(isinstance(action, tuple) and action[0] == "video" for action in context.actions)


@pytest.mark.asyncio
async def test_douyin_adapter_fails_closed_on_readback_mismatch():
    context = FixtureDouyinContext(readback=False)
    result = await DouyinPublisher(FixtureDouyinRuntime(context)).prepare_draft(_package())
    assert result.status is PublishStatus.FAILED
    assert result.message == "DOUYIN_VIDEO_READBACK_FAILED"
    assert result.filled_fields == []


@pytest.mark.asyncio
async def test_douyin_adapter_preserves_midflow_window_or_challenge_state():
    for transition_state, expected_status, expected_message in (
        ("window_closed", PublishStatus.FAILED, "DOUYIN_WINDOW_CLOSED"),
        ("captcha", PublishStatus.FAILED, "DOUYIN_CHALLENGE_REQUIRED"),
        ("unknown", PublishStatus.FAILED, "DOUYIN_PAGE_CHANGED"),
    ):
        context = FixtureDouyinContext(transition_state=transition_state)
        result = await DouyinPublisher(FixtureDouyinRuntime(context)).prepare_draft(_package())
        assert result.status is expected_status
        assert result.message == expected_message


@pytest.mark.asyncio
async def test_douyin_adapter_rejects_cross_platform_package_before_browser_launch():
    class Runtime:
        async def launch_persistent_context(self, _platform):
            raise AssertionError("cross-platform package must be rejected before launch")

    package = _package().model_copy(update={"platform": "xiaohongshu"})
    with pytest.raises(ValueError, match="Publish package platform mismatch"):
        await DouyinPublisher(Runtime()).prepare_draft(package)


@pytest.mark.asyncio
async def test_stateful_checkpoint_captures_evidence_and_does_not_reupload_on_resume(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"")
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"cover-fixture")
    package = _package().model_copy(update={"video_path": str(video), "cover_path": str(cover)})
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        media_sha256="sha256:" + "b" * 64,
    )
    context = FixtureDouyinContext()
    callbacks = []

    async def callback(updated, stage, blocker):
        callbacks.append((updated, stage, blocker))

    publisher = DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
        checkpoint_callback=callback,
    )
    result = await publisher.prepare_draft(package)
    assert result.status is PublishStatus.DRAFT_READY
    assert publisher.checkpoint is not None
    assert publisher.checkpoint.topic_entities
    assert publisher.checkpoint.cover_receipts
    assert PublishStage.VERIFY in publisher.checkpoint.completed_stages
    upload_count = sum(1 for action in context.actions if isinstance(action, tuple) and action[0] == "video")

    resumed = await publisher.prepare_draft(package)
    assert resumed.status is PublishStatus.DRAFT_READY
    assert sum(1 for action in context.actions if isinstance(action, tuple) and action[0] == "video") == upload_count
    assert callbacks


@pytest.mark.asyncio
async def test_stateful_checkpoint_blocks_without_cover_receipt(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"")
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"cover-fixture")
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        media_sha256="sha256:" + "b" * 64,
    )
    context = FixtureDouyinContext(cover_receipt=False)
    callbacks = []

    def callback(updated, stage, blocker):
        callbacks.append((updated, stage, blocker))

    result = await DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
        checkpoint_callback=callback,
    ).prepare_draft(_package().model_copy(update={"video_path": str(video), "cover_path": str(cover)}))
    assert result.status is PublishStatus.FAILED
    assert result.message == "DOUYIN_COVER_RECEIPT_READBACK_FAILED"
    assert callbacks[-1][2] == "COVER_READBACK_MISMATCH"


@pytest.mark.asyncio
async def test_cover_receipt_accepts_known_upload_to_editor_route_transition(tmp_path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"cover-fixture")

    class RouteTransitionContext(FixtureDouyinContext):
        async def read_cover_receipt(self, _path):
            return {
                "before_urls": ["https://cdn.example/old-cover.png"],
                "accepted_url": "https://cdn.example/new-cover.png",
                "task_space_id": 101,
                "task_space_name": "douyin:https://creator.douyin.com/creator-micro/content/upload",
            }

    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_ref_douyin",
            task_space_id=101,
            task_space_name="douyin:https://creator.douyin.com/creator-micro/content/post/video",
            page_fingerprint="sha256:" + "a" * 64,
            media_identity="sha256:" + "f" * 64,
        ),
        completed_stages=[PublishStage.INSPECT, PublishStage.UPLOAD, PublishStage.WAIT],
        last_stage=PublishStage.WAIT,
        upload_mode=UploadMode.INJECTED,
        media_sha256="sha256:" + "b" * 64,
    )
    context = RouteTransitionContext()
    publisher = DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
    )
    evidence = await publisher._read_cover_evidence(
        context,
        str(cover),
    )
    assert evidence and evidence[0].task_space_id == 101


@pytest.mark.asyncio
async def test_cover_receipt_rejects_cross_id_same_editor_route(tmp_path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"cover-fixture")

    class ForeignDraftContext(FixtureDouyinContext):
        async def read_cover_receipt(self, _path):
            return {
                "before_urls": [],
                "accepted_url": "https://cdn.example/foreign-cover.png",
                "task_space_id": 202,
                "task_space_name": "douyin:https://creator.douyin.com/creator-micro/content/editor",
            }

    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_ref_douyin",
            task_space_id=101,
            task_space_name="douyin:https://creator.douyin.com/creator-micro/content/editor",
            page_fingerprint="sha256:" + "a" * 64,
        ),
    )
    context = ForeignDraftContext()
    evidence = await DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
    )._read_cover_evidence(context, str(cover))
    assert evidence is None


@pytest.mark.asyncio
async def test_cover_receipt_rejects_same_id_foreign_editor_name(tmp_path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"cover-fixture")

    class ForeignNameContext(FixtureDouyinContext):
        async def read_cover_receipt(self, _path):
            return {
                "before_urls": [],
                "accepted_url": "https://cdn.example/foreign-cover.png",
                "task_space_id": 101,
                "task_space_name": "douyin:https://evil.example/creator-micro/content/editor",
            }

    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_ref_douyin",
            task_space_id=101,
            task_space_name="douyin:https://creator.douyin.com/creator-micro/content/editor",
            page_fingerprint="sha256:" + "a" * 64,
        ),
    )
    context = ForeignNameContext()
    evidence = await DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
    )._read_cover_evidence(context, str(cover))
    assert evidence is None


@pytest.mark.asyncio
async def test_checkpoint_rejects_cross_id_same_editor_route():
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_ref_douyin",
            task_space_id=101,
            task_space_name="douyin:https://creator.douyin.com/creator-micro/content/post/video",
            page_fingerprint="sha256:" + "a" * 64,
        ),
    )
    callbacks = []
    publisher = DouyinPublisher(
        FixtureDouyinRuntime(FixtureDouyinContext()),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
        checkpoint_callback=lambda updated, stage, blocker: callbacks.append(
            (updated, stage, blocker)
        ),
    )
    with pytest.raises(RuntimeError, match="FOREIGN_DRAFT"):
        await publisher._checkpoint(
            PublishStage.INSPECT,
            page_fingerprint="sha256:" + "b" * 64,
            task_space_id=202,
            task_space_name="douyin:https://creator.douyin.com/creator-micro/content/editor",
        )
    assert callbacks[-1][2] == PublishBlockerCode.FOREIGN_DRAFT.value


@pytest.mark.asyncio
async def test_restart_auth_blocker_resets_old_prefix_before_persisting_inspect_blocker():
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_ref_douyin",
            task_space_id=101,
            task_space_name="douyin:fixture-editor",
            page_fingerprint="sha256:" + "a" * 64,
            media_identity="sha256:" + "f" * 64,
        ),
        completed_stages=[PublishStage.INSPECT, PublishStage.UPLOAD, PublishStage.WAIT],
        last_stage=PublishStage.WAIT,
        upload_mode=UploadMode.INJECTED,
        media_sha256="sha256:" + "b" * 64,
    )
    callbacks = []

    def callback(updated, stage, blocker):
        callbacks.append((updated, stage, blocker))

    result = await DouyinPublisher(
        FixtureDouyinRuntime(FixtureDouyinContext("signed_out")),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
        checkpoint_callback=callback,
    ).prepare_draft(_package())
    assert result.status is PublishStatus.LOGIN_REQUIRED
    saved, stage, blocker = callbacks[-1]
    assert saved.completed_stages == []
    assert saved.blocked_stage is PublishStage.INSPECT
    assert stage is PublishStage.INSPECT
    assert blocker == PublishBlockerCode.AUTH_REQUIRED.value


@pytest.mark.asyncio
async def test_foreign_fingerprint_is_typed_and_does_not_start_upload():
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_ref_douyin",
            task_space_id=101,
            task_space_name="douyin:fixture-editor",
            page_fingerprint="sha256:" + "a" * 64,
        ),
        completed_stages=[PublishStage.INSPECT],
        last_stage=PublishStage.INSPECT,
    )
    context = FixtureDouyinContext(fingerprint="sha256:" + "c" * 64)
    callbacks = []

    def callback(updated, stage, blocker):
        callbacks.append((updated, stage, blocker))

    result = await DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
        checkpoint_callback=callback,
    ).prepare_draft(_package())
    assert result.message == "DOUYIN_FOREIGN_DRAFT"
    assert not any(isinstance(action, tuple) and action[0] == "video" for action in context.actions)
    assert callbacks[-1][2] == PublishBlockerCode.FOREIGN_DRAFT.value


@pytest.mark.asyncio
async def test_mid_upload_auth_expiry_resets_prefix_before_waiting_for_login(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"")
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        media_sha256="sha256:" + "b" * 64,
    )
    context = FixtureDouyinContext(transition_state="signed_out")
    callbacks = []

    def callback(updated, stage, blocker):
        callbacks.append((updated, stage, blocker))

    result = await DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
        checkpoint_callback=callback,
    ).prepare_draft(_package().model_copy(update={"video_path": str(video), "hashtags": [], "cover_path": ""}))
    assert result.status is PublishStatus.LOGIN_REQUIRED
    assert callbacks[-1][0].completed_stages == []
    assert callbacks[-1][2] == PublishBlockerCode.AUTH_REQUIRED.value


@pytest.mark.asyncio
async def test_resume_rejects_same_page_with_different_uploaded_media(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"")
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_ref_douyin",
            task_space_id=101,
            task_space_name="douyin:fixture-editor",
            page_fingerprint="sha256:" + "a" * 64,
            media_identity="sha256:" + "f" * 64,
        ),
        completed_stages=[PublishStage.INSPECT, PublishStage.UPLOAD],
        last_stage=PublishStage.UPLOAD,
        upload_mode=UploadMode.INJECTED,
        media_sha256="sha256:" + "b" * 64,
    )

    class DifferentMediaContext(FixtureDouyinContext):
        async def uploaded_media_metadata(self):
            return {"name": "other.mp4", "size": 0, "type": "video/mp4"}

    context = DifferentMediaContext(state="editor_ready")
    callbacks = []

    def callback(updated, stage, blocker):
        callbacks.append((updated, stage, blocker))

    result = await DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
        checkpoint_callback=callback,
    ).prepare_draft(_package().model_copy(update={"video_path": str(video), "hashtags": [], "cover_path": ""}))
    assert result.message == "DOUYIN_MEDIA_IDENTITY_MISMATCH"
    assert not any(isinstance(action, tuple) and action[0] == "video" for action in context.actions)
    assert callbacks[-1][2] == PublishBlockerCode.STATE_AMBIGUOUS.value


@pytest.mark.asyncio
async def test_restart_with_preview_but_cleared_file_input_reuses_upload_without_reinject(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"")
    checkpoint = PublishExecutionCheckpoint(
        package_fingerprint="sha256:" + "e" * 64,
        account_id="acct_1",
        platform="douyin",
        attempt=1,
        runtime_kind="playwright",
        draft_identity=DraftIdentity(
            runtime_kind="playwright",
            profile_ref="profile_ref_douyin",
            task_space_id=101,
            task_space_name="douyin:fixture-editor",
            page_fingerprint="sha256:" + "a" * 64,
            media_identity="sha256:" + "f" * 64,
            remote_media_identity="sha256:" + hashlib.sha256(b"remote-media-1").hexdigest(),
        ),
        completed_stages=[PublishStage.INSPECT, PublishStage.UPLOAD, PublishStage.WAIT],
        last_stage=PublishStage.WAIT,
        upload_mode=UploadMode.INJECTED,
        media_sha256="sha256:" + "b" * 64,
    )

    class RestartedPreviewContext(FixtureDouyinContext):
        async def uploaded_media_metadata(self):
            return None

        async def read_remote_media_identity(self):
            return "remote-media-1"

    context = RestartedPreviewContext(state="editor_ready")
    result = await DouyinPublisher(
        FixtureDouyinRuntime(context),
        account_id="acct_1",
        profile_ref="profile_ref_douyin",
        checkpoint=checkpoint,
        checkpoint_callback=lambda *_args: None,
    ).prepare_draft(
        _package().model_copy(update={"video_path": str(video), "hashtags": [], "cover_path": ""})
    )
    assert result.status is PublishStatus.DRAFT_READY
    assert not any(isinstance(action, tuple) and action[0] == "video" for action in context.actions)


@pytest.mark.asyncio
async def test_playwright_context_closed_page_maps_to_window_closed_and_blocks_action():
    class ClosedPage:
        def is_closed(self):
            return True

    context = PlaywrightPublishContext(object(), "douyin")
    context.page = ClosedPage()
    assert await context.detect_state() == "window_closed"
    assert await context.page_fingerprint() == "sha256:window_closed"
    with pytest.raises(RuntimeError, match="DOUYIN_PAGE_FINGERPRINT_REQUIRED"):
        await context.guard_action("fill_title")


@pytest.mark.asyncio
async def test_playwright_context_reads_selected_douyin_topic_with_captured_cid():
    class SemanticNode:
        async def get_attribute(self, name):
            return {"data-mention": "#", "data-id": ""}.get(name)

        async def inner_text(self):
            return "#问答"

    class SemanticLocator:
        async def count(self):
            return 1

        def nth(self, _index):
            return SemanticNode()

    class SemanticPage:
        def locator(self, _selector):
            return SemanticLocator()

    context = PlaywrightPublishContext(object(), "douyin")
    context.page = SemanticPage()
    context._topic_entity_ids["问答"] = "1583698233265166"
    assert await context.read_topic_entities() == [
        {
            "label": "#问答",
            "normalized_label": "问答",
            "mention_type": "#",
            "entity_id": "1583698233265166",
        }
    ]


@pytest.mark.asyncio
async def test_playwright_context_challenge_overlay_overrides_editor_state():
    class Body:
        first = None

        async def get_attribute(self, name):
            return {"data-state": "editor_ready", "data-auth-state": "signed_in"}.get(name)

    Body.first = Body()

    class Locator:
        async def count(self):
            return 0

    class VisibleChallengeLocator:
        def nth(self, _index):
            return self

        async def count(self):
            return 1

        async def is_visible(self):
            return True

    class ChallengePage:
        url = "https://creator.douyin.com/creator-micro/content/post/video"

        def is_closed(self):
            return False

        def locator(self, selector):
            return Body.first if selector == "body" else Locator()

        def get_by_text(self, _text, *, exact=False):
            del exact
            return VisibleChallengeLocator()

        async def content(self):
            return "<main data-state='editor_ready'>风险验证</main>"

    context = PlaywrightPublishContext(object(), "douyin")
    context.page = ChallengePage()
    assert await context.detect_state() == "captcha"


@pytest.mark.asyncio
async def test_shared_playwright_context_keeps_non_douyin_legacy_actions_available():
    class LegacyPage:
        @property
        def first(self):
            return self

        async def fill(self, _value):
            return None

        async def count(self):
            return 1

        def locator(self, _selector):
            return self

    class RuntimeContext:
        def __init__(self):
            self.page = LegacyPage()

        def locator(self, _selector):
            return self.page

    context = PlaywrightPublishContext(RuntimeContext(), "xiaohongshu")
    context.page = RuntimeContext().page
    assert await context.fill_title("夏季新品") is True
