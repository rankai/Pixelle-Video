import importlib
import io
import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from pixelle_video.services.assets_v2.repository import AssetLibraryRepository


def _image_bytes(color: str = "red") -> bytes:
    payload = io.BytesIO()
    Image.new("RGB", (32, 18), color).save(payload, format="PNG")
    return payload.getvalue()


def _transparent_image_bytes() -> bytes:
    payload = io.BytesIO()
    Image.new("RGBA", (24, 24), (109, 93, 246, 128)).save(payload, format="PNG")
    return payload.getvalue()


def test_image_transparency_is_preserved_in_revision_and_library_projection(tmp_path):
    repository = AssetLibraryRepository(tmp_path)
    payload = _transparent_image_bytes()
    session = repository.create_upload_session("transparent.png", len(payload), "image")
    repository.append_upload_chunk(session["upload_id"], payload)
    completed = repository.finalize_upload(session["upload_id"])
    asset = repository.get_asset(completed["asset_id"])
    assert asset["has_transparency"] == 1
    assert repository.list_library_page(kind="image", page_size=1)["items"][0]["resource_id"] == completed["asset_id"]


def test_legacy_image_is_migrated_with_thumbnail_and_relative_paths(tmp_path):
    image_root = tmp_path / "image_assets"
    image_root.mkdir()
    source = image_root / "product.png"
    source.write_bytes(_image_bytes())
    (image_root / "image_assets.json").write_text(
        '[{"asset_id":"legacy-image-1","filename":"product.png","name":"产品主图"}]',
        encoding="utf-8",
    )

    repository = AssetLibraryRepository(tmp_path)
    asset = repository.get_asset("media-image-legacy-image-1")

    assert asset is not None
    assert asset["source"] == "imported"
    assert asset["relative_path"] == "image_assets/product.png"
    assert not asset["relative_path"].startswith("/")
    variants = repository.get_variants(asset["asset_id"])
    assert [item["role"] for item in variants] == ["thumbnail"]
    assert repository.get_revision_path(asset["asset_id"], "thumbnail").is_file()
    with sqlite3.connect(repository.db_path) as connection:
        markers = {
            row[0]
            for row in connection.execute(
                "SELECT key FROM schema_meta WHERE key IN ('legacy_media_migration_v1', 'legacy_media_migration_v2')"
            )
        }
    assert markers == {"legacy_media_migration_v1", "legacy_media_migration_v2"}


def test_stream_upload_finalizes_and_duplicate_is_reported(tmp_path):
    repository = AssetLibraryRepository(tmp_path)
    payload = _image_bytes("blue")

    first = repository.create_upload_session("blue.png", len(payload), "image", name="蓝色产品")
    repository.append_upload_chunk(first["upload_id"], payload[:7])
    repository.append_upload_chunk(first["upload_id"], payload[7:])
    completed = repository.finalize_upload(first["upload_id"])
    assert completed["status"] == "ready"
    assert completed["asset_id"]
    asset = repository.get_asset(completed["asset_id"])
    assert asset["width"] == 32
    assert asset["height"] == 18
    assert asset["relative_path"].startswith("asset_library/media/")

    duplicate = repository.create_upload_session("same.png", len(payload), "image")
    repository.append_upload_chunk(duplicate["upload_id"], payload)
    duplicate_result = repository.finalize_upload(duplicate["upload_id"])
    assert duplicate_result["status"] == "ready"
    assert duplicate_result["duplicate_asset_id"] == completed["asset_id"]

    usage = repository.record_usage(
        completed["asset_id"], "session-1", "postproduction", "overlay_video", "group-1"
    )
    snapshot = repository.create_snapshot(
        completed["asset_id"],
        "session-1",
        "postproduction",
        template_revision=1,
        renderer_version="test-renderer",
    )
    assert usage["revision_id"] == asset["current_revision_id"]
    assert repository.list_usage("session-1")[0]["slot_id"] == "group-1"
    assert snapshot["sha256"] == asset["sha256"]
    assert not snapshot["resolved_relative_path"].startswith("/")
    assert repository.list_snapshots("session-1")[0]["renderer_version"] == "test-renderer"
    external = repository.record_external_usage(
        "voice", "voice-1", "session-1", "voice", "reference", "voice-slot"
    )
    assert external["resource_kind"] == "voice"
    assert external["resource_id"] == "voice-1"


def test_interrupted_upload_is_failed_and_temp_file_removed_on_restart(tmp_path):
    repository = AssetLibraryRepository(tmp_path)
    payload = _image_bytes()
    session = repository.create_upload_session("partial.png", len(payload), "image")
    repository.append_upload_chunk(session["upload_id"], payload[:5])
    temporary = tmp_path / session["temp_relative_path"]
    assert temporary.is_file()

    restarted = AssetLibraryRepository(tmp_path)
    recovered = restarted.get_upload_session(session["upload_id"])
    assert recovered["status"] == "failed"
    assert recovered["error_code"] == "restart_recovery"
    assert not temporary.exists()


def test_render_resolves_v2_video_asset_id_to_local_revision(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    repository = AssetLibraryRepository(tmp_path / "data")
    payload = b"not a real video, but a persisted revision fixture"
    session = repository.create_upload_session("overlay.mp4", len(payload), "video")
    repository.append_upload_chunk(session["upload_id"], payload)
    completed = repository.finalize_upload(session["upload_id"])

    from pixelle_video.services.ip_broadcast_composer import _validate_visual_overlay_assets

    _validate_visual_overlay_assets(
        [
            {
                "group_id": "v2-group",
                "visual_type": "uploaded_video",
                "video_asset_id": completed["asset_id"],
                "uploaded_video_path": "/api/v2/media-assets/not-a-real-id/file",
            }
        ]
    )


def test_v2_api_lists_and_streams_assets_without_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    module = importlib.import_module("api.routers.assets_v2")
    monkeypatch.setattr(module, "_repository", AssetLibraryRepository(tmp_path))
    monkeypatch.setattr(module.api_config, "asset_center_v2_enabled", True)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    client = TestClient(app)
    payload = _image_bytes("green")

    created = client.post(
        "/api/v2/uploads",
        json={
            "filename": "green.png",
            "declared_bytes": len(payload),
            "target_kind": "image",
            "name": "绿色产品",
        },
    )
    assert created.status_code == 201
    upload_id = created.json()["upload_id"]
    completed = client.put(
        f"/api/v2/uploads/{upload_id}/content",
        content=payload,
        headers={"content-length": str(len(payload))},
    )
    assert completed.status_code == 200
    asset = completed.json()["asset"]
    assert "/" not in asset["revision"]["relative_path"][:1]
    assert asset["file_url"] == f"/api/v2/media-assets/{asset['asset_id']}/file"
    assert client.get(asset["file_url"]).content == payload
    assert client.get("/api/v2/library/items", params={"kind": "image"}).json()["total"] == 1


def test_v2_archive_restore_and_bulk_management_are_reversible(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    module = importlib.import_module("api.routers.assets_v2")
    monkeypatch.setattr(module, "_repository", AssetLibraryRepository(tmp_path))
    monkeypatch.setattr(module.api_config, "asset_center_v2_enabled", True)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    client = TestClient(app)
    payload = _image_bytes("purple")

    created = client.post(
        "/api/v2/uploads",
        json={"filename": "purple.png", "declared_bytes": len(payload), "target_kind": "image"},
    )
    upload_id = created.json()["upload_id"]
    asset = client.put(f"/api/v2/uploads/{upload_id}/content", content=payload).json()["asset"]
    item_id = asset["asset_id"]

    archived = client.post(f"/api/v2/library/image/{item_id}/archive")
    assert archived.status_code == 200
    assert client.get("/api/v2/library/items", params={"kind": "image"}).json()["total"] == 0
    archived_items = client.get(
        "/api/v2/library/items", params={"kind": "image", "include_archived": "true"}
    ).json()
    assert archived_items["total"] == 1
    assert archived_items["items"][0]["status"] == "archived"

    bulk = client.post(
        "/api/v2/library/bulk",
        json={
            "action": "restore",
            "items": [{"kind": "image", "resource_id": item_id}],
        },
    )
    assert bulk.json()["succeeded"] == 1
    favorite = client.post(
        "/api/v2/library/bulk",
        json={
            "action": "favorite",
            "items": [{"kind": "image", "resource_id": item_id}],
        },
    )
    assert favorite.json()["succeeded"] == 1
    assert client.get("/api/v2/library/items", params={"kind": "image", "favorite": "true"}).json()["total"] == 1


def test_v2_api_is_disabled_by_default(monkeypatch):
    module = importlib.import_module("api.routers.assets_v2")
    monkeypatch.setattr(module.api_config, "asset_center_v2_enabled", False)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    assert TestClient(app).get("/api/v2/library/items").status_code == 404


def test_v2_rollback_keeps_legacy_manifest_routes_operational(monkeypatch, tmp_path):
    """The kill switch must leave the pre-V2 asset UI/API usable."""

    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    v2 = importlib.import_module("api.routers.assets_v2")
    legacy = importlib.import_module("api.routers.assets")
    monkeypatch.setattr(v2.api_config, "asset_center_v2_enabled", False)
    app = FastAPI()
    app.include_router(legacy.router, prefix="/api")
    app.include_router(v2.router, prefix="/api")
    client = TestClient(app)

    payload = _image_bytes("#7c3aed")
    created = client.post(
        "/api/assets/images",
        data={"name": "回滚图片"},
        files={"file": ("rollback.png", payload, "image/png")},
    )

    assert created.status_code == 200
    asset = created.json()
    assert asset["name"] == "回滚图片"
    assert client.get("/api/assets/images").json()["items"][0]["asset_id"] == asset["asset_id"]
    assert client.get(asset["file_url"]).content == payload
    assert client.get("/api/v2/library/items").status_code == 404

    deleted = client.delete(f"/api/assets/images/{asset['asset_id']}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get("/api/assets/images").json()["items"] == []


def test_v2_library_projects_domain_assets_without_absolute_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    voice_root = tmp_path / "data" / "voice_references"
    voice_root.mkdir(parents=True)
    (voice_root / "voice.mp3").write_bytes(b"voice")
    (voice_root / "voice_references.json").write_text(
        '[{"reference_id":"voice-1","name":"老板音色","filename":"voice.mp3","created_at":"2026-07-17"}]',
        encoding="utf-8",
    )
    portrait_root = tmp_path / "data" / "portraits"
    portrait_root.mkdir(parents=True)
    (portrait_root / "portrait.png").write_bytes(_image_bytes())
    (portrait_root / "portraits.json").write_text(
        '[{"portrait_id":"portrait-1","name":"老板形象","filename":"portrait.png","created_at":"2026-07-17","media_type":"image"}]',
        encoding="utf-8",
    )
    brand_root = tmp_path / "data" / "brand_kits"
    brand_root.mkdir(parents=True)
    (brand_root / "brand_kits.json").write_text(
        '[{"brand_id":"brand-1","brand_name":"示例品牌","created_at":"2026-07-17"}]',
        encoding="utf-8",
    )

    module = importlib.import_module("api.routers.assets_v2")
    monkeypatch.setattr(module, "_repository", AssetLibraryRepository(tmp_path / "data"))
    monkeypatch.setattr(module.api_config, "asset_center_v2_enabled", True)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    client = TestClient(app)

    for kind, expected_id in [
        ("voice", "voice-1"),
        ("digital_human", "portrait-1"),
        ("brand", "brand-1"),
        ("template", "boss_clean"),
    ]:
        response = client.get("/api/v2/library/items", params={"kind": kind})
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["resource_id"] == expected_id
        assert "asset_path" not in item
        assert str(tmp_path) not in response.text

    all_items = client.get("/api/v2/library/items").json()
    assert "audio" in {item["kind"] for item in all_items["items"]}


def test_stage1_database_is_rebuilt_before_audio_upload(tmp_path):
    db_root = tmp_path / "asset_library"
    db_root.mkdir(parents=True)
    db = db_root / "asset_library.sqlite3"
    connection = sqlite3.connect(db)
    connection.executescript(
        """
        CREATE TABLE media_assets (
            asset_id TEXT PRIMARY KEY, legacy_id TEXT,
            media_kind TEXT NOT NULL CHECK(media_kind IN ('image', 'video')),
            name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', source TEXT NOT NULL,
            current_revision_id TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, archived_at TEXT
        );
        CREATE TABLE asset_revisions (
            revision_id TEXT PRIMARY KEY, asset_id TEXT NOT NULL, version INTEGER NOT NULL,
            parent_revision_id TEXT, relative_path TEXT NOT NULL UNIQUE, mime_type TEXT NOT NULL,
            bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, width INTEGER, height INTEGER,
            aspect_ratio REAL, duration_ms INTEGER, frame_rate REAL, has_audio INTEGER,
            created_at TEXT NOT NULL, UNIQUE(asset_id, version)
        );
        CREATE TABLE upload_sessions (
            upload_id TEXT PRIMARY KEY, filename TEXT NOT NULL, declared_bytes INTEGER NOT NULL,
            received_bytes INTEGER NOT NULL DEFAULT 0,
            target_kind TEXT NOT NULL CHECK(target_kind IN ('image', 'video')),
            name TEXT, description TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,
            temp_relative_path TEXT NOT NULL UNIQUE, asset_id TEXT, duplicate_asset_id TEXT,
            error_code TEXT, error_message TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    connection.close()

    repository = AssetLibraryRepository(tmp_path)
    payload = b"audio fixture"
    session = repository.create_upload_session("voice.mp3", len(payload), "audio")
    repository.append_upload_chunk(session["upload_id"], payload)
    completed = repository.finalize_upload(session["upload_id"])
    assert completed["status"] == "ready"
    assert repository.get_asset(completed["asset_id"])["media_kind"] == "audio"


def test_existing_stage1_database_receives_incremental_legacy_audio_migration(tmp_path):
    """A v1 marker must not prevent the later voice manifest import."""

    repository = AssetLibraryRepository(tmp_path)
    voice_root = tmp_path / "voice_references"
    voice_root.mkdir()
    (voice_root / "legacy.mp3").write_bytes(b"legacy voice")
    (voice_root / "voice_references.json").write_text(
        '[{"reference_id":"voice-after-v1","name":"后加入音色","filename":"legacy.mp3"}]',
        encoding="utf-8",
    )
    with repository._connect() as connection:
        connection.execute("DELETE FROM schema_meta WHERE key = 'legacy_media_migration_v2'")

    restarted = AssetLibraryRepository(tmp_path)
    asset = restarted.get_asset_by_legacy_id("audio", "voice-after-v1")
    assert asset is not None
    assert asset["media_kind"] == "audio"


def test_domain_writes_share_library_projection_and_collection_ledger(tmp_path):
    repository = AssetLibraryRepository(tmp_path)
    brand = repository.create_brand_kit({"brand_name": "门店品牌", "primary_color": "#ff6b5c"})
    person = repository.create_digital_human_profile({"name": "老板数字人", "style": "稳重"})
    template = repository.create_template_revision({"display_name": "竖屏口播", "subtitle_contract": {"font_size": 56}})
    assert brand["resource_id"]
    assert person["resource_id"]
    assert template["summary"]["subtitle_font_size"] == 56
    repository.set_resource_tags("brand", brand["resource_id"], ["门店", "主推"])
    repository.set_favorite("digital_human", person["resource_id"], True)
    collection = repository.create_collection("本周生产")
    assert repository.add_collection_item(collection["collection_id"], "brand", brand["resource_id"])
    assert repository.list_collections()[0]["item_count"] == 1
    assert repository.resource_tags("brand", brand["resource_id"]) == ["主推", "门店"]
    assert repository.is_favorite("digital_human", person["resource_id"])
    updated_person = repository.patch_digital_human_profile(
        person["resource_id"], {"style": "活泼", "supported_workflows": ["local"]}
    )
    assert updated_person["tags"] == ["活泼"]
    extra_scene = repository.create_digital_human_scene(
        person["resource_id"], {"name": "厨房", "location": "厨房"}
    )
    assert extra_scene["name"] == "厨房"
    assert len(repository.get_domain_item("digital_human", person["resource_id"])["scenes"]) == 2
    updated_template = repository.patch_template_revision(
        template["resource_id"], {"subtitle_contract": {"font_size": 60}}
    )
    assert updated_template["summary"]["revision"] == 2
    assert len(repository.list_domain_revisions("template", template["resource_id"])) == 2


def test_domain_media_links_are_validated_and_poster_defaults_to_source(tmp_path):
    repository = AssetLibraryRepository(tmp_path)
    payload = _image_bytes("teal")
    upload = repository.create_upload_session("portrait.png", len(payload), "image")
    repository.append_upload_chunk(upload["upload_id"], payload)
    completed = repository.finalize_upload(upload["upload_id"])
    asset = repository.get_asset(completed["asset_id"])

    profile = repository.create_digital_human_profile(
        {"name": "绑定人物", "source_asset_id": asset["asset_id"]}
    )
    assert profile["poster_asset_id"] == asset["asset_id"]
    assert profile["scenes"][0]["source_revision_id"] == asset["current_revision_id"]

    try:
        repository.create_digital_human_profile(
            {"name": "坏人物", "poster_asset_id": "missing-media-id"}
        )
    except ValueError as exc:
        assert "existing image/video asset" in str(exc)
    else:
        raise AssertionError("invalid digital-human media reference should fail")


def test_digital_human_projection_keeps_cover_and_demo_scene_media_separate(tmp_path):
    repository = AssetLibraryRepository(tmp_path)

    cover_payload = _image_bytes("orange")
    cover_upload = repository.create_upload_session("boss-cover.png", len(cover_payload), "image")
    repository.append_upload_chunk(cover_upload["upload_id"], cover_payload)
    cover_result = repository.finalize_upload(cover_upload["upload_id"])
    cover_asset = repository.get_asset(cover_result["asset_id"])

    # The repository keeps the media-kind relationship even when a fixture is
    # not a playable video. Production uploads are analysed by ffprobe and get
    # a poster variant; this fixture only needs to verify the domain contract.
    demo_payload = b"demo video fixture"
    demo_upload = repository.create_upload_session("boss-demo.mp4", len(demo_payload), "video")
    repository.append_upload_chunk(demo_upload["upload_id"], demo_payload)
    demo_result = repository.finalize_upload(demo_upload["upload_id"])
    demo_asset = repository.get_asset(demo_result["asset_id"])

    profile = repository.create_digital_human_profile(
        {
            "name": "封面与演示分离的人物",
            "poster_asset_id": cover_asset["asset_id"],
            "source_asset_id": demo_asset["asset_id"],
            "source_revision_id": demo_asset["current_revision_id"],
            "scene_name": "默认演示",
        }
    )

    assert profile["cover_url"].endswith(f"/media-assets/{cover_asset['asset_id']}/file")
    assert profile["summary"]["media_type"] == "image"
    scene = profile["scenes"][0]
    assert scene["preview_media_type"] == "video"
    assert f"revision_id={demo_asset['current_revision_id']}" in scene["preview_url"]


def test_v2_api_writes_domain_assets_tags_favorites_and_collections(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    module = importlib.import_module("api.routers.assets_v2")
    monkeypatch.setattr(module, "_repository", AssetLibraryRepository(tmp_path / "data"))
    monkeypatch.setattr(module.api_config, "asset_center_v2_enabled", True)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    client = TestClient(app)
    brand = client.post("/api/v2/domain/brands", json={"brand_name": "API 品牌"})
    assert brand.status_code == 201
    brand_id = brand.json()["resource_id"]
    assert client.put(f"/api/v2/library/items/brand/{brand_id}/favorite", json={"favorite": True}).json()["favorite"]
    assert client.put(f"/api/v2/library/items/brand/{brand_id}/tags", json={"tags": ["门店"]}).json()["tags"] == ["门店"]
    collection = client.post("/api/v2/collections", json={"name": "API 集合"}).json()
    assert client.post(
        f"/api/v2/collections/{collection['collection_id']}/items",
        params={"kind": "brand", "resource_id": brand_id},
    ).status_code == 200
    item = client.get("/api/v2/library/items", params={"kind": "brand", "favorite": "true"}).json()["items"][0]
    assert item["resource_id"] == brand_id
    assert item["tags"] == ["门店"]
    assert client.post(f"/api/v2/library/brand/{brand_id}/archive").status_code == 200
    assert client.get("/api/v2/library/items", params={"kind": "brand"}).json()["total"] == 0
    archived = client.get(
        "/api/v2/library/items", params={"kind": "brand", "include_archived": "true"}
    ).json()["items"]
    assert archived[0]["status"] == "archived"
    assert client.post(f"/api/v2/library/brand/{brand_id}/restore").json()["status"] == "ready"


def test_archived_native_domain_item_is_not_reintroduced_by_legacy_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    legacy_brand_root = tmp_path / "data" / "brand_kits"
    legacy_brand_root.mkdir(parents=True)
    (legacy_brand_root / "brand_kits.json").write_text(
        '[{"brand_id":"legacy-brand","brand_name":"兼容品牌"}]',
        encoding="utf-8",
    )
    module = importlib.import_module("api.routers.assets_v2")
    monkeypatch.setattr(module, "_repository", AssetLibraryRepository(tmp_path / "data"))
    monkeypatch.setattr(module.api_config, "asset_center_v2_enabled", True)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    client = TestClient(app)

    assert client.post("/api/v2/library/brand/legacy-brand/archive").status_code == 200
    assert client.get("/api/v2/library/items", params={"kind": "brand"}).json()["total"] == 0
    archived = client.get(
        "/api/v2/library/items", params={"kind": "brand", "include_archived": "true"}
    ).json()["items"]
    assert archived[0]["resource_id"] == "legacy-brand"
    assert archived[0]["status"] == "archived"


def test_v2_api_revision_facets_bulk_and_reconciliation(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    module = importlib.import_module("api.routers.assets_v2")
    monkeypatch.setattr(module, "_repository", AssetLibraryRepository(tmp_path / "data"))
    monkeypatch.setattr(module.api_config, "asset_center_v2_enabled", True)
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    client = TestClient(app)
    payload = _image_bytes("purple")
    created = client.post("/api/v2/uploads", json={"filename": "one.png", "declared_bytes": len(payload), "target_kind": "image"}).json()
    asset_result = client.put(f"/api/v2/uploads/{created['upload_id']}/content", content=payload).json()["asset"]
    asset_id = asset_result["asset_id"]
    revision = client.post(f"/api/v2/media-assets/{asset_id}/revisions?filename=two.png", content=_image_bytes("orange"), headers={"x-filename": "two.png"})
    assert revision.status_code == 200
    revisions = client.get(f"/api/v2/media-assets/{asset_id}/revisions").json()["items"]
    assert len(revisions) == 2
    assert client.post(f"/api/v2/media-assets/{asset_id}/revisions/{revisions[-1]['revision_id']}/activate").status_code == 200
    assert client.post(f"/api/v2/media-assets/{asset_id}/analysis/retry").status_code == 200
    reconcile = client.post("/api/v2/sessions/session-reconcile/reconcile", json={"references": [{"resource_kind": "image", "resource_id": asset_id, "step": "postproduction", "purpose": "cover", "slot_id": "cover"}]})
    assert reconcile.status_code == 200
    assert reconcile.json()["written"] == 1
    assert client.get(f"/api/v2/library/image/{asset_id}/usage").json()["items"][0]["purpose"] == "cover"
    facets = client.get("/api/v2/library/facets").json()
    assert facets["kinds"]["image"] == 1
    filtered = client.get("/api/v2/library/items", params={"kind": "image", "q": "one", "sort": "recent"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert client.get("/api/v2/library/facets", params={"q": "one"}).status_code == 200
    bulk = client.post("/api/v2/library/bulk", json={"action": "favorite", "items": [{"kind": "image", "resource_id": asset_id}]})
    assert bulk.json()["succeeded"] == 1
    assert client.get("/api/v2/library/items", params={"kind": "image", "sort": "recent"}).status_code == 200


def test_digital_human_scene_resolves_its_pinned_revision(tmp_path):
    repository = AssetLibraryRepository(tmp_path)
    first_payload = _image_bytes("red")
    upload = repository.create_upload_session("portrait.png", len(first_payload), "image")
    repository.append_upload_chunk(upload["upload_id"], first_payload)
    first = repository.finalize_upload(upload["upload_id"])
    first_asset = repository.get_asset(first["asset_id"])

    second_payload = _image_bytes("blue")
    revision_part = repository.incoming_root / "pinned-revision.part"
    revision_part.write_bytes(second_payload)
    repository.create_revision_from_path(first["asset_id"], "portrait.png", revision_part)

    profile = repository.create_digital_human_profile(
        {
            "name": "固定版本人物",
            "poster_asset_id": first["asset_id"],
            "source_asset_id": first["asset_id"],
            "source_revision_id": first_asset["current_revision_id"],
        }
    )
    scene = profile["scenes"][0]
    path = repository.get_scene_source_path(scene["scene_id"])
    assert path is not None
    assert path.read_bytes() == first_payload


def test_legacy_media_routes_read_and_write_v2_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    v2 = importlib.import_module("api.routers.assets_v2")
    assets = importlib.import_module("api.routers.assets")
    repository = AssetLibraryRepository(tmp_path / "data")
    monkeypatch.setattr(v2, "_repository", repository)
    monkeypatch.setattr(v2.api_config, "asset_center_v2_enabled", True)
    app = FastAPI()
    app.include_router(assets.router, prefix="/api")
    client = TestClient(app)

    payload = _image_bytes("yellow")
    created = client.post(
        "/api/assets/images",
        data={"name": "兼容图片"},
        files={"file": ("compat.png", payload, "image/png")},
    )
    assert created.status_code == 200
    item = created.json()
    assert client.get("/api/assets/images").json()["items"][0]["asset_id"] == item["asset_id"]
    assert client.get(item["file_url"]).content == payload
    assert client.delete(f"/api/assets/images/{item['asset_id']}").json()["deleted"] is True


def test_legacy_manifest_deltas_reconcile_after_a_v2_restart(monkeypatch, tmp_path):
    """Assets added/removed while V2 is rolled back must not be lost later."""

    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    image_root = tmp_path / "data" / "image_assets"
    image_root.mkdir(parents=True)
    first_payload = _image_bytes("#f97316")
    second_payload = _image_bytes("#0ea5e9")
    (image_root / "first.png").write_bytes(first_payload)
    (image_root / "image_assets.json").write_text(
        json.dumps(
            [{"asset_id": "legacy-first", "name": "旧图一", "filename": "first.png"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    first_repository = AssetLibraryRepository(tmp_path / "data")
    assert first_repository.get_asset_by_legacy_id("image", "legacy-first")

    (image_root / "second.png").write_bytes(second_payload)
    (image_root / "image_assets.json").write_text(
        json.dumps(
            [{"asset_id": "legacy-second", "name": "旧图二", "filename": "second.png"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    restarted = AssetLibraryRepository(tmp_path / "data")
    assert restarted.get_asset_by_legacy_id("image", "legacy-second")
    assert restarted.get_asset_by_legacy_id("image", "legacy-first")["status"] == "archived"
    assert [item["legacy_id"] for item in restarted.list_assets("image")] == ["legacy-second"]


def test_legacy_domain_manifest_deltas_reconcile_after_a_v2_restart(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    portraits_root = tmp_path / "data" / "portraits"
    brands_root = tmp_path / "data" / "brand_kits"
    portraits_root.mkdir(parents=True)
    brands_root.mkdir(parents=True)
    (portraits_root / "first.png").write_bytes(_image_bytes("#a855f7"))
    (portraits_root / "portraits.json").write_text(
        json.dumps(
            [{"portrait_id": "portrait-first", "name": "人物一", "filename": "first.png"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (brands_root / "brand_kits.json").write_text(
        json.dumps(
            [{"brand_id": "brand-first", "brand_name": "品牌一"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    AssetLibraryRepository(tmp_path / "data")
    (portraits_root / "second.png").write_bytes(_image_bytes("#14b8a6"))
    (portraits_root / "portraits.json").write_text(
        json.dumps(
            [{"portrait_id": "portrait-second", "name": "人物二", "filename": "second.png"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (brands_root / "brand_kits.json").write_text(
        json.dumps(
            [{"brand_id": "brand-second", "brand_name": "品牌二"}],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    restarted = AssetLibraryRepository(tmp_path / "data")
    assert restarted.get_domain_item("digital_human", "portrait-second")
    assert restarted.get_domain_item("brand", "brand-second")
    assert restarted.get_domain_item("digital_human", "portrait-first")["status"] == "archived"
    assert restarted.get_domain_item("brand", "brand-first")["status"] == "archived"


def test_workflow_boundaries_resolve_v2_audio_and_portrait_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    repository = AssetLibraryRepository(tmp_path / "data")
    image_payload = _image_bytes("orange")
    image_upload = repository.create_upload_session("face.png", len(image_payload), "image")
    repository.append_upload_chunk(image_upload["upload_id"], image_payload)
    image_asset = repository.finalize_upload(image_upload["upload_id"])
    profile = repository.create_digital_human_profile(
        {"name": "边界人物", "poster_asset_id": image_asset["asset_id"]}
    )
    audio_payload = b"not a valid wav but a stable V2 revision"
    audio_upload = repository.create_upload_session("voice.wav", len(audio_payload), "audio")
    repository.append_upload_chunk(audio_upload["upload_id"], audio_payload)
    audio_asset = repository.finalize_upload(audio_upload["upload_id"])

    from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSession, _append_tts_params

    session = IpBroadcastSession(session_id="v2-boundary")
    session.state.update(
        {
            "portrait_id": profile["resource_id"],
            "portrait_path": f"/api/v2/media-assets/{image_asset['asset_id']}/file",
            "digital_human_scene_id": profile["summary"]["default_scene_id"],
        }
    )
    assert session._has_portrait()
    kwargs: dict[str, object] = {"inference_mode": "provider"}
    _append_tts_params(
        kwargs,
        {
            "tts_workflow": "index",
            "tts_ref_audio_id": audio_asset["asset_id"],
            "tts_ref_audio_path": f"/api/v2/media-assets/{audio_asset['asset_id']}/file",
        },
    )
    assert Path(str(kwargs["ref_audio"])).is_file()


def test_custom_template_contract_resolves_to_registered_renderer(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    repository = AssetLibraryRepository(tmp_path / "data")
    template = repository.create_template_revision(
        {
            "template_id": "storefront-custom",
            "display_name": "门店自定义",
            "cover_contract": {"base_template_id": "boss_authority"},
            "subtitle_contract": {"font_size": 61, "margin_v": 210},
        }
    )
    from pixelle_video.services.ip_broadcast_templates import (
        build_ass_force_style,
        get_ip_broadcast_template_for_render,
    )

    resolved = get_ip_broadcast_template_for_render(template["resource_id"])
    assert resolved.template_id == "storefront-custom"
    assert resolved.subtitle_style.font_size == 61
    assert resolved.subtitle_style.margin_v == 210
    assert "Fontsize=61" in build_ass_force_style(resolved)
