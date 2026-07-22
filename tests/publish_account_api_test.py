from fastapi.testclient import TestClient

import api.routers.publish as publish_router
from api.app import app
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.services.publish.account_service import PublishAccountService
from pixelle_video.services.publish.profile_manager import BrowserProfileManager


def test_publish_account_api_uses_real_repository_projection(monkeypatch, tmp_path):
    repository = PublishAccountRepository(tmp_path / "publishing.sqlite3")
    service = PublishAccountService(repository, BrowserProfileManager(tmp_path / "accounts", legacy_profile_root=tmp_path / "legacy", repository=repository))
    monkeypatch.setattr(publish_router, "get_publish_account_service", lambda: service)
    with TestClient(app) as client:
        platforms = client.get("/api/publish/platforms")
        assert platforms.status_code == 200
        assert {item["platform"] for item in platforms.json()["items"]} == {"douyin", "video_channel", "kuaishou", "xiaohongshu"}
        created = client.post("/api/publish/accounts", json={"platform": "douyin", "display_name": "API 账号", "make_default": True})
        assert created.status_code == 201
        account = created.json()
        assert account["is_default"] is True
        assert "profile_path" not in account
        assert "cookie" not in str(account).lower()
        listed = client.get("/api/publish/accounts").json()["items"]
        assert {item["account_id"] for item in listed} == {account["account_id"]}
        archived = client.post(f"/api/publish/accounts/{account['account_id']}/archive")
        assert archived.status_code == 200
        assert client.get("/api/publish/accounts").json()["items"] == []
        assert client.get("/api/publish/accounts?include_archived=true").json()["items"][0]["archived_at"]
