import time

from fastapi.testclient import TestClient

from api.app import app
from api.routers.app_center import get_app_center_repository
from pixelle_video.app_center.llm_port import FakeLLMPort
from pixelle_video.app_center.runner import AppRunner
from pixelle_video.app_center.structured_apps import build_builtin_structured_executors
from pixelle_video.app_center.task_projection import AppRunTaskProjector


def _copy_response():
    variants = []
    for index, angle in enumerate(("利益", "好奇", "场景"), start=1):
        hook, body, cta = f"入口{index}", f"真实内容{index}", "到店了解"
        full_text = hook + body + cta
        variants.append({"version_name": f"版本{index}", "angle": angle, "hook": hook, "body": body, "cta": cta, "full_text": full_text, "word_count": len(full_text), "estimated_seconds": (len(full_text) + 3) // 4})
    return {"variants": variants, "missing_facts": [], "risk_flags": []}


def test_content_project_and_app_run_api_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("PIXELLE_APP_CENTER_CONTENT_APPS", "true")
    get_app_center_repository.cache_clear()
    monkeypatch.setattr(
        "api.routers.app_center.get_app_center_runner",
        lambda: AppRunner(
            get_app_center_repository(),
            executors=build_builtin_structured_executors(get_app_center_repository(), FakeLLMPort(_copy_response())),
            task_projector=AppRunTaskProjector(),
        ),
    )
    client = TestClient(app)

    project_response = client.post("/api/content-projects", json={"name": "API 项目", "primary_goal": "验证 API"})
    assert project_response.status_code == 201
    project = project_response.json()
    snapshot_response = client.post(
        f"/api/content-projects/{project['project_id']}/context-snapshots",
        json={"payload": {"store_name": "API 店"}},
    )
    assert snapshot_response.status_code == 201
    run_response = client.post(
        "/api/app-runs",
        json={
            "project_id": project["project_id"],
            "app_id": "builtin.marketing-copy",
            "app_version": "1.0.0",
                "input_payload": {"goal": "到店", "product_or_service": "咖啡", "content_format": "oral", "length_bucket": "short_15s"},
            "idempotency_key": "api-run-idempotency-1",
        },
    )
    assert run_response.status_code == 201
    run = run_response.json()
    assert run["state"] == "draft"
    transition = client.post(f"/api/app-runs/{run['app_run_id']}/transition", json={"state": "queued"})
    assert transition.status_code == 200
    assert transition.json()["state"] == "queued"
    executed = client.post(f"/api/app-runs/{run['app_run_id']}/execute")
    assert executed.status_code == 202
    assert executed.json()["task_id"]
    for _ in range(20):
        if client.get(f"/api/app-runs/{run['app_run_id']}").json()["state"] == "needs_review":
            break
        time.sleep(0.01)
    assert client.get(f"/api/app-runs/{run['app_run_id']}").json()["state"] == "needs_review"
    completed = client.post(f"/api/app-runs/{run['app_run_id']}/complete-review")
    assert completed.status_code == 200
    assert completed.json()["state"] == "completed"
    artifact_id = completed.json()["output_artifact_ids"][0]
    artifacts = client.get(f"/api/content-projects/{project['project_id']}/artifacts")
    assert artifacts.status_code == 200 and artifacts.json()[0]["artifact_id"] == artifact_id
    versions = client.get(f"/api/artifacts/{artifact_id}/versions")
    assert versions.status_code == 200 and versions.json()[0]["version_number"] == 1
    appended = client.post(
        f"/api/artifacts/{artifact_id}/versions",
        json={"file_refs": [{"file_key": "cover", "relative_path": "assets/cover.png"}], "source": "edited"},
    )
    assert appended.status_code == 201
    assert client.get(f"/api/artifacts/{artifact_id}/files/cover").status_code == 200
    handoff = client.post(
        f"/api/artifacts/{artifact_id}/handoffs",
        json={
            "project_id": project["project_id"],
            "source_artifact_id": artifact_id,
            "source_artifact_version_id": versions.json()[0]["artifact_version_id"],
            "target_app_id": "builtin.viral-titles",
            "target_app_version": "1.0.0",
            "artifact_version_ids": [versions.json()[0]["artifact_version_id"]],
        },
    )
    assert handoff.status_code == 201
    assert client.get(f"/api/artifacts/{artifact_id}/handoffs").status_code == 200
    assert client.post(f"/api/app-runs/{run['app_run_id']}/execute").status_code == 409
    assert client.post(f"/api/content-projects/{project['project_id']}/archive").status_code == 200
    invalid = client.post(f"/api/app-runs/{run['app_run_id']}/transition", json={"state": "queued"})
    assert invalid.status_code == 409


def test_api_executes_marketing_copy_through_structured_executor(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "structured-api.sqlite"))
    monkeypatch.setenv("PIXELLE_APP_CENTER_CONTENT_APPS", "true")
    get_app_center_repository.cache_clear()
    monkeypatch.setattr(
        "api.routers.app_center.get_app_center_runner",
        lambda: AppRunner(
            get_app_center_repository(),
            executors=build_builtin_structured_executors(get_app_center_repository(), FakeLLMPort(_copy_response())),
            task_projector=AppRunTaskProjector(),
        ),
    )
    client = TestClient(app)
    project = client.post("/api/content-projects", json={"name": "结构化 API", "primary_goal": "验证文案"}).json()
    run = client.post("/api/app-runs", json={"project_id": project["project_id"], "app_id": "builtin.marketing-copy", "app_version": "1.0.0", "input_payload": {"goal": "到店", "product_or_service": "咖啡", "content_format": "oral", "length_bucket": "short_15s"}, "idempotency_key": "structured-api-run-001"}).json()
    assert client.post(f"/api/app-runs/{run['app_run_id']}/transition", json={"state": "queued"}).status_code == 200
    assert client.post(f"/api/app-runs/{run['app_run_id']}/execute").status_code == 202
    for _ in range(30):
        current = client.get(f"/api/app-runs/{run['app_run_id']}").json()
        if current["state"] == "needs_review":
            break
        time.sleep(0.01)
    assert current["state"] == "needs_review"
    artifact = client.get(f"/api/content-projects/{project['project_id']}/artifacts").json()[0]
    version = client.get(f"/api/artifacts/{artifact['artifact_id']}/versions").json()[0]
    assert version["content"]["artifact_type"] == "copywriting"
    assert len(version["content"]["variants"]) == 3
