import asyncio

import pytest

from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore


def _copywriting_content():
    return {
        "schema_version": 1,
        "artifact_type": "copywriting",
        "variants": [
            {
                "version_name": "门店口播",
                "angle": "场景",
                "hook": "到店先看",
                "body": "今天到店有活动",
                "cta": "欢迎来店咨询",
                "full_text": "到店先看，今天到店有活动，欢迎来店咨询。",
                "word_count": 20,
                "estimated_seconds": 5,
            },
            {
                "version_name": "优惠口播",
                "angle": "利益",
                "hook": "进店先看",
                "body": "到店可以先了解服务",
                "cta": "欢迎进店",
                "full_text": "进店先看，到店可以先了解服务，欢迎进店。",
                "word_count": 20,
                "estimated_seconds": 5,
            },
            {
                "version_name": "服务口播",
                "angle": "身份",
                "hook": "老板可以这样做",
                "body": "把到店服务讲清楚",
                "cta": "欢迎来店了解",
                "full_text": "老板可以这样做，把到店服务讲清楚，欢迎来店了解。",
                "word_count": 22,
                "estimated_seconds": 6,
            },
        ],
        "missing_facts": [],
        "risk_flags": [],
    }


@pytest.fixture
def gray_harness(tmp_path):
    repository = AppCenterRepository(tmp_path / "app-center.sqlite")
    project = repository.create_project("本地灰度项目", "制作一条口播视频")
    copy_artifact = repository.create_artifact(project.project_id, "copywriting", "灰度文案")
    copy_version = repository.append_artifact_version(copy_artifact.artifact_id, content=_copywriting_content())
    title_artifact = repository.create_artifact(project.project_id, "selected_title", "灰度标题")
    title_version = repository.append_artifact_version(title_artifact.artifact_id, content={"title": "到店先看这件事"})
    session_path = tmp_path / "legacy-sessions"
    binding_path = tmp_path / "bindings.json"
    sessions = IpBroadcastSessionStore(session_path)
    bindings = IpBroadcastBindingStore(binding_path)
    adapter = IpBroadcastAppAdapter(repository, session_store=sessions, binding_store=bindings, enforce_feature_flag=False)
    return repository, project, copy_version, title_version, session_path, binding_path, adapter


def test_local_gray_cycle_covers_three_sources_restart_and_explicit_accept(gray_harness):
    repository, project, copy_version, title_version, session_path, binding_path, adapter = gray_harness
    source_payloads = [
        {"source_mode": "blank_project", "goal": "制作一条本地灰度口播", "source_artifact_version_ids": []},
        {
            "source_mode": "copywriting",
            "source_artifact_version_ids": [copy_version.artifact_version_id],
            "selected_variant_index": 0,
        },
        {"source_mode": "selected_title", "source_artifact_version_ids": [title_version.artifact_version_id]},
    ]
    observed = []

    for index, payload in enumerate(source_payloads):
        created = adapter.create_or_resume(project.project_id, payload, idempotency_key=f"gray-cycle-{index:02d}")
        restarted = IpBroadcastAppAdapter(
            repository,
            session_store=IpBroadcastSessionStore(session_path),
            binding_store=IpBroadcastBindingStore(binding_path),
            enforce_feature_flag=False,
        )
        recovered = restarted.reconcile(created.binding.session_id, project_id=project.project_id)
        assert recovered.run.app_run_id == created.run.app_run_id
        assert recovered.run.session_id == created.run.session_id

        executed = asyncio.run(restarted.execute_local(created.run.app_run_id))
        assert executed.run.state == "needs_review"
        assert executed.projection["completion_allowed"] is False
        attempt = repository.list_attempts(created.run.app_run_id)[-1]
        assert attempt.provider_class == "local-isolated"
        accepted = restarted.accept_local_outputs(created.run.app_run_id)
        assert accepted.run.state == "completed"
        observed.append({
            "source_mode": payload["source_mode"],
            "app_run_id": created.run.app_run_id,
            "session_id": created.run.session_id,
            "before_restart_app_run_id": recovered.run.app_run_id,
            "state_before_accept": executed.run.state,
            "state_after_accept": accepted.run.state,
            "provider_class": attempt.provider_class,
            "external_provider_calls": 0,
            "platform_writes": 0,
            "final_publish_clicks": 0,
        })

    assert [item["source_mode"] for item in observed] == ["blank_project", "copywriting", "selected_title"]
    assert all(item["before_restart_app_run_id"] == item["app_run_id"] for item in observed)
    assert all(item["state_before_accept"] == "needs_review" and item["state_after_accept"] == "completed" for item in observed)
    assert all(item["provider_class"] == "local-isolated" for item in observed)
    assert all(item["external_provider_calls"] == item["platform_writes"] == item["final_publish_clicks"] == 0 for item in observed)
