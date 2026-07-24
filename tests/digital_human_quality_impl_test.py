import asyncio
import json
from pathlib import Path

import pytest

from pixelle_video.app_center.digital_human_input import (
    DigitalHumanInputError,
    normalize_digital_human_input,
)
from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
    IpBroadcastSessionError,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.ip_broadcast_templates import (
    build_ass_force_style,
    get_ip_broadcast_template_for_render,
)
from pixelle_video.services.ip_broadcast_workflow import (
    IpBroadcastSession,
    IpBroadcastSessionStore,
    _build_cover_title,
    _run_digital_human,
    _write_quality_evidence,
)


def _payload(project_id: str = "project-a") -> dict:
    return {
        "schema_version": 2,
        "app_version": "1.1.0",
        "project_id": project_id,
        "content_source": {
            "mode": "custom_script",
            "script": "打架先动手和后动手有什么区别？门店纠纷先保留证据，再按流程处理。",
        },
        "digital_human": {
            "mode": "image_talking",
            "portrait_id": "portrait-a",
            "scene_id": "scene-a",
            "asset_revision_id": "revision-a",
            "workflow_profile": "stable",
        },
        "delivery": {
            "publish_title": "门店纠纷怎么处理",
            "publish_description": "先保留证据，再按流程处理，门店老板可以这样做。",
            "cover_title": "门店纠纷先留证",
            "hashtags": ["门店经营", "老板经验"],
            "subtitle_preset": "readable_v2",
            "subtitle_enabled": True,
        },
    }


def test_quality_delivery_normalizes_aliases_and_strips_tags():
    payload = _payload()
    payload["content_source"] = {
        "mode": "marketing_copy_artifact",
        "source_artifact_version_id": "copy-1",
        "selected_variant_index": 0,
    }
    normalized = normalize_digital_human_input(payload, project_id="project-a")
    assert normalized.payload["content_source"]["mode"] == "copywriting_artifact"
    assert normalized.payload["delivery"]["hashtags"] == ["门店经营", "老板经验"]


@pytest.mark.parametrize(
    ("delivery", "error"),
    [
        (
            {"cover_title": "这是一条超过二十四个显示字符硬上限的封面标题示例"},
            "DH_QUALITY_COVER_TITLE_TOO_LONG",
        ),
        (
            {"cover_title": "第一行标题文字必须明显超过十二个字\n第二行标题文字也必须超过十二个字"},
            "DH_QUALITY_COVER_TITLE_TOO_LONG",
        ),
        (
            {
                "cover_subtitle": "这是一条封面副标题文字，长度明显超过二十八个显示字符上限，需要被拦截"
            },
            "DH_QUALITY_COVER_SUBTITLE_TOO_LONG",
        ),
        ({"subtitle_preset": "legacy"}, "DH_QUALITY_SUBTITLE_PRESET_REQUIRED"),
        ({"hashtags": ["门店", "  "]}, "DIGITAL_HUMAN_DELIVERY_INVALID"),
    ],
)
def test_quality_delivery_rejects_unsafe_copy_or_cover_fields(delivery, error):
    payload = _payload()
    payload["delivery"] = delivery
    with pytest.raises(DigitalHumanInputError, match=error):
        normalize_digital_human_input(payload, project_id="project-a")


def test_custom_script_does_not_accept_goal_alias():
    payload = _payload()
    payload["content_source"] = {"mode": "custom_script", "goal": "只提供目标"}
    with pytest.raises(DigitalHumanInputError, match="DH_QUALITY_CUSTOM_SCRIPT_MUTATION"):
        normalize_digital_human_input(payload, project_id="project-a")


def test_v2_adapter_pins_delivery_and_spoken_script_into_session(tmp_path: Path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    payload = _payload(project.project_id)
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        dual_backend_flag=True,
        dual_desktop_flag=True,
        dual_desktop_ready=True,
        digital_human_asset_resolver=lambda _scene_id: (
            {
                "media_type": "image",
                "status": "ready",
                "revision_id": "revision-a",
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image", "profile_id": "portrait-a"},
        ),
    )
    created = adapter.create_or_resume(
        project.project_id, payload, idempotency_key="quality-delivery-1"
    )
    session = created.session
    assert session.state["spoken_script"] == payload["content_source"]["script"]
    assert session.state["title"] == payload["delivery"]["publish_title"]
    assert session.state["description"] == payload["delivery"]["publish_description"]
    assert session.state["cover_title"] == payload["delivery"]["cover_title"]
    assert session.state["hashtags"] == payload["delivery"]["hashtags"]
    assert session.state["subtitle_preset"] == "readable_v2"
    assert created.run.input_payload["delivery"]["subtitle_preset"] == "readable_v2"


def test_readable_v2_force_style_is_explicitly_large_and_safe():
    template = get_ip_broadcast_template_for_render("boss_clean")
    style = build_ass_force_style(
        template,
        {"font_size": 48, "outline": 3, "margin_v": 190},
        video_width=1080,
        video_height=1920,
    )
    assert "Fontsize=48" in style
    assert "Outline=3" in style
    assert "MarginV=190" in style


def test_readable_v2_cover_fallback_is_short_and_not_script_prefix():
    session = IpBroadcastSession(
        session_id="cover-quality",
        state={
            "subtitle_preset": "readable_v2",
            "final_script": "打架先动手和后动手有什么区别？门店纠纷先保留证据，再按流程处理。",
            "title": "这是一条非常非常非常长的发布标题，不能直接拿来做封面",
            "business_goal_name": "门店探店",
        },
    )
    cover_title = _build_cover_title(session)
    assert cover_title == "到店前先看这件事"
    assert len(cover_title) <= 24
    assert not cover_title.startswith("打架先动手")


def test_v2_local_review_requires_complete_four_artifact_delivery(tmp_path: Path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        dual_backend_flag=True,
        dual_desktop_flag=True,
        dual_desktop_ready=True,
        digital_human_asset_resolver=lambda _scene_id: (
            {
                "media_type": "image",
                "status": "ready",
                "revision_id": "revision-a",
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image", "profile_id": "portrait-a"},
        ),
    )
    created = adapter.create_or_resume(
        project.project_id,
        _payload(project.project_id),
        idempotency_key="quality-four-artifacts",
    )
    result = asyncio.run(adapter.execute_local(created.run.app_run_id))
    assert result.run.state == "needs_review"
    artifact_types = {
        repository.get_artifact(artifact_id).artifact_type
        for artifact_id in result.run.output_artifact_ids
    }
    assert artifact_types == {"video", "cover", "publish_copy", "spoken_script"}
    accepted = adapter.accept_local_outputs(created.run.app_run_id)
    assert accepted.run.state == "completed"


def test_quality2_scheduler_tick_does_not_duplicate_existing_provider_video(tmp_path: Path):
    existing = tmp_path / "existing.mp4"
    existing.write_bytes(b"video")

    class _Provider:
        def __init__(self):
            self.calls = 0

        async def generate(self, **_kwargs):
            self.calls += 1
            return str(existing)

    class _Core:
        digital_human = _Provider()

    session = IpBroadcastSession(
        session_id="dedupe",
        state={
            "digital_human_video_path": str(existing),
            "audio_path": str(existing),
            "portrait_path": str(existing),
            "digital_human_workflow": "workflows/runninghub/digital_combination.json",
        },
    )
    asyncio.run(_run_digital_human(_Core(), session))
    assert _Core.digital_human.calls == 0


def test_quality2_scheduler_rejects_existing_provider_task_without_retry_plan(tmp_path: Path):
    existing = tmp_path / "existing.mp3"
    existing.write_bytes(b"audio")

    class _Provider:
        last_generation_meta = {}

        async def generate(self, **_kwargs):
            raise AssertionError("provider must not be called for an existing task")

    class _Core:
        digital_human = _Provider()

    session = IpBroadcastSession(
        session_id="duplicate-task",
        state={
            "digital_human_video_path": "",
            "provider_task_id": "provider-task-in-flight",
            "provider_task_status": "running",
            "audio_path": str(existing),
            "portrait_path": str(existing),
            "digital_human_workflow": "workflows/runninghub/digital_combination.json",
        },
    )
    with pytest.raises(ValueError, match="DH_QUALITY_PROVIDER_DUPLICATE_TASK"):
        asyncio.run(_run_digital_human(_Core(), session))


def test_quality2_evidence_records_hashes_and_closed_publish_boundary(tmp_path: Path, monkeypatch):
    video = tmp_path / "final.mp4"
    cover = tmp_path / "cover.png"
    raw = tmp_path / "raw.mp4"
    video.write_bytes(b"final")
    cover.write_bytes(b"cover")
    raw.write_bytes(b"raw")
    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_workflow.get_output_path",
        lambda name: str(tmp_path / name),
    )
    session = IpBroadcastSession(
        session_id="quality-evidence",
        state={
            "subtitle_preset": "readable_v2",
            "final_video_path": str(video),
            "cover_path": str(cover),
            "digital_human_video_path": str(raw),
            "spoken_script": "完整门店营销口播文案。",
            "provider_task_id": "provider-task-1",
            "provider_task_create_count": 1,
        },
        artifacts={
            "final_video": str(video),
            "cover": str(cover),
            "publish_package_json": str(tmp_path / "publish.json"),
        },
    )
    _write_quality_evidence(session)
    evidence = json.loads(
        Path(session.artifacts["quality_evidence_json"]).read_text(encoding="utf-8")
    )
    assert evidence["provider_task_id"] == "provider-task-1"
    assert evidence["provider_task_create_count"] == 1
    assert evidence["final_publish_clicked"] is False
    assert evidence["final_video"]["sha256"]
    assert evidence["frame_samples"]["status"] == "unavailable"


def test_quality2_retry_requires_plan_and_is_limited_to_one(tmp_path: Path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        dual_backend_flag=True,
        dual_desktop_flag=True,
        dual_desktop_ready=True,
        digital_human_asset_resolver=lambda _scene_id: (
            {
                "media_type": "image",
                "status": "ready",
                "revision_id": "revision-a",
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image", "profile_id": "portrait-a"},
        ),
    )
    created = adapter.create_or_resume(
        project.project_id, _payload(project.project_id), idempotency_key="quality-retry-plan"
    )
    repository.transition_app_run(created.run.app_run_id, "queued")
    repository.transition_app_run(created.run.app_run_id, "running")
    failed = repository.transition_app_run(created.run.app_run_id, "failed")
    session = adapter.session_store.get_session(created.binding.session_id)
    assert session is not None
    session.state["provider_task_id"] = "provider-failed-1"
    session.state["provider_task_status"] = "retryable_failed"
    adapter.session_store.save_session(session)
    with pytest.raises(IpBroadcastSessionError, match="DH_QUALITY_RETRY_PLAN_REQUIRED"):
        adapter.retry(failed.app_run_id)
    adapter.prepare_provider_retry(
        failed.app_run_id,
        root_cause="输入节点映射错误",
        retry_reason="已修正节点映射，沿用同一份文案和资产",
    )
    retried = adapter.retry(failed.app_run_id)
    assert retried.run.state == "queued"
    assert retried.session.state["provider_retry_count"] == 1
    repository.transition_app_run(retried.run.app_run_id, "running")
    failed_again = repository.transition_app_run(retried.run.app_run_id, "failed")
    with pytest.raises(IpBroadcastSessionError, match="DH_QUALITY_RETRY_LIMIT"):
        adapter.retry(failed_again.app_run_id)
