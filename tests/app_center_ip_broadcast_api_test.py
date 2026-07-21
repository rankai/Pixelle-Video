from pathlib import Path

from fastapi.testclient import TestClient

from api.app import app
from api.routers.app_center import get_app_center_repository
from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
)
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore


def test_ip_broadcast_app_api_projects_safe_status_and_cancel(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    monkeypatch.delenv("PIXELLE_APP_CENTER_DIGITAL_HUMAN", raising=False)
    get_app_center_repository.cache_clear()
    repository = get_app_center_repository()
    sessions = IpBroadcastSessionStore(tmp_path / "sessions")
    bindings = IpBroadcastBindingStore(tmp_path / "bindings.json")
    adapter = IpBroadcastAppAdapter(repository, session_store=sessions, binding_store=bindings, enforce_feature_flag=False)
    monkeypatch.setattr("api.routers.ip_broadcast_app.get_ip_broadcast_app_adapter", lambda: adapter)
    client = TestClient(app)

    project = client.post("/api/content-projects", json={"name": "IP API", "primary_goal": "测试适配器"}).json()
    context_snapshot = client.post(
        f"/api/content-projects/{project['project_id']}/context-snapshots",
        json={"payload": {"store_name": "API 门店"}},
    ).json()
    payload = {
        "project_id": project["project_id"],
        "input_payload": {"source_mode": "blank_project", "goal": "到店咨询", "source_artifact_version_ids": []},
        "idempotency_key": "ip-api-idem-1",
        "context_snapshot_id": context_snapshot["context_snapshot_id"],
    }
    created = client.post("/api/app-center/ip-broadcast/runs", json=payload)
    assert created.status_code == 201
    body = created.json()
    assert body["state"] == "draft"
    assert body["projection"]["app_run_state"] == "draft"
    assert "input_payload" not in body
    assert "state_data" not in body
    assert all("path" not in key.lower() for key in body)

    replay = client.post("/api/app-center/ip-broadcast/runs", json=payload)
    assert replay.status_code == 201
    assert replay.json()["app_run_id"] == body["app_run_id"]

    status_response = client.get(
        f"/api/app-center/ip-broadcast/runs/{body['app_run_id']}",
        params={"project_id": project["project_id"]},
    )
    assert status_response.status_code == 200
    assert status_response.json()["session_id"] == body["session_id"]

    executed = client.post(f"/api/app-center/ip-broadcast/runs/{body['app_run_id']}/execute")
    assert executed.status_code == 200
    assert executed.json()["state"] == "needs_review"
    assert "input_payload" not in executed.text

    session = sessions.get_session(body["session_id"])
    session.notices[1] = {
        "kind": "error",
        "message": "/private/API_KEY=secret",
        "next_action": "/tmp/token=abc",
    }
    session.artifacts["/private/credential=secret"] = "/private/video.mp4"
    sessions.save_session(session)
    redacted = client.get(
        f"/api/app-center/ip-broadcast/runs/{body['app_run_id']}",
        params={"project_id": project["project_id"]},
    ).json()
    assert "API_KEY" not in str(redacted)
    assert "/private" not in str(redacted)
    assert "/private/credential=secret" not in redacted["artifact_keys"]

    other = client.post("/api/content-projects", json={"name": "另一个项目", "primary_goal": "隔离"}).json()
    cross_project = client.get(
        f"/api/app-center/ip-broadcast/runs/{body['app_run_id']}",
        params={"project_id": other["project_id"]},
    )
    assert cross_project.status_code == 409
    assert cross_project.json()["detail"]["code"] == "SESSION_PROJECT_MISMATCH"

    cancelled = client.post(f"/api/app-center/ip-broadcast/runs/{body['app_run_id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert client.post(f"/api/app-center/ip-broadcast/runs/{body['app_run_id']}/cancel").status_code == 200
    invalid_retry = client.post(f"/api/app-center/ip-broadcast/runs/{body['app_run_id']}/retry")
    assert invalid_retry.status_code == 409
    assert invalid_retry.json()["detail"]["code"] == "APP_RUN_STATE_INVALID"

    forbidden = client.post(
        "/api/app-center/ip-broadcast/runs",
        json={
            "project_id": project["project_id"],
            "input_payload": {"source_mode": "blank_project", "goal": "拒绝敏感字段", "provider": "secret"},
            "idempotency_key": "ip-api-forbidden-1",
        },
    )
    assert forbidden.status_code == 422
    assert forbidden.json()["detail"]["code"] == "INPUT_PAYLOAD_INVALID"


def test_ip_broadcast_app_api_production_default_is_fail_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    monkeypatch.delenv("PIXELLE_APP_CENTER_DIGITAL_HUMAN", raising=False)
    get_app_center_repository.cache_clear()
    client = TestClient(app)
    project = client.post("/api/content-projects", json={"name": "关闭 API", "primary_goal": "flag"}).json()
    response = client.post(
        "/api/app-center/ip-broadcast/runs",
        json={
            "project_id": project["project_id"],
            "input_payload": {"source_mode": "blank_project", "goal": "不得创建", "source_artifact_version_ids": []},
            "idempotency_key": "ip-api-disabled-1",
        },
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "APP_FEATURE_DISABLED"


def test_ip_broadcast_app_api_accept_is_explicit_and_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    get_app_center_repository.cache_clear()
    repository = get_app_center_repository()
    sessions = IpBroadcastSessionStore(tmp_path / "sessions")
    bindings = IpBroadcastBindingStore(tmp_path / "bindings.json")
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=sessions,
        binding_store=bindings,
        enforce_feature_flag=False,
        trusted_roots=[tmp_path],
    )
    monkeypatch.setattr("api.routers.ip_broadcast_app.get_ip_broadcast_app_adapter", lambda: adapter)
    client = TestClient(app)
    project = client.post("/api/content-projects", json={"name": "accept API", "primary_goal": "显式确认"}).json()
    created = adapter.create_or_resume(
        project["project_id"],
        {"source_mode": "blank_project", "goal": "显式确认", "source_artifact_version_ids": []},
        idempotency_key="ip-api-accept-1",
    )
    output = Path(tmp_path / "outputs")
    output.mkdir()
    video = output / "video.mp4"
    video.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")
    cover = output / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\ncover")
    session = sessions.get_session(created.binding.session_id)
    assert session is not None
    session.state.update(
        {
            "final_video_path": str(video),
            "cover_path": str(cover),
            "publish_package": {"title": "确认标题", "description": "确认描述", "hashtags": ["门店"]},
        }
    )
    sessions.save_session(session)
    repository.transition_app_run(created.run.app_run_id, "queued")
    repository.transition_app_run(created.run.app_run_id, "running")
    repository.transition_app_run(created.run.app_run_id, "needs_review")
    adapter.register_legacy_outputs(created.run.app_run_id)

    # The generic AppRun completion routes are intentionally not an alternate
    # success path for digital-human output review, even when the imported
    # package is otherwise valid.  Use the dedicated redacted endpoint below.
    generic_complete = client.post(f"/api/app-runs/{created.run.app_run_id}/complete")
    assert generic_complete.status_code == 409
    assert generic_complete.json()["detail"]["code"] == "ARTIFACT_ACCEPT_EXPLICIT_REQUIRED"
    assert "input_payload" not in generic_complete.text
    generic_review = client.post(f"/api/app-runs/{created.run.app_run_id}/complete-review")
    assert generic_review.status_code == 409
    assert generic_review.json()["detail"]["code"] == "ARTIFACT_ACCEPT_EXPLICIT_REQUIRED"
    assert "input_payload" not in generic_review.text
    transition_bypass = client.post(
        f"/api/app-runs/{created.run.app_run_id}/transition",
        json={"state": "completed"},
    )
    assert transition_bypass.status_code == 409
    assert transition_bypass.json()["detail"]["code"] == "ARTIFACT_ACCEPT_EXPLICIT_REQUIRED"

    accepted = client.post(f"/api/app-center/ip-broadcast/runs/{created.run.app_run_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["state"] == "completed"
    repeated = client.post(f"/api/app-center/ip-broadcast/runs/{created.run.app_run_id}/accept")
    assert repeated.status_code == 200
    assert repeated.json()["state"] == "completed"

    fake = adapter.create_or_resume(
        project["project_id"],
        {"source_mode": "blank_project", "goal": "generic complete 不得绕过", "source_artifact_version_ids": []},
        idempotency_key="ip-api-generic-guard-1",
    )
    import asyncio

    asyncio.run(adapter.run_fake(fake.run.app_run_id))
    bypass = client.post(f"/api/app-runs/{fake.run.app_run_id}/complete")
    assert bypass.status_code == 409
    assert fake.run.app_run_id


def test_ip_broadcast_app_api_isolated_execute_and_accept(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "isolated-api.sqlite"))
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    get_app_center_repository.cache_clear()
    repository = get_app_center_repository()
    sessions = IpBroadcastSessionStore(tmp_path / "sessions")
    bindings = IpBroadcastBindingStore(tmp_path / "bindings.json")
    adapter = IpBroadcastAppAdapter(repository, session_store=sessions, binding_store=bindings, enforce_feature_flag=False)
    monkeypatch.setattr("api.routers.ip_broadcast_app.get_ip_broadcast_app_adapter", lambda: adapter)
    client = TestClient(app)
    project = client.post("/api/content-projects", json={"name": "隔离 API", "primary_goal": "执行接收"}).json()
    created = adapter.create_or_resume(
        project["project_id"],
        {"source_mode": "blank_project", "goal": "API 隔离执行", "source_artifact_version_ids": []},
        idempotency_key="ip-api-isolated-execute-1",
    )
    executed = client.post(f"/api/app-center/ip-broadcast/runs/{created.run.app_run_id}/execute")
    assert executed.status_code == 200
    assert executed.json()["state"] == "needs_review"
    accepted = client.post(f"/api/app-center/ip-broadcast/runs/{created.run.app_run_id}/accept")
    assert accepted.status_code == 200
    assert accepted.json()["state"] == "completed"
    assert "input_payload" not in accepted.text
