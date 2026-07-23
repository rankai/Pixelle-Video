from types import SimpleNamespace

from fastapi.testclient import TestClient

from api.app import app
from api.routers import publish_v2
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore
from pixelle_video.services.publish.account_models import PublishPlatform
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.services.publish.account_service import PublishAccountService
from pixelle_video.services.publish.core_models import PublishRunState
from pixelle_video.services.publish.profile_manager import BrowserProfileManager


def _headers():
    return {"X-Pixelle-Local-Capability": "cap-test", "Origin": "tauri://localhost"}


def _configure_publish_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "1")
    monkeypatch.setenv("PIXELLE_PUBLISH_V2_ENABLED", "1")
    monkeypatch.setenv("PIXELLE_LOCAL_CAPABILITY", "cap-test")
    monkeypatch.setenv("PIXELLE_PUBLISHING_DB", str(tmp_path / "publishing.sqlite"))
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "app.sqlite"))
    monkeypatch.setenv("PIXELLE_PUBLISH_MEDIA_ROOTS", str(tmp_path))
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    publish_v2.get_publish_core_repository.cache_clear()
    publish_v2.get_publish_account_repository.cache_clear()
    publish_v2.get_app_center_repository.cache_clear()
    publish_v2.get_publish_package_service.cache_clear()
    publish_v2.get_publish_run_service.cache_clear()


def test_adapter_result_event_uses_latest_checkpoint_state_version(monkeypatch):
    events = []

    class Repository:
        def get_run(self, _run_id):
            return SimpleNamespace(state=PublishRunState.RUNNING, state_version=99)

        def append_event(self, run_id, event_type, *, state, state_version, payload):
            events.append((run_id, event_type, state, state_version, payload))

    monkeypatch.setattr(publish_v2, "get_publish_core_repository", lambda: Repository())
    publish_v2._append_adapter_result_event(
        "run_latest_version",
        SimpleNamespace(status=SimpleNamespace(value="draft_ready")),
        "douyin-entry@1",
    )

    assert events == [
        (
            "run_latest_version",
            "adapter_result",
            PublishRunState.RUNNING,
            99,
                {
                    "step": "adapter_prepare",
                    "adapter_version": "douyin-entry@1",
                    "evidence_kind": "live_douyin_dom_readback",
                    "adapter_state": None,
                    "filled_fields": [],
                    "readback_fields": [],
                    "platform_fallback_boundaries": [],
                        "media_readback": False,
                        "cover_readback": False,
                        "cover_receipt_present": False,
                        "final_publish_click_count": 0,
                },
        )
    ]


def test_publish_v2_requires_local_capability_and_projects_run(tmp_path, monkeypatch):
    _configure_publish_runtime(tmp_path, monkeypatch)


    app_repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = app_repository.create_project("API 发布", "验证 V2")
    media = tmp_path / "video.mp4"
    media.write_bytes(b"00000000ftypisom-api")
    artifact = app_repository.create_artifact(project.project_id, "video", "视频")
    version = app_repository.append_artifact_version(artifact.artifact_id, file_refs=[{"path": str(media)}])
    account = publish_v2.get_publish_account_repository().create_account(PublishPlatform.DOUYIN, "API 账号", "profile_api")
    other_account = publish_v2.get_publish_account_repository().create_account(PublishPlatform.VIDEO_CHANNEL, "其他账号", "profile_other")

    with TestClient(app) as client:
        denied = client.post("/api/publish/v2/packages", json={"project_id": project.project_id, "artifact_version_ids": [version.artifact_version_id]})
        assert denied.status_code == 403 and denied.json()["detail"] == "CAPABILITY_REQUIRED"
        wrong_origin = client.post("/api/publish/v2/packages", headers={"X-Pixelle-Local-Capability": "cap-test", "Origin": "https://evil.example"}, json={"project_id": project.project_id, "artifact_version_ids": [version.artifact_version_id]})
        assert wrong_origin.status_code == 403 and wrong_origin.json()["detail"] == "ORIGIN_NOT_ALLOWED"
        created = client.post("/api/publish/v2/packages", headers=_headers(), json={"project_id": project.project_id, "artifact_version_ids": [version.artifact_version_id]})
        assert created.status_code == 201
        package = created.json()
        assert str(media) not in str(package)
        session = client.post("/api/publish/v2/packages/from-session", headers=_headers(), json={"project_id": project.project_id, "session_id": "legacy-1"})
        assert session.status_code == 404 and session.json()["detail"] == "LEGACY_SESSION_NOT_FOUND"
        assert client.post("/api/publish/v2/packages/from-session", headers=_headers(), json={"project_id": project.project_id, "session_id": "legacy-1", "path": "/tmp/escape.mp4"}).status_code == 422
        accepted = client.post("/api/publish/v2/runs", headers=_headers(), json={"package_id": package["package_id"], "account_id": account.account_id, "platform": "douyin", "idempotency_key": "api-v2-key-001"})
        assert accepted.status_code == 202
        body = accepted.json()
        assert body["task_id"] and body["requires_human_confirmation"] is True
        replay = client.post("/api/publish/v2/runs", headers=_headers(), json={"package_id": package["package_id"], "account_id": account.account_id, "platform": "douyin", "idempotency_key": "api-v2-key-001"})
        assert replay.status_code == 202 and replay.json()["idempotent_replay"] is True
        run = client.get(f"/api/publish/v2/runs/{body['run_id']}")
        assert run.status_code == 200
        assert run.json()["run"]["human_confirmation"]["required"] is True
        assert client.get(f"/api/publish/v2/runs/{body['run_id']}/events").status_code == 200
        missing_account = client.post("/api/publish/v2/runs", headers=_headers(), json={"package_id": package["package_id"], "account_id": "acct_missing", "platform": "douyin", "idempotency_key": "api-v2-missing-001"})
        assert missing_account.status_code == 404 and missing_account.json()["detail"] == "ACCOUNT_NOT_FOUND"
        mismatch = client.post("/api/publish/v2/runs", headers=_headers(), json={"package_id": package["package_id"], "account_id": other_account.account_id, "platform": "douyin", "idempotency_key": "api-v2-mismatch-001"})
        assert mismatch.status_code == 409 and mismatch.json()["detail"] == "ACCOUNT_PLATFORM_MISMATCH"

    publish_v2.get_publish_core_repository.cache_clear()
    publish_v2.get_publish_account_repository.cache_clear()
    publish_v2.get_app_center_repository.cache_clear()
    publish_v2.get_publish_package_service.cache_clear()
    publish_v2.get_publish_run_service.cache_clear()


def test_publish_v2_from_session_registers_canonical_artifacts_and_preflights(tmp_path, monkeypatch):
    _configure_publish_runtime(tmp_path, monkeypatch)

    video = tmp_path / "handoff.mp4"
    video.write_bytes(b"00000000ftypisom-handoff")
    cover = tmp_path / "handoff.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\nhandoff")
    store = IpBroadcastSessionStore(tmp_path / "sessions")
    session = store.create_session()
    session.state["final_video_path"] = str(video)
    session.state["cover_path"] = str(cover)
    session.artifacts["final_video"] = str(video)
    session.artifacts["cover"] = str(cover)
    store.save_session(session)
    monkeypatch.setattr(publish_v2, "_session_store", store)

    with TestClient(app) as client:
        response = client.post(
            "/api/publish/v2/packages/from-session",
            headers=_headers(),
            json={"project_id": "legacy-project", "session_id": session.session_id, "platform_copy": {"title": "t1"}},
        )
        assert response.status_code == 201, response.text
        package = response.json()
        assert package["source"]["kind"] == "artifact_versions"
        assert str(video) not in str(package)
        preflight = client.post(f"/api/publish/v2/packages/{package['package_id']}/preflight", headers=_headers())
        assert preflight.status_code == 200
        replay = client.post(
            "/api/publish/v2/packages/from-session",
            headers=_headers(),
            json={"project_id": "legacy-project", "session_id": session.session_id, "platform_copy": {"title": "t1"}},
        )
        assert replay.status_code == 201
        assert replay.json()["package_id"] == package["package_id"]

        video.write_bytes(b"00000000ftypisom-handoff-v2")
        session.state["title"] = "t2"
        store.save_session(session)
        changed = client.post(
            "/api/publish/v2/packages/from-session",
            headers=_headers(),
            json={"project_id": "legacy-project", "session_id": session.session_id, "platform_copy": {"title": "t2"}},
        )
        assert changed.status_code == 201, changed.text
        changed_package = changed.json()
        assert changed_package["package_id"] != package["package_id"]
        old_package = client.get(f"/api/publish/v2/packages/{package['package_id']}")
        assert old_package.status_code == 200
        assert old_package.json()["invalidated_at"] is not None
        assert client.post(f"/api/publish/v2/packages/{changed_package['package_id']}/preflight", headers=_headers()).status_code == 200


def test_publish_v2_rolls_back_to_v1_when_flag_is_off(monkeypatch):
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "1")
    monkeypatch.setenv("PIXELLE_PUBLISH_V2_ENABLED", "0")
    with TestClient(app) as client:
        response = client.get("/api/publish/v2/packages/pkg_missing")
    assert response.status_code == 404 and response.json()["detail"] == "V2_DISABLED"


def test_publish_v2_resolver_runtime_is_unique_or_fail_closed(tmp_path, monkeypatch):
    _configure_publish_runtime(tmp_path, monkeypatch)
    app_repository = AppCenterRepository(tmp_path / "app.sqlite")

    def create_package(label: str, *, title: str | None = None):
        project = app_repository.create_project(f"Resolver {label}", "runtime resolver")
        media = tmp_path / f"resolver-{label}.mp4"
        media.write_bytes(f"00000000ftypisom-{label}".encode())
        artifact = app_repository.create_artifact(project.project_id, "video", f"视频 {label}")
        version = app_repository.append_artifact_version(artifact.artifact_id, file_refs=[{"path": str(media)}])
        payload = {"project_id": project.project_id, "artifact_version_ids": [version.artifact_version_id]}
        if title is not None:
            payload["platform_copy"] = {"title": title}
        with TestClient(app) as client:
            response = client.post("/api/publish/v2/packages", headers=_headers(), json=payload)
        assert response.status_code == 201, response.text
        return project, artifact, version.artifact_version_id, response.json()

    _project, unique_artifact, _unique_version_id, unique_package = create_package("unique")
    with TestClient(app) as client:
        unique = client.get("/api/publish/v2/packages/resolve", params={"artifact_id": unique_artifact.artifact_id})
    assert unique.status_code == 200
    assert unique.json()["package_id"] == unique_package["package_id"]

    _stale_project, stale_artifact, _stale_version_id, stale_package = create_package("stale")
    publish_v2.get_publish_core_repository().invalidate_package(stale_package["package_id"], "runtime stale fixture")
    with TestClient(app) as client:
        stale = client.get("/api/publish/v2/packages/resolve", params={"artifact_id": stale_artifact.artifact_id})
    assert stale.status_code == 409
    assert stale.json()["detail"] == "PUBLISH_PACKAGE_STALE"

    ambiguous_project, ambiguous_artifact, first_version_id, _first = create_package("ambiguous", title="标题 A")
    with TestClient(app) as client:
        second = client.post(
            "/api/publish/v2/packages",
            headers=_headers(),
            json={
                "project_id": ambiguous_project.project_id,
                "artifact_version_ids": [first_version_id],
                "platform_copy": {"title": "标题 C"},
            },
        )
        assert second.status_code == 201, second.text
        ambiguous = client.get("/api/publish/v2/packages/resolve", params={"artifact_id": ambiguous_artifact.artifact_id})
    assert ambiguous.status_code == 409
    assert ambiguous.json()["detail"] == "PUBLISH_PACKAGE_AMBIGUOUS"


def test_publish_v2_derives_publish_copy_artifact_when_platform_copy_is_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "1")
    monkeypatch.setenv("PIXELLE_PUBLISH_V2_ENABLED", "1")
    monkeypatch.setenv("PIXELLE_LOCAL_CAPABILITY", "cap-test")
    monkeypatch.setenv("PIXELLE_PUBLISHING_DB", str(tmp_path / "publishing.sqlite"))
    monkeypatch.setenv("PIXELLE_APP_CENTER_DB", str(tmp_path / "app.sqlite"))
    monkeypatch.setenv("PIXELLE_PUBLISH_MEDIA_ROOTS", str(tmp_path))
    publish_v2.get_publish_core_repository.cache_clear()
    publish_v2.get_publish_account_repository.cache_clear()
    publish_v2.get_app_center_repository.cache_clear()
    publish_v2.get_publish_package_service.cache_clear()
    publish_v2.get_publish_run_service.cache_clear()

    app_repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = app_repository.create_project("API 文案", "来源文案")
    video_path = tmp_path / "api-copy.mp4"
    video_path.write_bytes(b"00000000ftypisom-api-copy")
    cover_path = tmp_path / "api-copy.png"
    cover_path.write_bytes(b"\x89PNG\r\n\x1a\napi-copy")
    video = app_repository.create_artifact(project.project_id, "video", "视频")
    cover = app_repository.create_artifact(project.project_id, "cover", "封面")
    copy = app_repository.create_artifact(project.project_id, "publish_copy", "发布文案")
    video_version = app_repository.append_artifact_version(video.artifact_id, file_refs=[{"path": str(video_path)}])
    cover_version = app_repository.append_artifact_version(cover.artifact_id, file_refs=[{"path": str(cover_path)}])
    copy_version = app_repository.append_artifact_version(copy.artifact_id, content={"artifact_type": "publish_copy", "title": "API 来源标题", "description": "API 来源描述", "hashtags": ["来源"]})

    with TestClient(app) as client:
        response = client.post(
            "/api/publish/v2/packages",
            headers=_headers(),
            json={"project_id": project.project_id, "artifact_version_ids": [video_version.artifact_version_id, cover_version.artifact_version_id, copy_version.artifact_version_id]},
        )
    assert response.status_code == 201
    assert response.json()["platform_copy"]["title"] == "API 来源标题"
    publish_v2.get_publish_core_repository.cache_clear()
    publish_v2.get_publish_account_repository.cache_clear()
    publish_v2.get_app_center_repository.cache_clear()
    publish_v2.get_publish_package_service.cache_clear()
    publish_v2.get_publish_run_service.cache_clear()


def test_publish_v2_maps_package_validation_failures_to_422(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "1")
    monkeypatch.setenv("PIXELLE_PUBLISH_V2_ENABLED", "1")
    monkeypatch.setenv("PIXELLE_LOCAL_CAPABILITY", "cap-test")

    class InvalidPackageService:
        def create_from_artifact_versions(self, *_args, **_kwargs):
            raise ValueError("VIDEO_OR_CAROUSEL_ARTIFACT_REF_REQUIRED")

    monkeypatch.setattr(publish_v2, "get_publish_package_service", lambda: InvalidPackageService())
    project = AppCenterRepository(tmp_path / "app.sqlite").create_project("API 校验", "混合媒体错误")

    with TestClient(app) as client:
        response = client.post(
            "/api/publish/v2/packages",
            headers=_headers(),
            json={"project_id": project.project_id, "artifact_version_ids": ["artifact_version_invalid"]},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "VIDEO_OR_CAROUSEL_ARTIFACT_REF_REQUIRED"


def test_publish_v2_account_route_parity_and_capability_guard(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_DESKTOP_MODE", "1")
    monkeypatch.setenv("PIXELLE_PUBLISH_V2_ENABLED", "1")
    monkeypatch.setenv("PIXELLE_LOCAL_CAPABILITY", "cap-test")
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite")
    service = PublishAccountService(
        repository,
        BrowserProfileManager(tmp_path / "profiles", legacy_profile_root=tmp_path / "legacy", repository=repository),
    )
    monkeypatch.setattr(publish_v2, "get_publish_account_service_v2", lambda: service)
    for suffix, operation_id in (("connect", "connectPublishAccountV2"), ("verify", "verifyPublishAccountV2"), ("open", "openPublishAccountV2")):
        route = next(route for route in app.routes if route.path == f"/api/publish/v2/accounts/{{account_id}}/{suffix}" and "POST" in route.methods)
        assert route.operation_id == operation_id
        assert route.status_code in (None, 200)
    with TestClient(app) as client:
        assert client.get("/api/publish/v2/accounts").status_code == 200
        denied = client.post("/api/publish/v2/accounts", json={"platform": "douyin", "display_name": "V2 账号"})
        assert denied.status_code == 403 and denied.json()["detail"] == "CAPABILITY_REQUIRED"
        created = client.post("/api/publish/v2/accounts", headers=_headers(), json={"platform": "douyin", "display_name": "V2 账号"})
        assert created.status_code == 201
        account_id = created.json()["account_id"]
        assert client.get(f"/api/publish/v2/accounts/{account_id}").status_code == 200
        assert client.post(f"/api/publish/v2/accounts/{account_id}/make-default", headers=_headers()).status_code == 200
        assert client.post(f"/api/publish/v2/accounts/{account_id}/archive", headers=_headers()).status_code == 200
        assert client.get("/api/publish/v2/accounts/acct_missing").json()["detail"] == "PUBLISH_ACCOUNT_NOT_FOUND"
