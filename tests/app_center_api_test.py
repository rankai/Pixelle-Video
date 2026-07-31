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
    for index in range(1, 4):
        variants.append({"full_text": f"入口{index}真实内容{index}到店了解"})
    return {"variants": variants}


def test_content_project_and_app_run_api_contract(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "api.sqlite"))
    monkeypatch.setenv("PIXELLE_APP_CENTER_CONTENT_APPS", "true")
    get_app_center_repository.cache_clear()
    monkeypatch.setattr(
        "api.routers.app_center.get_app_center_runner",
        lambda: AppRunner(
            get_app_center_repository(),
            executors=build_builtin_structured_executors(
                get_app_center_repository(), FakeLLMPort(_copy_response())
            ),
            task_projector=AppRunTaskProjector(),
        ),
    )
    client = TestClient(app)

    project_response = client.post(
        "/api/content-projects", json={"name": "API 项目", "primary_goal": "验证 API"}
    )
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
            "input_payload": {
                "goal": "到店",
                "product_or_service": "咖啡",
                "content_format": "oral",
                "length_bucket": "short_15s",
            },
            "idempotency_key": "api-run-idempotency-1",
        },
    )
    assert run_response.status_code == 201
    run = run_response.json()
    assert run["state"] == "draft"
    transition = client.post(
        f"/api/app-runs/{run['app_run_id']}/transition", json={"state": "queued"}
    )
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
    presets = client.get(
        "/api/style-presets",
        params={"app_id": "builtin.marketing-copy"},
    )
    assert presets.status_code == 200
    assert presets.json()["items"]
    assert "prompt_rules" not in presets.json()["items"][0]
    selected_title = client.post(
        f"/api/content-projects/{project['project_id']}/artifacts",
        json={
            "artifact_type": "selected_title",
            "name": "API 主标题",
            "source_app_run_id": run["app_run_id"],
        },
    )
    assert selected_title.status_code == 201
    event = client.post(
        f"/api/app-runs/{run['app_run_id']}/events",
        json={
            "event_type": "result.selected",
            "payload": {
                "artifact_id": artifact_id,
                "artifact_version_id": versions.json()[0]["artifact_version_id"],
                "item_index": 0,
                "summary": "设为主文案",
            },
        },
    )
    assert event.status_code == 201
    listed_events = client.get(f"/api/app-runs/{run['app_run_id']}/events")
    assert listed_events.status_code == 200
    assert listed_events.json()[0]["event_type"] == "result.selected"
    appended = client.post(
        f"/api/artifacts/{artifact_id}/versions",
        json={
            "file_refs": [{"file_key": "cover", "relative_path": "assets/cover.png"}],
            "source": "edited",
        },
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
            "mapping_version": 2,
        },
    )
    assert handoff.status_code == 201
    retried_handoff = client.post(
        f"/api/artifacts/{artifact_id}/handoffs",
        json={
            "project_id": project["project_id"],
            "source_artifact_id": artifact_id,
            "source_artifact_version_id": versions.json()[0]["artifact_version_id"],
            "target_app_id": "builtin.viral-titles",
            "target_app_version": "1.0.0",
            "artifact_version_ids": [versions.json()[0]["artifact_version_id"]],
            "mapping_version": 2,
        },
    )
    assert retried_handoff.status_code == 201
    assert retried_handoff.json()["handoff_id"] == handoff.json()["handoff_id"]
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
            executors=build_builtin_structured_executors(
                get_app_center_repository(), FakeLLMPort(_copy_response())
            ),
            task_projector=AppRunTaskProjector(),
        ),
    )
    client = TestClient(app)
    project = client.post(
        "/api/content-projects", json={"name": "结构化 API", "primary_goal": "验证文案"}
    ).json()
    snapshot = client.post(
        f"/api/content-projects/{project['project_id']}/context-snapshots",
        json={
            "schema_version": 2,
            "payload": {
                "schema_version": 2,
                "subject_type": "store",
                "store_or_brand": {
                    "name": "结构化咖啡店",
                    "industry": "咖啡餐饮",
                    "address": None,
                    "contact": None,
                },
                "offer": {
                    "name": "现磨咖啡",
                    "category": "饮品",
                    "price_facts": [],
                    "promotion_facts": [],
                },
                "audience": {"primary": "附近上班族", "scenes": []},
                "selling_points": [{"fact_id": "selling-1", "text": "门店现磨", "source": "user"}],
                "proof_points": [],
                "required_facts": [],
                "forbidden_claims": [],
                "asset_refs": [],
                "brand_revision_ref": None,
            },
        },
    ).json()
    run = client.post(
        "/api/app-runs",
        json={
            "project_id": project["project_id"],
            "app_id": "builtin.marketing-copy",
            "app_version": "1.1.0",
            "input_payload": {
                "schema_version": 2,
                "app_id": "builtin.marketing-copy",
                "input_schema_ref": "marketing-copy-input.v2",
                "project_id": project["project_id"],
                "context_snapshot_id": snapshot["context_snapshot_id"],
                "task_brief": {
                    "marketing_goal": "到店",
                    "offer_name": "现磨咖啡",
                    "selling_point_fact_ids": ["selling-1"],
                    "benefit_tags": ["下午茶"],
                    "benefit_text": "下午茶",
                    "audience": "附近上班族",
                    "must_include": [],
                },
                "style_ref": {"style_id": "copy.owner_voice", "version": 1},
                "custom_style_reference": None,
                "source_artifact_version_ids": [],
            },
            "context_snapshot_id": snapshot["context_snapshot_id"],
            "idempotency_key": "structured-api-run-001",
        },
    ).json()
    assert (
        client.post(
            f"/api/app-runs/{run['app_run_id']}/transition", json={"state": "queued"}
        ).status_code
        == 200
    )
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
    assert version["schema_version"] == 2
    assert len(version["content"]["variants"]) == 3
    assert all(set(item) == {"full_text"} for item in version["content"]["variants"])
    handoff = client.post(
        f"/api/artifacts/{artifact['artifact_id']}/handoffs",
        json={
            "project_id": project["project_id"],
            "source_artifact_id": artifact["artifact_id"],
            "source_artifact_version_id": version["artifact_version_id"],
            "target_app_id": "builtin.viral-titles",
            "target_app_version": "1.1.0",
            "artifact_version_ids": [version["artifact_version_id"]],
            "mapping_version": 2,
        },
    )
    assert handoff.status_code == 201
