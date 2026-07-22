import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    assets_module = importlib.import_module("api.routers.assets")
    app = FastAPI()
    app.include_router(assets_module.router, prefix="/api")
    return TestClient(app)


def test_list_ip_broadcast_templates_returns_cards(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    response = client.get("/api/assets/templates/ip-broadcast")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 3
    first = payload["items"][0]
    assert first["template_id"] == "boss_clean"
    assert first["display_name"]
    assert first["short_description"]
    assert first["preview_url"] == "/api/assets/templates/ip-broadcast/boss_clean/preview"
    assert first["subtitle_style"]["font_size"] == 17
    assert first["subtitle_style"]["margin_v"] == 227

    preview = client.get(first["preview_url"])
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "image/jpeg"


def test_voice_reference_upload_list_and_delete(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    upload = client.post(
        "/api/assets/voices",
        data={"name": "老板本人声音"},
        files={"file": ("voice.mp3", b"fake mp3", "audio/mpeg")},
    )

    assert upload.status_code == 200
    item = upload.json()
    assert item["reference_id"]
    assert item["asset_path"].endswith(".mp3")

    listed = client.get("/api/assets/voices").json()["items"]
    assert [voice["reference_id"] for voice in listed] == [item["reference_id"]]

    deleted = client.delete(f"/api/assets/voices/{item['reference_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/api/assets/voices").json()["items"] == []


def test_portrait_upload_list_and_delete(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    upload = client.post(
        "/api/assets/portraits",
        data={"name": "老板形象"},
        files={"file": ("portrait.png", b"fake png", "image/png")},
    )

    assert upload.status_code == 200
    item = upload.json()
    assert item["portrait_id"]
    assert item["media_type"] == "image"
    assert item["asset_path"].endswith(".png")

    listed = client.get("/api/assets/portraits").json()["items"]
    assert [portrait["portrait_id"] for portrait in listed] == [item["portrait_id"]]

    deleted = client.delete(f"/api/assets/portraits/{item['portrait_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/api/assets/portraits").json()["items"] == []


def test_video_asset_upload_list_and_delete(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    upload = client.post(
        "/api/assets/videos",
        data={"name": "探店环境镜头"},
        files={"file": ("clip.mp4", b"fake mp4", "video/mp4")},
    )

    assert upload.status_code == 200
    item = upload.json()
    assert item["asset_id"]
    assert item["asset_path"].endswith(".mp4")
    assert item["thumbnail_exists"] is False

    listed = client.get("/api/assets/videos").json()["items"]
    assert [asset["asset_id"] for asset in listed] == [item["asset_id"]]

    deleted = client.delete(f"/api/assets/videos/{item['asset_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/api/assets/videos").json()["items"] == []


def test_image_asset_upload_preview_list_and_delete(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    upload = client.post(
        "/api/assets/images",
        data={"name": "夏季新品主图"},
        files={"file": ("product.webp", b"fake webp", "image/webp")},
    )

    assert upload.status_code == 200
    item = upload.json()
    assert item["asset_path"].endswith(".webp")
    assert client.get(item["file_url"]).status_code == 200
    assert [asset["asset_id"] for asset in client.get("/api/assets/images").json()["items"]] == [
        item["asset_id"]
    ]
    assert client.delete(f"/api/assets/images/{item['asset_id']}").json()["deleted"] is True
    assert client.get("/api/assets/images").json()["items"] == []
