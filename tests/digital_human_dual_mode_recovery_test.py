import asyncio
from pathlib import Path

import pytest

from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
    IpBroadcastSessionError,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.ip_broadcast_workflow import (
    IpBroadcastSession,
    IpBroadcastSessionStore,
    _run_digital_human,
)


def _payload(project_id: str) -> dict:
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
            "publish_description": "先保留证据，再按流程处理。",
            "cover_title": "门店纠纷先留证",
            "hashtags": ["门店经营"],
        },
    }


def _adapter(tmp_path: Path, revision: dict[str, str]):
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
                "revision_id": revision["value"],
                "mime_type": "image/jpeg",
                "width": 1080,
                "height": 1920,
            },
            {"media_type": "image", "profile_id": "portrait-a"},
        ),
    )
    return repository, project, adapter


def test_recovery_rejects_asset_revision_change_before_local_execution(tmp_path: Path):
    revision = {"value": "revision-a"}
    repository, project, adapter = _adapter(tmp_path, revision)
    created = adapter.create_or_resume(
        project.project_id,
        _payload(project.project_id),
        idempotency_key="dh-recovery-revision",
    )
    revision["value"] = "revision-b"
    with pytest.raises(IpBroadcastSessionError, match="DH_QUALITY_FIXED_INPUT_MUTATED"):
        asyncio.run(adapter.execute_local(created.run.app_run_id))
    assert repository.list_attempts(created.run.app_run_id) == []


def test_recovery_running_restart_keeps_task_identity_and_requires_plan(tmp_path: Path):
    revision = {"value": "revision-a"}
    repository, project, adapter = _adapter(tmp_path, revision)
    created = adapter.create_or_resume(
        project.project_id,
        _payload(project.project_id),
        idempotency_key="dh-recovery-running",
    )
    session = adapter.session_store.get_session(created.binding.session_id)
    assert session is not None
    session.state["provider_task_id"] = "provider-task-running"
    session.state["provider_task_status"] = "running"
    adapter.session_store.save_session(session)
    repository.transition_app_run(created.run.app_run_id, "queued")
    running = repository.transition_app_run(created.run.app_run_id, "running")
    attempt = repository.create_attempt(running.app_run_id)
    repository.update_attempt(attempt.attempt_id, state="running", started_at=running.updated_at)
    recovered = asyncio.run(adapter.execute_local(created.run.app_run_id))
    assert recovered.run.state == "failed"
    assert recovered.run.error_code == "APP_EXECUTOR_INTERRUPTED"
    persisted = adapter.session_store.get_session(created.binding.session_id)
    assert persisted is not None
    assert persisted.state["provider_task_id"] == "provider-task-running"
    with pytest.raises(IpBroadcastSessionError, match="DH_QUALITY_RETRY_PLAN_REQUIRED"):
        adapter.retry(created.run.app_run_id)


def test_recovery_needs_review_restart_preserves_four_artifacts(tmp_path: Path):
    revision = {"value": "revision-a"}
    repository, project, adapter = _adapter(tmp_path, revision)
    created = adapter.create_or_resume(
        project.project_id,
        _payload(project.project_id),
        idempotency_key="dh-recovery-review",
    )
    reviewed = asyncio.run(adapter.execute_local(created.run.app_run_id))
    assert reviewed.run.state == "needs_review"
    restarted = IpBroadcastAppAdapter(
        repository,
        session_store=adapter.session_store,
        binding_store=IpBroadcastBindingStore(adapter.binding_store._path),
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
    recovered = asyncio.run(restarted.execute_local(created.run.app_run_id))
    assert recovered.run.output_artifact_ids == reviewed.run.output_artifact_ids
    assert set(recovered.session.artifacts) >= {"video", "cover", "publish_copy", "spoken_script"}
    accepted = restarted.accept_local_outputs(created.run.app_run_id)
    assert accepted.run.state == "completed"


def test_failed_v2_execution_requires_retry_plan(tmp_path: Path):
    revision = {"value": "revision-a"}
    repository, project, adapter = _adapter(tmp_path, revision)
    created = adapter.create_or_resume(
        project.project_id,
        _payload(project.project_id),
        idempotency_key="dh-recovery-failed-guard",
    )
    repository.transition_app_run(created.run.app_run_id, "queued")
    repository.transition_app_run(created.run.app_run_id, "running")
    repository.transition_app_run(created.run.app_run_id, "failed")
    with pytest.raises(IpBroadcastSessionError, match="DH_QUALITY_RETRY_PLAN_REQUIRED"):
        asyncio.run(adapter.execute_local(created.run.app_run_id))
    with pytest.raises(IpBroadcastSessionError, match="DH_QUALITY_RETRY_PLAN_REQUIRED"):
        adapter.retry(created.run.app_run_id)


def test_recovery_rejects_incomplete_v2_artifact_set_before_accept(tmp_path: Path):
    revision = {"value": "revision-a"}
    repository, project, adapter = _adapter(tmp_path, revision)
    created = adapter.create_or_resume(
        project.project_id,
        _payload(project.project_id),
        idempotency_key="dh-recovery-incomplete",
    )
    reviewed = asyncio.run(adapter.execute_local(created.run.app_run_id))
    incomplete = [
        artifact_id
        for artifact_id in reviewed.run.output_artifact_ids
        if repository.get_artifact(artifact_id).artifact_type != "spoken_script"
    ]
    repository.set_output_artifacts(created.run.app_run_id, incomplete)
    with pytest.raises(IpBroadcastSessionError, match="DH_QUALITY_FINAL_ARTIFACT_INCOMPLETE"):
        adapter.accept_local_outputs(created.run.app_run_id)


def test_recovery_provider_failure_persists_task_and_safe_retry_boundary(tmp_path: Path):
    audio = tmp_path / "audio.mp3"
    portrait = tmp_path / "portrait.png"
    audio.write_bytes(b"audio")
    portrait.write_bytes(b"portrait")

    class _Provider:
        last_generation_meta = {"provider_task_id": "provider-timeout-1"}

        async def generate(self, **_kwargs):
            raise RuntimeError("provider timeout")

    class _Core:
        digital_human = _Provider()

    session = IpBroadcastSession(
        session_id="provider-failure",
        state={
            "audio_path": str(audio),
            "portrait_path": str(portrait),
            "portrait_media_type": "image",
            "digital_human_workflow": "workflows/runninghub/digital_combination.json",
        },
    )
    with pytest.raises(RuntimeError, match="provider timeout"):
        asyncio.run(_run_digital_human(_Core(), session))
    assert session.state["provider_task_id"] == "provider-timeout-1"
    assert session.state["provider_task_status"] == "retryable_failed"
    assert session.state["provider_retry_plan"]["approved"] is False
