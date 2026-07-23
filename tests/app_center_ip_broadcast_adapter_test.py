import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest

from api.tasks.manager import TaskManager
from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAdapterError,
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
    IpBroadcastInputError,
    IpBroadcastSessionError,
    project_legacy_state,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.runner import ExecutorOutput, RelatedArtifactOutput
from pixelle_video.app_center.task_projection import AppRunTaskProjector
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore


def _copywriting_content():
    return {
        "schema_version": 1,
        "artifact_type": "copywriting",
        "variants": [
            {
                "version_name": "门店口播",
                "angle": "场景",
                "hook": "路过别错过",
                "body": "今天到店有活动",
                "cta": "欢迎来店咨询",
                "full_text": "路过别错过，今天到店有活动，欢迎来店咨询。",
                "word_count": 23,
                "estimated_seconds": 6,
            },
            {
                "version_name": "优惠口播",
                "angle": "利益",
                "hook": "进店先看这件事",
                "body": "到店可以先了解服务",
                "cta": "欢迎进店",
                "full_text": "进店先看这件事，到店可以先了解服务，欢迎进店。",
                "word_count": 25,
                "estimated_seconds": 7,
            },
            {
                "version_name": "服务口播",
                "angle": "身份",
                "hook": "老板们可以这样做",
                "body": "把到店服务讲清楚",
                "cta": "欢迎来店了解",
                "full_text": "老板们可以这样做，把到店服务讲清楚，欢迎来店了解。",
                "word_count": 26,
                "estimated_seconds": 7,
            },
        ],
        "missing_facts": [],
        "risk_flags": [],
    }


@pytest.fixture
def harness(tmp_path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("门店项目", "到店咨询")
    copywriting = repository.create_artifact(project.project_id, "copywriting", "门店文案")
    copy_version = repository.append_artifact_version(copywriting.artifact_id, content=_copywriting_content())
    title = repository.create_artifact(project.project_id, "selected_title", "门店标题")
    title_version = repository.append_artifact_version(title.artifact_id, content={"title": "到店前先看这件事"})
    sessions = IpBroadcastSessionStore(tmp_path / "legacy-sessions")
    bindings = IpBroadcastBindingStore(tmp_path / "bindings.json")
    # The real adapter is flag-gated; tests explicitly opt into the local
    # implementation seam without changing the product default.
    adapter = IpBroadcastAppAdapter(repository, session_store=sessions, binding_store=bindings, enforce_feature_flag=False)
    return repository, project, copy_version, title_version, sessions, bindings, adapter


def test_create_blank_binds_session_and_replays_idempotently(harness):
    _, project, _, _, _, _, adapter = harness
    first = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        idempotency_key="ip-blank-1",
    )
    replay = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        idempotency_key="ip-blank-1",
    )

    assert first.run.app_run_id == replay.run.app_run_id
    assert first.binding.session_id == replay.binding.session_id
    assert first.run.session_id == first.binding.session_id
    assert first.projection["app_run_state"] == "draft"


def test_production_adapter_is_fail_closed_when_feature_flag_is_off(harness, monkeypatch):
    repository, project, _, _, sessions, bindings, local = harness
    monkeypatch.delenv("PIXELLE_APP_CENTER_DIGITAL_HUMAN", raising=False)
    strict = IpBroadcastAppAdapter(repository, session_store=sessions, binding_store=bindings)
    with pytest.raises(IpBroadcastAdapterError, match="APP_FEATURE_DISABLED"):
        strict.create_or_resume(
            project.project_id,
            {"project_id": project.project_id, "source_mode": "blank_project", "goal": "默认关闭", "source_artifact_version_ids": []},
            idempotency_key="ip-flag-off-1",
        )
    retry_source = local.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "重试关闭", "source_artifact_version_ids": []},
        idempotency_key="ip-flag-off-retry",
    )
    repository.transition_app_run(retry_source.run.app_run_id, "queued")
    repository.transition_app_run(retry_source.run.app_run_id, "running")
    repository.transition_app_run(retry_source.run.app_run_id, "failed")
    with pytest.raises(IpBroadcastAdapterError, match="APP_FEATURE_DISABLED"):
        strict.retry(retry_source.run.app_run_id)

    complete_source = local.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "完成关闭", "source_artifact_version_ids": []},
        idempotency_key="ip-flag-off-complete",
    )
    asyncio.run(local.run_fake(complete_source.run.app_run_id))
    with pytest.raises(IpBroadcastAdapterError, match="APP_FEATURE_DISABLED"):
        asyncio.run(strict.accept_fake(complete_source.run.app_run_id))


def test_copywriting_and_selected_title_sources_are_project_pinned(harness):
    _, project, copy_version, title_version, _, _, adapter = harness
    copy_run = adapter.create_or_resume(
        project.project_id,
        {
            "source_mode": "copywriting",
            "source_artifact_version_ids": [copy_version.artifact_version_id],
            "selected_variant_index": 1,
        },
        idempotency_key="ip-copy-1",
    )
    assert copy_run.run.input_payload["selected_variant_index"] == 1
    assert copy_run.binding.source_revision.startswith("sha256:")

    title_run = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "selected_title", "source_artifact_version_ids": [title_version.artifact_version_id]},
        idempotency_key="ip-title-1",
    )
    assert title_run.run.input_payload["source_mode"] == "selected_title"

    with pytest.raises(IpBroadcastInputError, match="SOURCE_MODE_EXACTLY_ONE"):
        adapter.validate_input(
            project.project_id,
            {
                "source_mode": "copywriting",
                "source_artifact_version_ids": [copy_version.artifact_version_id, title_version.artifact_version_id],
                "selected_variant_index": 0,
            },
        )
    with pytest.raises(IpBroadcastInputError, match="COPYWRITING_VARIANT_REQUIRED"):
        adapter.validate_input(
            project.project_id,
            {"source_mode": "copywriting", "source_artifact_version_ids": [copy_version.artifact_version_id]},
        )

    with pytest.raises(IpBroadcastInputError, match="PROJECT_ID_MISMATCH"):
        adapter.validate_input(
            project.project_id,
            {"project_id": "another-project", "source_mode": "blank_project", "goal": "不一致", "source_artifact_version_ids": []},
        )


def test_resume_requires_explicit_claim_and_survives_restart(harness, tmp_path):
    repository, project, _, _, sessions, bindings, adapter = harness
    legacy = sessions.create_session()
    with pytest.raises(IpBroadcastSessionError, match="LEGACY_SESSION_EXPLICIT_CLAIM_REQUIRED"):
        adapter.create_or_resume(
            project.project_id,
            {"session_id": legacy.session_id, "resume_mode": "resume_existing"},
            idempotency_key="ip-resume-1",
        )

    resumed = adapter.create_or_resume(
        project.project_id,
        {"session_id": legacy.session_id, "resume_mode": "resume_existing"},
        idempotency_key="ip-resume-1",
        explicit_claim=True,
    )
    restarted = IpBroadcastAppAdapter(
        repository,
        session_store=IpBroadcastSessionStore(tmp_path / "legacy-sessions"),
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
    )
    recovered = restarted.reconcile(legacy.session_id, project_id=project.project_id)
    assert recovered.run.app_run_id == resumed.run.app_run_id
    assert recovered.run.session_id == legacy.session_id
    assert recovered.binding.explicit_claim is True
    assert bindings.get(legacy.session_id) is not None


def test_resume_cross_project_and_duplicate_active_session_fail_closed(harness):
    repository, project, _, _, sessions, _, adapter = harness
    other = repository.create_project("另一项目", "到店咨询")
    first = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        idempotency_key="ip-active-1",
    )
    with pytest.raises(IpBroadcastSessionError, match="SESSION_PROJECT_MISMATCH"):
        adapter.reconcile(first.binding.session_id, project_id=other.project_id)

    active_replay = adapter.create_or_resume(
        project.project_id,
        {"session_id": first.binding.session_id, "resume_mode": "resume_existing"},
        idempotency_key="ip-active-2",
    )
    assert active_replay.run.app_run_id == first.run.app_run_id

    assert sessions.get_session(first.binding.session_id) is not None


def test_bound_legacy_state_revision_drift_is_rejected_on_resume(harness):
    _, project, _, _, sessions, _, adapter = harness
    legacy = sessions.create_session()
    _created = adapter.create_or_resume(
        project.project_id,
        {"session_id": legacy.session_id, "resume_mode": "resume_existing"},
        idempotency_key="ip-state-revision-1",
        explicit_claim=True,
    )
    session = sessions.get_session(legacy.session_id)
    session.state["source_text"] = "外部修改"
    sessions.save_session(session)
    with pytest.raises(IpBroadcastSessionError, match="SESSION_STATE_REVISION_MISMATCH"):
        adapter.create_or_resume(
            project.project_id,
            {"session_id": legacy.session_id, "resume_mode": "resume_existing"},
            idempotency_key="ip-state-revision-2",
        )


def test_normal_runtime_state_progression_does_not_break_bound_resume(harness):
    _, project, _, _, sessions, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "正常推进", "source_artifact_version_ids": []},
        idempotency_key="ip-state-progress-1",
    )
    session = sessions.get_session(created.binding.session_id)
    session.state["final_script"] = "已生成脚本"
    session.state["audio_path"] = "generated-audio.wav"
    sessions.save_session(session)
    recovered = adapter.create_or_resume(
        project.project_id,
        {"session_id": created.binding.session_id, "resume_mode": "resume_existing"},
        idempotency_key="ip-state-progress-2",
    )
    assert recovered.run.app_run_id == created.run.app_run_id


def test_runtime_source_and_resume_revision_mismatch_fail_closed(harness):
    repository, project, copy_version, title_version, sessions, _, adapter = harness
    other = repository.create_project("另一项目", "到店咨询")
    other_title = repository.create_artifact(other.project_id, "selected_title", "另一项目标题")
    other_version = repository.append_artifact_version(other_title.artifact_id, content={"title": "不得跨项目"})
    with pytest.raises(IpBroadcastInputError, match="SOURCE_VERSION_PROJECT_MISMATCH"):
        adapter.validate_input(
            project.project_id,
            {"source_mode": "selected_title", "source_artifact_version_ids": [other_version.artifact_version_id]},
        )
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "copywriting", "source_artifact_version_ids": [copy_version.artifact_version_id], "selected_variant_index": 0},
        idempotency_key="ip-revision-1",
    )
    with pytest.raises(IpBroadcastSessionError, match="SOURCE_REVISION_MISMATCH"):
        adapter.create_or_resume(
            project.project_id,
            {"session_id": created.binding.session_id, "resume_mode": "resume_existing", "source_mode": "selected_title", "source_artifact_version_ids": [title_version.artifact_version_id]},
            idempotency_key="ip-revision-2",
        )
    assert sessions.get_session(created.binding.session_id) is not None


def test_optional_generic_task_projection_is_redacted_and_reconciled(harness, tmp_path):
    repository, project, _, _, _, _, _ = harness
    manager = TaskManager()
    projector = AppRunTaskProjector(manager)
    sessions = IpBroadcastSessionStore(tmp_path / "projected-sessions")
    bindings = IpBroadcastBindingStore(tmp_path / "projected-bindings.json")
    adapter = IpBroadcastAppAdapter(repository, session_store=sessions, binding_store=bindings, task_projector=projector, enforce_feature_flag=False)
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "任务投影", "source_artifact_version_ids": []},
        idempotency_key="ip-task-projection-1",
    )
    task = manager.list_tasks()[0]
    assert task.status.value == "pending"
    assert task.request_params is None
    assert task.source_fact_id == created.run.app_run_id
    task_session = sessions.get_session(created.binding.session_id)
    task_session.state["legacy_lifecycle_state"] = "waiting_for_human"
    sessions.save_session(task_session)
    adapter.reconcile(created.binding.session_id, project_id=project.project_id)
    assert manager.get_task(task.task_id).status.value == "waiting_for_human"
    assert manager.get_task(task.task_id).step_key == "waiting_for_human"
    task_session.state.pop("legacy_lifecycle_state")
    sessions.save_session(task_session)
    queued = repository.transition_app_run(created.run.app_run_id, "queued")
    adapter.reconcile(created.binding.session_id, project_id=project.project_id)
    assert manager.get_task(task.task_id).status.value == "pending"
    running = repository.transition_app_run(queued.app_run_id, "running")
    adapter.reconcile(created.binding.session_id, project_id=project.project_id)
    assert manager.get_task(task.task_id).status.value == "running"
    repository.transition_app_run(running.app_run_id, "failed")
    adapter.reconcile(created.binding.session_id, project_id=project.project_id)
    assert manager.get_task(task.task_id).status.value == "failed"


def test_fake_workflow_registers_outputs_and_completion_is_explicit(harness):
    _, project, _, _, _, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        idempotency_key="ip-fake-1",
    )
    reviewed = asyncio.run(adapter.run_fake(created.run.app_run_id))
    assert reviewed.run.state == "needs_review"
    assert set(reviewed.run.output_artifact_ids) == set(reviewed.session.artifacts.values())
    assert {"video", "cover", "publish_copy"} <= set(reviewed.session.artifacts)
    assert reviewed.projection["completion_allowed"] is False

    completed = asyncio.run(adapter.accept_fake(created.run.app_run_id))
    assert completed.run.state == "completed"
    assert completed.projection["completion_allowed"] is True
    assert completed.session.step_status[6] == "done"


def test_batch5_local_executor_reuses_run_session_task_and_outputs(harness):
    repository, project, _, _, sessions, _, adapter = harness
    manager = TaskManager()
    projector = AppRunTaskProjector(manager)
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=sessions,
        binding_store=adapter.binding_store,
        task_projector=projector,
        enforce_feature_flag=False,
    )
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "隔离 executor", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-local-1",
    )
    first = asyncio.run(adapter.execute_local(created.run.app_run_id))
    second = asyncio.run(adapter.execute_local(created.run.app_run_id))
    assert first.run.state == second.run.state == "needs_review"
    assert first.run.output_artifact_ids == second.run.output_artifact_ids
    assert len(repository.list_attempts(created.run.app_run_id)) == 1
    assert len([item for item in repository.list_artifacts(project.project_id) if item.source_app_run_id == created.run.app_run_id]) == 3
    session = sessions.get_session(created.binding.session_id)
    assert session is not None and session.step_status[6] == "ready"
    assert manager.list_tasks()[0].status.value == "needs_review"
    assert manager.list_tasks()[0].source_fact_id == created.run.app_run_id


def test_provider_executor_runs_real_media_boundary_and_stops_for_human_review(harness, tmp_path, monkeypatch):
    repository, project, _, _, sessions, bindings, _ = harness
    video_path = tmp_path / "generated.mp4"
    cover_path = tmp_path / "cover.png"
    video_path.write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00")
    cover_path.write_bytes(b"\x89PNG\r\n\x1a\nprovider-cover")

    async def fake_step(_core, session, step_key):
        if step_key == "postproduction":
            session.artifacts["final_video"] = str(video_path)
            session.artifacts["cover"] = str(cover_path)
            session.state["publish_package"] = {
                "title": "到店前先看这件事",
                "description": "门店活动介绍",
                "hashtags": ["门店营销"],
            }
        return True

    monkeypatch.setattr("pixelle_video.app_center.ip_broadcast_adapter.run_ip_broadcast_step", fake_step)
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=sessions,
        binding_store=bindings,
        enforce_feature_flag=False,
        trusted_roots=[tmp_path],
    )
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        idempotency_key="ip-provider-boundary-1",
    )
    reviewed = asyncio.run(adapter.execute_provider(created.run.app_run_id, object()))
    assert reviewed.run.state == "needs_review"
    assert {repository.get_artifact(item).artifact_type for item in reviewed.run.output_artifact_ids} == {"video", "cover", "publish_copy"}
    assert reviewed.session.step_status[6] == "ready"
    accepted = adapter.accept_generated_outputs(reviewed.run.app_run_id)
    assert accepted.run.state == "completed"
    assert accepted.session.step_status[6] == "done"
    replay = adapter.accept_generated_outputs(reviewed.run.app_run_id)
    assert replay.run.state == "completed"


def test_provider_executor_repairs_orphaned_running_attempt_after_restart(harness):
    repository, project, _, _, sessions, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "恢复 provider running", "source_artifact_version_ids": []},
        idempotency_key="ip-provider-restart-running-1",
    )
    repository.transition_app_run(created.run.app_run_id, "queued")
    running = repository.transition_app_run(created.run.app_run_id, "running")
    attempt = repository.create_attempt(running.app_run_id)
    repository.update_attempt(attempt.attempt_id, state="running", started_at=running.updated_at)

    recovered = asyncio.run(adapter.execute_provider(created.run.app_run_id, object()))

    assert recovered.run.state == "failed"
    assert recovered.run.error_code == "APP_EXECUTOR_INTERRUPTED"
    assert repository.list_attempts(created.run.app_run_id)[-1].state == "failed"
    session = sessions.get_session(created.binding.session_id)
    assert session is not None and session.step_status[6] == "error"


def test_batch5_local_executor_enforces_context_and_source_binding(harness):
    repository, project, _, _, _, _, adapter = harness
    snapshot = repository.save_context_snapshot(project.project_id, {"store_name": "隔离店"})
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "绑定校验", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-binding-1",
        context_snapshot_id=snapshot.context_snapshot_id,
    )
    with pytest.raises(IpBroadcastSessionError, match="APP_RUN_BINDING_MISMATCH"):
        asyncio.run(adapter.execute_local(created.run.app_run_id, context_snapshot_id="snapshot-other"))
    restarted = IpBroadcastAppAdapter(
        repository,
        session_store=adapter.session_store,
        binding_store=IpBroadcastBindingStore(adapter.binding_store._path),
        enforce_feature_flag=False,
    )
    assert restarted.binding_store.get(created.binding.session_id).context_snapshot_id == snapshot.context_snapshot_id
    with pytest.raises(IpBroadcastSessionError, match="SOURCE_REVISION_MISMATCH"):
        repository.update_app_run_draft(
            created.run.app_run_id,
            input_payload={"source_mode": "blank_project", "goal": "篡改", "source_revision": "sha256:other"},
            context_snapshot_id=snapshot.context_snapshot_id,
            session_id=created.binding.session_id,
        )
        asyncio.run(restarted.execute_local(created.run.app_run_id))


def test_batch5_idempotent_replay_rejects_context_snapshot_drift(harness):
    repository, project, _, _, _, _, adapter = harness
    first_snapshot = repository.save_context_snapshot(project.project_id, {"store_name": "第一版"})
    second_snapshot = repository.save_context_snapshot(project.project_id, {"store_name": "第二版"})
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "幂等上下文", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-context-replay-1",
        context_snapshot_id=first_snapshot.context_snapshot_id,
    )
    with pytest.raises(IpBroadcastSessionError, match="APP_RUN_BINDING_MISMATCH"):
        adapter.create_or_resume(
            project.project_id,
            {"source_mode": "blank_project", "goal": "幂等上下文", "source_artifact_version_ids": []},
            idempotency_key="ip-batch5-context-replay-1",
            context_snapshot_id=second_snapshot.context_snapshot_id,
        )
    assert repository.get_app_run(created.run.app_run_id).context_snapshot_id == first_snapshot.context_snapshot_id


def test_batch5_local_executor_failure_then_retry_preserves_history(harness):
    repository, project, _, _, sessions, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "失败重试", "source_artifact_version_ids": [], "__local_executor_error": True},
        idempotency_key="ip-batch5-retry-1",
    )
    failed = asyncio.run(adapter.execute_local(created.run.app_run_id))
    assert failed.run.state == "failed"
    assert failed.projection["completion_allowed"] is False
    assert sessions.get_session(created.binding.session_id) is not None
    assert [item for item in repository.list_artifacts(project.project_id) if item.source_app_run_id == created.run.app_run_id] == []
    first_attempt = repository.list_attempts(created.run.app_run_id)[-1]
    assert first_attempt.state == "failed"

    retried = adapter.retry(created.run.app_run_id)
    assert retried.run.state == "queued"
    recovered = asyncio.run(adapter.execute_local(created.run.app_run_id))
    assert recovered.run.state == "failed"
    attempts = repository.list_attempts(created.run.app_run_id)
    assert len(attempts) == 2
    assert attempts[0].state == "failed" and attempts[1].state == "failed"
    assert recovered.binding.session_id == created.binding.session_id


def test_batch5_local_executor_concurrency_has_one_attempt_and_one_output_set(harness):
    repository, project, _, _, _, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "并发执行", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-concurrency-1",
    )

    def run_once():
        return asyncio.run(adapter.execute_local(created.run.app_run_id))

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: run_once(), (1, 2)))
    assert first.run.output_artifact_ids == second.run.output_artifact_ids
    assert len(repository.list_attempts(created.run.app_run_id)) == 1
    assert len([item for item in repository.list_artifacts(project.project_id) if item.source_app_run_id == created.run.app_run_id]) == 3


def test_batch5_local_accept_rechecks_fingerprint_and_exact_outputs(harness):
    repository, project, _, _, _, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "隔离 accept", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-accept-1",
    )
    reviewed = asyncio.run(adapter.execute_local(created.run.app_run_id))
    accepted = asyncio.run(adapter.accept_fake(reviewed.run.app_run_id))
    assert accepted.run.state == "completed"
    assert accepted.session.step_status[6] == "done"
    session = adapter.session_store.get_session(created.binding.session_id)
    assert session is not None
    session.step_status[6] = "ready"
    adapter.session_store.save_session(session)
    replay = adapter.accept_local_outputs(created.run.app_run_id)
    assert replay.run.state == "completed"
    assert replay.session.step_status[6] == "done"
    video_artifact = next(
        repository.get_artifact(item)
        for item in reviewed.run.output_artifact_ids
        if repository.get_artifact(item).artifact_type == "video"
    )
    repository.append_artifact_version(video_artifact.artifact_id, content={"fake": "post-completion-tamper"}, source="generated")
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_FINGERPRINT_MISMATCH"):
        adapter.accept_local_outputs(created.run.app_run_id)

    second = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "篡改 accept", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-accept-2",
    )
    tampered = asyncio.run(adapter.execute_local(second.run.app_run_id))
    video_artifact = next(
        repository.get_artifact(item)
        for item in tampered.run.output_artifact_ids
        if repository.get_artifact(item).artifact_type == "video"
    )
    repository.append_artifact_version(video_artifact.artifact_id, content={"fake": "tampered"}, source="generated")
    with pytest.raises(IpBroadcastSessionError, match="ARTIFACT_FINGERPRINT_MISMATCH"):
        asyncio.run(adapter.accept_fake(second.run.app_run_id))


def test_batch5_local_restart_repairs_missing_review_fingerprint(harness):
    repository, project, _, _, _, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "恢复指纹", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-fingerprint-repair-1",
    )
    reviewed = asyncio.run(adapter.execute_local(created.run.app_run_id))
    attempt = repository.list_attempts(created.run.app_run_id)[-1]
    repository.update_attempt(attempt.attempt_id, diagnostic_json={})
    restarted = IpBroadcastAppAdapter(
        repository,
        session_store=adapter.session_store,
        binding_store=IpBroadcastBindingStore(adapter.binding_store._path),
        enforce_feature_flag=False,
    )
    repaired = asyncio.run(restarted.execute_local(reviewed.run.app_run_id))
    assert repaired.run.state == "needs_review"
    assert repository.list_attempts(reviewed.run.app_run_id)[-1].diagnostic.get("local_output_fingerprint", "").startswith("sha256:")
    accepted = restarted.accept_local_outputs(reviewed.run.app_run_id)
    assert accepted.run.state == "completed"


def test_batch5_local_restart_recovers_orphaned_running_attempt_to_retryable_failure(harness):
    repository, project, _, _, sessions, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "恢复 running", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-restart-running-1",
    )
    repository.transition_app_run(created.run.app_run_id, "queued")
    running = repository.transition_app_run(created.run.app_run_id, "running")
    attempt = repository.create_attempt(running.app_run_id)
    repository.update_attempt(attempt.attempt_id, state="running", started_at=running.updated_at)
    recovered = asyncio.run(adapter.execute_local(created.run.app_run_id))
    assert recovered.run.state == "failed"
    assert recovered.run.error_code == "APP_EXECUTOR_INTERRUPTED"
    assert repository.list_attempts(created.run.app_run_id)[-1].state == "failed"
    session = sessions.get_session(created.binding.session_id)
    assert session is not None and session.step_status[6] == "error"
    retried = adapter.retry(created.run.app_run_id)
    assert retried.run.state == "queued"


def test_batch5_retry_partial_executor_failure_preserves_previous_artifacts(harness, monkeypatch):
    repository, project, _, _, _, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "保留历史", "source_artifact_version_ids": []},
        idempotency_key="ip-batch5-history-compensation-1",
    )
    first = asyncio.run(adapter.execute_local(created.run.app_run_id))
    old_output_ids = list(first.run.output_artifact_ids)
    repository.transition_app_run(first.run.app_run_id, "failed")
    adapter.retry(first.run.app_run_id)

    def malformed_output(_run):
        return ExecutorOutput(
            artifact_type="video",
            name="失败视频",
            content={"fake": True},
            related_artifacts=[
                RelatedArtifactOutput("cover", "cover", "失败封面", content={"fake": True}),
                RelatedArtifactOutput("bad", "unknown-artifact", "非法产物", content={"fake": True}),
            ],
        )

    monkeypatch.setattr(adapter, "_local_executor_output", malformed_output)
    failed = asyncio.run(adapter.execute_local(first.run.app_run_id))
    assert failed.run.state == "failed"
    assert failed.run.output_artifact_ids == old_output_ids
    preserved_ids = [item.artifact_id for item in repository.list_artifacts(project.project_id) if item.source_app_run_id == first.run.app_run_id]
    assert set(preserved_ids) == set(old_output_ids)


def test_cancel_is_idempotent_and_retry_reuses_session_without_deleting_artifacts(harness):
    repository, project, _, _, _, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        idempotency_key="ip-cancel-1",
    )
    cancelled = adapter.cancel(created.run.app_run_id)
    cancelled_again = adapter.cancel(created.run.app_run_id)
    assert cancelled.run.state == "cancelled"
    assert cancelled_again.run.app_run_id == cancelled.run.app_run_id
    assert cancelled_again.binding.session_id == cancelled.binding.session_id

    retry_source = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        idempotency_key="ip-retry-1",
    )
    before_artifacts = {item.artifact_id for item in repository.list_artifacts(project.project_id)}
    retry_session = adapter.session_store.get_session(retry_source.binding.session_id)
    retry_session.step_status[3] = "running"
    retry_session.notices[3] = {"kind": "error", "message": "旧失败", "retryable": "true"}
    retry_session.state["legacy_lifecycle_state"] = "needs_attention"
    adapter.session_store.save_session(retry_session)
    failed = adapter.repository.transition_app_run(retry_source.run.app_run_id, "queued")
    failed = adapter.repository.transition_app_run(failed.app_run_id, "running")
    failed = adapter.repository.transition_app_run(failed.app_run_id, "failed")
    retried = adapter.retry(failed.app_run_id)
    assert retried.run.state == "queued"
    assert retried.binding.session_id == retry_source.binding.session_id
    assert retried.projection["task_status"] == "pending"
    assert retried.session.step_status[3] == "ready"
    assert all(notice.get("kind") != "error" for notice in retried.session.notices.values())
    assert "legacy_lifecycle_state" not in retried.session.state
    assert before_artifacts <= {item.artifact_id for item in repository.list_artifacts(project.project_id)}


@pytest.mark.parametrize(
    ("when", "task_status", "app_state", "allowed"),
    [
        ("waiting_for_login", "waiting_for_login", "needs_review", False),
        ("waiting_for_human", "waiting_for_human", "needs_review", False),
        ("needs_attention", "needs_attention", "needs_review", False),
        ("ip_learning_topic_confirmation", "needs_review", "needs_review", False),
        ("all_outputs_verified", "completed", "completed", True),
    ],
)
def test_legacy_waiting_states_never_complete(when, task_status, app_state, allowed):
    projection = project_legacy_state(when)
    assert projection.task_status == task_status
    assert projection.app_run_state == app_state
    assert projection.completion_allowed is allowed


def test_reconcile_projects_persisted_legacy_waiting_and_topic_states(harness):
    _, project, _, _, sessions, _, adapter = harness
    created = adapter.create_or_resume(
        project.project_id,
        {"source_mode": "blank_project", "goal": "等待态", "source_artifact_version_ids": []},
        idempotency_key="ip-waiting-1",
    )
    session = sessions.get_session(created.binding.session_id)
    session.state["legacy_lifecycle_state"] = "waiting_for_human"
    sessions.save_session(session)
    waiting = adapter.reconcile(created.binding.session_id, project_id=project.project_id)
    assert waiting.projection["task_status"] == "waiting_for_human"
    assert waiting.projection["completion_allowed"] is False

    session.state.pop("legacy_lifecycle_state")
    session.state["ip_learning_requires_topic_confirmation"] = True
    sessions.save_session(session)
    topic = adapter.reconcile(created.binding.session_id, project_id=project.project_id)
    assert topic.projection["current_step"] == "source"
    assert topic.projection["task_status"] == "needs_review"

    cancelled = adapter.cancel(created.run.app_run_id)
    assert cancelled.projection["task_status"] == "cancelled"
    assert cancelled.projection["completion_allowed"] is False
