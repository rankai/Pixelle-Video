from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import api.routers.app_center as app_center_api
import api.routers.assets_v2 as assets_v2_api
from pixelle_video.app_center.brand_project import (
    BrandProjectService,
    ProjectContextResolver,
)
from pixelle_video.app_center.migration import migrate_app_center
from pixelle_video.app_center.project_context import (
    ProjectContextError,
    context_projection_fingerprint,
)
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository


def _image_bytes(color: str = "#6c5ce7") -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 20), color).save(output, format="PNG")
    return output.getvalue()


def _audio_bytes() -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * 1_600)
    return output.getvalue()


def _upload(repository: AssetLibraryRepository, kind: str, payload: bytes) -> dict:
    suffix = "png" if kind == "image" else "wav"
    session = repository.create_upload_session(f"brand.{suffix}", len(payload), kind)
    repository.append_upload_chunk(session["upload_id"], payload)
    return repository.finalize_upload(session["upload_id"])


def _repositories(tmp_path: Path):
    assets = AssetLibraryRepository(tmp_path / "assets")
    app = AppCenterRepository(tmp_path / "app.sqlite", asset_repository=assets)
    return app, assets


def _table_count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as connection:
        return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _fingerprint(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _database_rows(path: Path) -> dict[str, list[tuple]]:
    with sqlite3.connect(path) as connection:
        tables = [
            row[0]
            for row in connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            )
        ]
        return {
            table: connection.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
            for table in tables
        }


def _v2_payload() -> dict:
    return {
        "schema_version": 2,
        "subject_type": "store",
        "store_or_brand": {
            "name": "兼容门店",
            "industry": "零售",
            "address": None,
            "contact": None,
        },
        "offer": {
            "name": "兼容商品",
            "category": "零售",
            "price_facts": [],
            "promotion_facts": [],
        },
        "audience": {"primary": "附近顾客", "scenes": []},
        "selling_points": [],
        "proof_points": [],
        "required_facts": [],
        "forbidden_claims": [],
        "asset_refs": [],
        "brand_revision_ref": None,
    }


def test_exact_brand_domain_revision_read_never_falls_back_to_latest(tmp_path):
    _app, assets = _repositories(tmp_path)
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-history",
            "brand_name": "旧名称",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    assets.patch_brand_kit(brand["resource_id"], {"brand_name": "新名称"})

    first = assets.get_domain_revision("brand", brand["resource_id"], 1)
    second = assets.get_domain_revision("brand", brand["resource_id"], 2)
    assert first and first["payload"]["brand_name"] == "旧名称"
    assert second and second["payload"]["brand_name"] == "新名称"
    assert assets.get_domain_revision("brand", brand["resource_id"], 999) is None


def test_ready_brand_without_domain_history_fails_project_summary_closed(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    assets.create_brand_kit(
        {
            "brand_id": "brand-history-missing",
            "brand_name": "历史缺失品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    with sqlite3.connect(assets.db_path) as connection:
        connection.execute(
            """
            DELETE FROM domain_revisions
            WHERE resource_kind = 'brand' AND resource_id = ?
            """,
            ("brand-history-missing",),
        )
    assert (
        assets.domain_snapshot_metadata("brand", "brand-history-missing")["domain_revision"] is None
    )

    monkeypatch.setattr(assets_v2_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(assets_v2_api.api_config, "asset_center_v2_enabled", True)
    api = FastAPI()
    api.include_router(assets_v2_api.router, prefix="/api")
    client = TestClient(api)
    before = (_database_rows(app.db_path), _database_rows(assets.db_path))
    summary = client.get("/api/v2/domain/brands/brand-history-missing/project-summary")
    assert summary.status_code == 409
    assert summary.json()["detail"] == {
        "code": "PROJECT_BRAND_REVISION_NOT_FOUND",
        "message": "品牌历史版本无法读取，请保留当前项目资料并联系支持",
    }
    exact = client.get("/api/v2/domain/brands/brand-history-missing/revisions/1")
    assert exact.status_code == 409
    assert exact.json()["detail"] == summary.json()["detail"]
    assert (_database_rows(app.db_path), _database_rows(assets.db_path)) == before


def test_create_project_atomically_pins_brand_and_current_media_revisions(tmp_path):
    app, assets = _repositories(tmp_path)
    logo = _upload(assets, "image", _image_bytes())
    bgm = _upload(assets, "audio", _audio_bytes())
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-pinned",
            "brand_name": "街角咖啡",
            "logo_asset_id": logo["asset_id"],
            "default_bgm_asset_id": bgm["asset_id"],
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    service = BrandProjectService(app, assets)
    project, snapshot = service.create_project(
        "下午茶推广",
        "吸引周边上班族到店",
        brand_id=brand["resource_id"],
        expected_domain_revision=1,
    )

    assert project.brand_id == "brand-pinned"
    assert project.current_context_snapshot_id == snapshot.context_snapshot_id
    assert snapshot.schema_version == 3
    assert snapshot.source_brand_id == "brand-pinned"
    assert snapshot.source_brand_revision_id == "1"
    values = snapshot.payload["brand_context"]["values"]
    assert values["logo_ref"] == {
        "asset_id": logo["asset_id"],
        "asset_revision": assets.get_asset(logo["asset_id"])["current_revision_id"],
    }
    assert values["default_bgm_ref"] == {
        "asset_id": bgm["asset_id"],
        "asset_revision": assets.get_asset(bgm["asset_id"])["current_revision_id"],
    }

    assets.patch_brand_kit("brand-pinned", {"brand_name": "街角咖啡新名"})
    resolved = ProjectContextResolver(app, assets).resolve_for_run(project.project_id)
    assert resolved.brand_summary["display_name"] == "街角咖啡"
    assert resolved.brand_summary["domain_revision"] == 1


def test_failed_brand_resolution_leaves_project_database_unchanged(tmp_path):
    app, assets = _repositories(tmp_path)
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-archived",
            "brand_name": "已归档品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    assets.patch_brand_kit(brand["resource_id"], {"status": "archived"})
    before = (
        _table_count(app.db_path, "content_projects"),
        _table_count(app.db_path, "context_snapshots"),
    )

    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).create_project(
            "不应创建", "验证原子性", brand_id=brand["resource_id"]
        )
    assert exc.value.code == "PROJECT_BRAND_NOT_AVAILABLE"
    assert before == (
        _table_count(app.db_path, "content_projects"),
        _table_count(app.db_path, "context_snapshots"),
    )


def test_missing_brand_or_media_revision_fails_closed_before_project_write(tmp_path):
    app, assets = _repositories(tmp_path)
    logo = _upload(assets, "image", _image_bytes())
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-missing-media",
            "brand_name": "缺失媒体品牌",
            "logo_asset_id": logo["asset_id"],
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    assert assets.archive_asset(logo["asset_id"]) is True
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).create_project(
            "媒体不可用", "验证失败关闭", brand_id=brand["resource_id"]
        )
    assert exc.value.code == "PROJECT_BRAND_ASSET_REVISION_MISSING"
    assert _table_count(app.db_path, "content_projects") == 0

    assets.create_brand_kit(
        {
            "brand_id": "brand-missing-revision",
            "brand_name": "缺失版本品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    with sqlite3.connect(assets.db_path) as connection:
        connection.execute(
            "DELETE FROM domain_revisions WHERE resource_kind = 'brand' AND resource_id = ?",
            ("brand-missing-revision",),
        )
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).create_project(
            "版本不可用", "验证失败关闭", brand_id="brand-missing-revision"
        )
    assert exc.value.code == "PROJECT_BRAND_REVISION_NOT_FOUND"
    assert _table_count(app.db_path, "content_projects") == 0


def test_explicit_bind_change_and_unbind_are_immutable_and_conflict_safe(tmp_path):
    app, assets = _repositories(tmp_path)
    first = assets.create_brand_kit(
        {
            "brand_id": "brand-first",
            "brand_name": "品牌一",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    second = assets.create_brand_kit(
        {
            "brand_id": "brand-second",
            "brand_name": "品牌二",
            "primary_color": "#778899",
            "secondary_color": "#AABBCC",
        }
    )
    project = app.create_project("历史项目", "到店")
    service = BrandProjectService(app, assets)
    bound, first_snapshot = service.replace_binding(
        project.project_id,
        brand_id=first["resource_id"],
        expected_context_snapshot_id=None,
    )
    changed, second_snapshot = service.replace_binding(
        project.project_id,
        brand_id=second["resource_id"],
        expected_context_snapshot_id=first_snapshot.context_snapshot_id,
        project_overrides={"phone": "仅本项目电话"},
    )
    assert bound.brand_id == "brand-first"
    assert changed.brand_id == "brand-second"
    assert second_snapshot.payload["brand_context"]["overridden_fields"] == ["phone"]
    assert (
        app.get_context_snapshot(first_snapshot.context_snapshot_id).payload["brand_context"][
            "brand_id"
        ]
        == "brand-first"
    )

    with pytest.raises(ProjectContextError) as exc:
        service.replace_binding(
            project.project_id,
            brand_id=first["resource_id"],
            expected_context_snapshot_id=first_snapshot.context_snapshot_id,
        )
    assert exc.value.code == "PROJECT_CONTEXT_CONFLICT"

    unbound, unbound_snapshot = service.replace_binding(
        project.project_id,
        brand_id=None,
        expected_context_snapshot_id=second_snapshot.context_snapshot_id,
    )
    assert unbound.brand_id is None
    assert unbound_snapshot.payload["brand_context"] is None
    assert unbound_snapshot.source_brand_id is None
    assert unbound_snapshot.source_brand_revision_id is None

    app.archive_project(project.project_id)
    with pytest.raises(ProjectContextError) as exc:
        service.replace_binding(
            project.project_id,
            brand_id=first["resource_id"],
            expected_context_snapshot_id=unbound_snapshot.context_snapshot_id,
        )
    assert exc.value.code == "PROJECT_ARCHIVED"


def test_resolver_reads_v1_v2_v3_without_writing(tmp_path):
    app, assets = _repositories(tmp_path)
    project = app.create_project("兼容项目", "到店")
    v1 = app.save_context_snapshot(project.project_id, {"store_name": "旧门店"}, schema_version=1)
    resolver = ProjectContextResolver(app, assets)
    resolved = resolver.resolve_for_run(project.project_id, v1.context_snapshot_id)
    assert resolved.source_schema_version == 1
    assert resolved.business_payload == {"store_name": "旧门店"}
    v2_payload = _v2_payload()
    v2 = app.save_context_snapshot(project.project_id, v2_payload, schema_version=2)
    resolved_v2 = resolver.resolve_for_run(project.project_id, v2.context_snapshot_id)
    assert resolved_v2.source_schema_version == 2
    assert resolved_v2.business_payload == v2_payload
    before = (
        _table_count(app.db_path, "content_projects"),
        _table_count(app.db_path, "context_snapshots"),
        _table_count(assets.db_path, "domain_revisions"),
    )
    resolver.resolve_for_run(project.project_id, v1.context_snapshot_id)
    resolver.resolve_for_run(project.project_id, v2.context_snapshot_id)
    assert before == (
        _table_count(app.db_path, "content_projects"),
        _table_count(app.db_path, "context_snapshots"),
        _table_count(assets.db_path, "domain_revisions"),
    )


def test_api_rejects_forged_v3_and_exposes_read_only_brand_revision_routes(monkeypatch, tmp_path):
    app_repository, assets = _repositories(tmp_path)
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-api",
            "brand_name": "API 品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app_repository)
    monkeypatch.setattr(app_center_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(assets_v2_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", True)
    monkeypatch.setattr(assets_v2_api.api_config, "asset_center_v2_enabled", True)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    api.include_router(assets_v2_api.router, prefix="/api")
    client = TestClient(api)

    created = client.post(
        "/api/content-projects",
        json={
            "name": "品牌项目",
            "primary_goal": "到店",
            "brand_id": brand["resource_id"],
            "expected_brand_domain_revision": 1,
        },
    )
    assert created.status_code == 201
    project_id = created.json()["project_id"]
    forged = client.post(
        f"/api/content-projects/{project_id}/context-snapshots",
        json={
            "schema_version": 3,
            "payload": {
                "schema_version": 3,
                "brand_context": {"brand_id": "forged"},
                "project_brief": {},
            },
            "source_brand_revision_id": "999",
        },
    )
    assert forged.status_code == 422
    assert forged.json()["detail"]["code"] == "PROJECT_BRAND_CONTEXT_UNTRUSTED"
    extra = client.post(
        "/api/content-projects",
        json={"name": "伪造", "primary_goal": "到店", "source_brand_revision_id": "9"},
    )
    assert extra.status_code == 422
    compatible_v1_source = client.post(
        f"/api/content-projects/{project_id}/context-snapshots",
        json={
            "schema_version": 1,
            "payload": {"store_name": "兼容来源"},
            "source_brand_id": "brand-api",
            "source_brand_revision_id": "1",
        },
    )
    assert compatible_v1_source.status_code == 201
    assert compatible_v1_source.json()["source_brand_id"] == "brand-api"
    compatible_v2_payload = _v2_payload()
    compatible_v2_payload["brand_revision_ref"] = "brand:brand-api@1"
    compatible_v2_source = client.post(
        f"/api/content-projects/{project_id}/context-snapshots",
        json={
            "schema_version": 2,
            "payload": compatible_v2_payload,
            "source_brand_id": "brand-api",
            "source_brand_revision_id": "1",
        },
    )
    assert compatible_v2_source.status_code == 201
    mismatched_source = client.post(
        f"/api/content-projects/{project_id}/context-snapshots",
        json={
            "schema_version": 1,
            "payload": {"store_name": "伪造来源"},
            "source_brand_id": "brand-other",
            "source_brand_revision_id": "1",
        },
    )
    assert mismatched_source.status_code == 422
    assert mismatched_source.json()["detail"]["code"] == "PROJECT_BRAND_CONTEXT_UNTRUSTED"
    missing_source_revision = client.post(
        f"/api/content-projects/{project_id}/context-snapshots",
        json={
            "schema_version": 1,
            "payload": {"store_name": "缺失历史版本"},
            "source_brand_id": "brand-api",
            "source_brand_revision_id": "9",
        },
    )
    assert missing_source_revision.status_code == 409
    assert missing_source_revision.json()["detail"]["code"] == "PROJECT_BRAND_REVISION_NOT_FOUND"
    missing_expected_revision = client.post(
        f"/api/content-projects/{project_id}/brand-binding",
        json={
            "brand_id": "brand-api",
            "expected_context_snapshot_id": created.json()["current_context_snapshot_id"],
        },
    )
    assert missing_expected_revision.status_code == 422
    assert missing_expected_revision.json()["detail"]["code"] == "PROJECT_BRAND_CONTEXT_UNTRUSTED"

    before = (
        _table_count(app_repository.db_path, "content_projects"),
        _table_count(app_repository.db_path, "context_snapshots"),
        _table_count(assets.db_path, "domain_revisions"),
    )
    assert client.get("/api/v2/domain/brands").status_code == 200
    summary = client.get("/api/v2/domain/brands/brand-api/project-summary")
    revision = client.get("/api/v2/domain/brands/brand-api/revisions/1")
    assert summary.json()["domain_revision"] == 1
    assert revision.json()["values"]["brand_name"] == "API 品牌"
    missing_summary = client.get("/api/v2/domain/brands/brand-missing/project-summary")
    assert missing_summary.status_code == 404
    assert missing_summary.json()["detail"] == {
        "code": "PROJECT_BRAND_NOT_FOUND",
        "message": "这个品牌已不存在，请重新选择",
    }
    missing_brand_revision = client.get("/api/v2/domain/brands/brand-missing/revisions/1")
    assert missing_brand_revision.status_code == 404
    assert missing_brand_revision.json()["detail"]["code"] == "PROJECT_BRAND_NOT_FOUND"
    missing_revision = client.get("/api/v2/domain/brands/brand-api/revisions/999")
    assert missing_revision.status_code == 409
    assert missing_revision.json()["detail"] == {
        "code": "PROJECT_BRAND_REVISION_NOT_FOUND",
        "message": "品牌历史版本无法读取，请保留当前项目资料并联系支持",
    }
    encoded = str(summary.json()) + str(revision.json())
    assert str(tmp_path) not in encoded
    assert before == (
        _table_count(app_repository.db_path, "content_projects"),
        _table_count(app_repository.db_path, "context_snapshots"),
        _table_count(assets.db_path, "domain_revisions"),
    )


def test_brand_project_api_error_contract_is_strict_and_user_safe(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    ready = assets.create_brand_kit(
        {
            "brand_id": "brand-error-ready",
            "brand_name": "正常品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    archived = assets.create_brand_kit(
        {
            "brand_id": "brand-error-archived",
            "brand_name": "归档品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    assets.patch_brand_kit(archived["resource_id"], {"status": "archived"})
    missing_revision = assets.create_brand_kit(
        {
            "brand_id": "brand-error-revision",
            "brand_name": "缺失版本品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    with sqlite3.connect(assets.db_path) as connection:
        connection.execute(
            """
            DELETE FROM domain_revisions
            WHERE resource_kind = 'brand' AND resource_id = ?
            """,
            (missing_revision["resource_id"],),
        )

    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app)
    monkeypatch.setattr(app_center_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", True)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    client = TestClient(api)

    cases = [
        (
            client.post(
                "/api/content-projects",
                json={
                    "name": "不存在",
                    "primary_goal": "失败关闭",
                    "brand_id": "brand-error-missing",
                    "expected_brand_domain_revision": 1,
                },
            ),
            404,
            "PROJECT_BRAND_NOT_FOUND",
            "这个品牌已不存在，请重新选择",
        ),
        (
            client.post(
                "/api/content-projects",
                json={
                    "name": "已归档",
                    "primary_goal": "失败关闭",
                    "brand_id": archived["resource_id"],
                    "expected_brand_domain_revision": 2,
                },
            ),
            409,
            "PROJECT_BRAND_NOT_AVAILABLE",
            "这个品牌当前不可用于新项目",
        ),
        (
            client.post(
                "/api/content-projects",
                json={
                    "name": "版本缺失",
                    "primary_goal": "失败关闭",
                    "brand_id": missing_revision["resource_id"],
                    "expected_brand_domain_revision": 1,
                },
            ),
            409,
            "PROJECT_BRAND_REVISION_NOT_FOUND",
            "品牌历史版本无法读取，请保留当前项目资料并联系支持",
        ),
        (
            client.post(
                "/api/content-projects",
                json={
                    "name": "缺少版本期望",
                    "primary_goal": "失败关闭",
                    "brand_id": ready["resource_id"],
                },
            ),
            422,
            "PROJECT_BRAND_CONTEXT_UNTRUSTED",
            "品牌资料需要由系统重新校验，请刷新后重试",
        ),
    ]
    for response, expected_status, expected_code, expected_message in cases:
        assert response.status_code == expected_status
        assert response.json()["detail"] == {
            "code": expected_code,
            "message": expected_message,
        }
        encoded = json.dumps(response.json(), ensure_ascii=False)
        assert str(tmp_path) not in encoded
        assert "brand-error-" not in encoded
        assert "sqlite" not in encoded.lower()

    project, snapshot = BrandProjectService(app, assets).create_project(
        "冲突项目",
        "失败关闭",
        brand_id=ready["resource_id"],
        expected_domain_revision=1,
    )
    conflict = client.post(
        f"/api/content-projects/{project.project_id}/brand-binding",
        json={
            "brand_id": ready["resource_id"],
            "expected_context_snapshot_id": None,
            "expected_domain_revision": 1,
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"] == {
        "code": "PROJECT_CONTEXT_CONFLICT",
        "message": "项目信息已在其他位置更新，请刷新后重试",
    }
    assert snapshot.context_snapshot_id not in json.dumps(conflict.json(), ensure_ascii=False)


def test_resolver_rejects_tampered_source_revision(tmp_path):
    app, assets = _repositories(tmp_path)
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-tamper",
            "brand_name": "可信品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    project, snapshot = BrandProjectService(app, assets).create_project(
        "可信项目", "到店", brand_id=brand["resource_id"]
    )
    tampered = deepcopy(snapshot.payload)
    tampered["brand_context"]["values"]["display_name"] = "伪造品牌"
    with sqlite3.connect(app.db_path) as connection:
        connection.execute(
            "UPDATE context_snapshots SET payload_json = ? WHERE context_snapshot_id = ?",
            (
                __import__("json").dumps(tampered, ensure_ascii=False),
                snapshot.context_snapshot_id,
            ),
        )
    with pytest.raises(ProjectContextError) as exc:
        ProjectContextResolver(app, assets).resolve_for_run(project.project_id)
    assert exc.value.code == "PROJECT_BRAND_CONTEXT_UNTRUSTED"


def test_concurrent_null_expected_binding_allows_exactly_one_success(tmp_path):
    app, assets = _repositories(tmp_path)
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-concurrent",
            "brand_name": "并发品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    project = app.create_project("并发项目", "只允许一次绑定")
    barrier = threading.Barrier(2)

    def bind_once() -> str:
        service = BrandProjectService(app, assets)
        barrier.wait()
        try:
            service.replace_binding(
                project.project_id,
                brand_id=brand["resource_id"],
                expected_context_snapshot_id=None,
                expected_domain_revision=1,
            )
            return "success"
        except ProjectContextError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: bind_once(), range(2)))
    assert sorted(results) == ["PROJECT_CONTEXT_CONFLICT", "success"]
    assert _table_count(app.db_path, "context_snapshots") == 1


def test_v1_v2_payload_only_fingerprints_remain_readable_without_rewrite(tmp_path):
    app, assets = _repositories(tmp_path)
    project = app.create_project("旧指纹", "兼容读取")
    v1 = app.save_context_snapshot(project.project_id, {"store_name": "旧门店"}, schema_version=1)
    v2 = app.save_context_snapshot(project.project_id, _v2_payload(), schema_version=2)
    with sqlite3.connect(app.db_path) as connection:
        connection.execute(
            "UPDATE context_snapshots SET fingerprint = ? WHERE context_snapshot_id = ?",
            (_fingerprint(v1.payload), v1.context_snapshot_id),
        )
        connection.execute(
            "UPDATE context_snapshots SET fingerprint = ? WHERE context_snapshot_id = ?",
            (_fingerprint(v2.payload), v2.context_snapshot_id),
        )
    before = _database_rows(app.db_path)
    restarted_app = AppCenterRepository(app.db_path, asset_repository=assets)
    resolver = ProjectContextResolver(restarted_app, assets)
    assert (
        resolver.resolve_for_run(project.project_id, v1.context_snapshot_id).business_payload[
            "store_name"
        ]
        == "旧门店"
    )
    assert (
        resolver.resolve_for_run(project.project_id, v2.context_snapshot_id).source_schema_version
        == 2
    )
    assert _database_rows(app.db_path) == before


def test_v3_projection_and_flag_off_api_are_pure_reads(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    logo = _upload(assets, "image", _image_bytes())
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-projection",
            "brand_name": "投影品牌",
            "logo_asset_id": logo["asset_id"],
            "store_address": "上海市测试路 1 号",
            "phone": "021-00000000",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    project, snapshot = BrandProjectService(app, assets).create_project(
        "投影项目", "到店", brand_id=brand["resource_id"]
    )
    resolver = ProjectContextResolver(app, assets)
    projection = resolver.resolve_v2_projection(project.project_id, snapshot.context_snapshot_id)
    assert projection["schema_version"] == 2
    assert projection["store_or_brand"] == {
        "name": "投影品牌",
        "industry": "未分类",
        "address": "上海市测试路 1 号",
        "contact": "021-00000000",
    }
    assert projection["brand_revision_ref"] == "brand:brand-projection@1"
    assert projection["asset_refs"] == [
        {
            "asset_id": logo["asset_id"],
            "asset_revision": assets.get_asset(logo["asset_id"])["current_revision_id"],
        }
    ]

    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app)
    monkeypatch.setattr(app_center_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", False)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    client = TestClient(api)
    before = (_database_rows(app.db_path), _database_rows(assets.db_path))
    response = client.get(f"/api/content-projects/{project.project_id}/context-snapshots")
    assert response.status_code == 200
    assert response.json()["schema_version"] == 2
    assert response.json()["payload"] == projection
    assert response.json()["projection_kind"] == "context_snapshot_v2"
    assert response.json()["source_context_snapshot_id"] == snapshot.context_snapshot_id
    assert "fingerprint" not in response.json()
    assert response.json()["projection_fingerprint"] == context_projection_fingerprint(
        project_id=project.project_id,
        source_context_snapshot_id=snapshot.context_snapshot_id,
        payload=projection,
    )
    assert (_database_rows(app.db_path), _database_rows(assets.db_path)) == before


@pytest.mark.parametrize("corrupt_payload", ["{bad-json", "[]"])
def test_corrupt_brand_revision_payload_fails_closed(monkeypatch, tmp_path, corrupt_payload):
    app, assets = _repositories(tmp_path)
    assets.create_brand_kit(
        {
            "brand_id": "brand-corrupt",
            "brand_name": "损坏品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    with sqlite3.connect(assets.db_path) as connection:
        connection.execute(
            """
            UPDATE domain_revisions SET payload_json = ?
            WHERE resource_kind = 'brand' AND resource_id = ? AND revision = 1
            """,
            (corrupt_payload, "brand-corrupt"),
        )
    with pytest.raises(ValueError, match="domain_revision_payload_invalid"):
        assets.get_domain_revision("brand", "brand-corrupt", 1)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).create_project(
            "损坏版本", "失败关闭", brand_id="brand-corrupt"
        )
    assert exc.value.code == "PROJECT_BRAND_REVISION_NOT_FOUND"

    monkeypatch.setattr(assets_v2_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(assets_v2_api.api_config, "asset_center_v2_enabled", True)
    api = FastAPI()
    api.include_router(assets_v2_api.router, prefix="/api")
    response = TestClient(api).get("/api/v2/domain/brands/brand-corrupt/revisions/1")
    assert response.status_code == 409
    assert response.json()["detail"] == {
        "code": "PROJECT_BRAND_REVISION_NOT_FOUND",
        "message": "品牌历史版本无法读取，请保留当前项目资料并联系支持",
    }


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.pop("brand_name"),
        lambda payload: payload.update({"phone": 13800138000}),
        lambda payload: payload.update({"brand_id": "brand-other"}),
    ],
)
def test_brand_revision_structure_is_strict_and_never_defaulted_or_coerced(tmp_path, mutator):
    app, assets = _repositories(tmp_path)
    assets.create_brand_kit(
        {
            "brand_id": "brand-strict-revision",
            "brand_name": "严格品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    with sqlite3.connect(assets.db_path) as connection:
        payload = json.loads(
            connection.execute(
                """
                SELECT payload_json FROM domain_revisions
                WHERE resource_kind = 'brand' AND resource_id = ? AND revision = 1
                """,
                ("brand-strict-revision",),
            ).fetchone()[0]
        )
        mutator(payload)
        connection.execute(
            """
            UPDATE domain_revisions SET payload_json = ?
            WHERE resource_kind = 'brand' AND resource_id = ? AND revision = 1
            """,
            (json.dumps(payload, ensure_ascii=False), "brand-strict-revision"),
        )
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).create_project(
            "严格版本", "失败关闭", brand_id="brand-strict-revision"
        )
    assert exc.value.code == "PROJECT_BRAND_REVISION_NOT_FOUND"
    assert _database_rows(app.db_path) == before


def test_create_revalidates_brand_archive_between_resolve_and_appdb_write(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    assets.create_brand_kit(
        {
            "brand_id": "brand-race-archive",
            "brand_name": "并发归档",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    original_guard = assets.guard_domain_revision

    @contextmanager
    def archive_before_guard(*args, **kwargs):
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(
                assets.patch_brand_kit,
                "brand-race-archive",
                {"status": "archived"},
            ).result()
        with original_guard(*args, **kwargs):
            yield

    monkeypatch.setattr(assets, "guard_domain_revision", archive_before_guard)
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).create_project(
            "并发归档项目",
            "不得落半成品",
            brand_id="brand-race-archive",
            expected_domain_revision=1,
        )
    assert exc.value.code == "PROJECT_BRAND_NOT_AVAILABLE"
    assert _database_rows(app.db_path) == before


def test_bind_revalidates_brand_update_between_resolve_and_appdb_write(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    assets.create_brand_kit(
        {
            "brand_id": "brand-race-update",
            "brand_name": "并发更新前",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    project = app.create_project("待绑定", "不得落孤立快照")
    original_guard = assets.guard_domain_revision

    @contextmanager
    def update_before_guard(*args, **kwargs):
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(
                assets.patch_brand_kit,
                "brand-race-update",
                {"brand_name": "并发更新后"},
            ).result()
        with original_guard(*args, **kwargs):
            yield

    monkeypatch.setattr(assets, "guard_domain_revision", update_before_guard)
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).replace_binding(
            project.project_id,
            brand_id="brand-race-update",
            expected_context_snapshot_id=None,
            expected_domain_revision=1,
        )
    assert exc.value.code == "PROJECT_CONTEXT_CONFLICT"
    assert _database_rows(app.db_path) == before


def test_resolver_checks_pinned_brand_media_identity_revision_and_type(tmp_path):
    app, assets = _repositories(tmp_path)
    first_logo = _upload(assets, "image", _image_bytes())
    second_logo = _upload(assets, "image", _image_bytes("#445566"))
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-media-check",
            "brand_name": "媒体校验品牌",
            "logo_asset_id": first_logo["asset_id"],
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    project, snapshot = BrandProjectService(app, assets).create_project(
        "媒体校验", "防止替换", brand_id=brand["resource_id"]
    )
    tampered = deepcopy(snapshot.payload)
    tampered["brand_context"]["values"]["logo_ref"] = {
        "asset_id": second_logo["asset_id"],
        "asset_revision": assets.get_asset(second_logo["asset_id"])["current_revision_id"],
    }
    envelope = {
        "schema_version": 3,
        "payload": tampered,
        "source_brand_id": snapshot.source_brand_id,
        "source_brand_revision_id": snapshot.source_brand_revision_id,
    }
    with sqlite3.connect(app.db_path) as connection:
        connection.execute(
            """
            UPDATE context_snapshots SET payload_json = ?, fingerprint = ?
            WHERE context_snapshot_id = ?
            """,
            (
                json.dumps(tampered, ensure_ascii=False, sort_keys=True),
                _fingerprint(envelope),
                snapshot.context_snapshot_id,
            ),
        )
    with pytest.raises(ProjectContextError) as exc:
        ProjectContextResolver(app, assets).resolve_for_run(project.project_id)
    assert exc.value.code == "PROJECT_BRAND_CONTEXT_UNTRUSTED"

    audio = _upload(assets, "audio", _audio_bytes())
    clean_project, clean_snapshot = BrandProjectService(app, assets).create_project(
        "媒体类型校验", "拒绝错误类型", brand_id=brand["resource_id"]
    )
    wrong_type = deepcopy(clean_snapshot.payload)
    wrong_type["brand_context"]["values"]["logo_ref"] = {
        "asset_id": audio["asset_id"],
        "asset_revision": assets.get_asset(audio["asset_id"])["current_revision_id"],
    }
    wrong_type["brand_context"]["overridden_fields"] = ["logo_ref"]
    wrong_envelope = {
        "schema_version": 3,
        "payload": wrong_type,
        "source_brand_id": clean_snapshot.source_brand_id,
        "source_brand_revision_id": clean_snapshot.source_brand_revision_id,
    }
    with sqlite3.connect(app.db_path) as connection:
        connection.execute(
            """
            UPDATE context_snapshots SET payload_json = ?, fingerprint = ?
            WHERE context_snapshot_id = ?
            """,
            (
                json.dumps(wrong_type, ensure_ascii=False, sort_keys=True),
                _fingerprint(wrong_envelope),
                clean_snapshot.context_snapshot_id,
            ),
        )
    with pytest.raises(ProjectContextError) as exc:
        ProjectContextResolver(app, assets).resolve_for_run(clean_project.project_id)
    assert exc.value.code == "PROJECT_BRAND_ASSET_REVISION_MISSING"


def test_rebind_rejects_tampered_current_snapshot_without_washing_history(tmp_path):
    app, assets = _repositories(tmp_path)
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-rebind-tamper",
            "brand_name": "重绑品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    project, snapshot = BrandProjectService(app, assets).create_project(
        "防洗白", "校验当前快照", brand_id=brand["resource_id"]
    )
    tampered = deepcopy(snapshot.payload)
    tampered["project_brief"]["marketing_goal"] = "被篡改"
    with sqlite3.connect(app.db_path) as connection:
        connection.execute(
            "UPDATE context_snapshots SET payload_json = ? WHERE context_snapshot_id = ?",
            (json.dumps(tampered, ensure_ascii=False), snapshot.context_snapshot_id),
        )
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).replace_binding(
            project.project_id,
            brand_id=brand["resource_id"],
            expected_context_snapshot_id=snapshot.context_snapshot_id,
            expected_domain_revision=1,
        )
    assert exc.value.code == "PROJECT_BRAND_CONTEXT_UNTRUSTED"
    assert _database_rows(app.db_path) == before


def test_v2_and_v1_binding_mapping_preserves_fields_or_blocks(tmp_path):
    app, assets = _repositories(tmp_path)
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-mapping",
            "brand_name": "目标品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    v2_project = app.create_project("v2 项目", "到店")
    v2_payload = _v2_payload()
    v2_payload["store_or_brand"].update(
        {"name": "项目专用店名", "address": "项目地址", "contact": "项目电话"}
    )
    v2_snapshot = app.save_context_snapshot(v2_project.project_id, v2_payload, schema_version=2)
    _bound, mapped = BrandProjectService(app, assets).replace_binding(
        v2_project.project_id,
        brand_id=brand["resource_id"],
        expected_context_snapshot_id=v2_snapshot.context_snapshot_id,
        expected_domain_revision=1,
    )
    assert mapped.payload["brand_context"]["overridden_fields"] == [
        "display_name",
        "phone",
        "store_address",
    ]
    assert mapped.payload["brand_context"]["values"]["display_name"] == "项目专用店名"
    assert mapped.payload["project_brief"]["offer"] == v2_payload["offer"]

    blocked_project = app.create_project("v1 不完整", "到店")
    blocked = app.save_context_snapshot(
        blocked_project.project_id, {"store_name": "只有店名"}, schema_version=1
    )
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).replace_binding(
            blocked_project.project_id,
            brand_id=brand["resource_id"],
            expected_context_snapshot_id=blocked.context_snapshot_id,
            expected_domain_revision=1,
        )
    assert exc.value.code == "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED"
    assert _database_rows(app.db_path) == before

    complete_project = app.create_project("v1 完整", "引导到店")
    complete = app.save_context_snapshot(
        complete_project.project_id,
        {
            "store_name": "旧项目门店",
            "industry": "咖啡餐饮",
            "offer_name": "下午茶套餐",
            "target_audience": "附近上班族",
            "selling_points": ["现磨咖啡"],
        },
        schema_version=1,
    )
    _project, complete_v3 = BrandProjectService(app, assets).replace_binding(
        complete_project.project_id,
        brand_id=brand["resource_id"],
        expected_context_snapshot_id=complete.context_snapshot_id,
        expected_domain_revision=1,
    )
    assert complete_v3.payload["project_brief"]["offer"]["name"] == "下午茶套餐"
    assert complete_v3.payload["project_brief"]["selling_points"][0]["text"] == "现磨咖啡"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("store_name", {"name": "字典门店"}),
        ("offer_name", ["列表商品"]),
        ("target_audience", 123),
        ("address", {"city": "上海"}),
        ("selling_points", [{"text": "缺少规范 fact_id/source"}]),
        ("forbidden_claims", {"text": "字典禁用词"}),
    ],
)
def test_v1_binding_mapping_rejects_ambiguous_legacy_values(tmp_path, field, value):
    app, assets = _repositories(tmp_path)
    assets.create_brand_kit(
        {
            "brand_id": "brand-legacy-strict",
            "brand_name": "严格映射品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    payload = {
        "store_name": "旧门店",
        "industry": "零售",
        "offer_name": "旧商品",
        "target_audience": "附近顾客",
    }
    payload[field] = value
    project = app.create_project("旧资料", "到店")
    snapshot = app.save_context_snapshot(project.project_id, payload, schema_version=1)
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).replace_binding(
            project.project_id,
            brand_id="brand-legacy-strict",
            expected_context_snapshot_id=snapshot.context_snapshot_id,
            expected_domain_revision=1,
        )
    assert exc.value.code == "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED"
    assert _database_rows(app.db_path) == before


def test_v1_mapping_accepts_strict_context_fact_objects(tmp_path):
    app, assets = _repositories(tmp_path)
    assets.create_brand_kit(
        {
            "brand_id": "brand-legacy-fact",
            "brand_name": "规范事实品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    project = app.create_project("规范事实", "到店")
    snapshot = app.save_context_snapshot(
        project.project_id,
        {
            "store_name": "旧门店",
            "industry": "零售",
            "offer_name": "旧商品",
            "target_audience": "附近顾客",
            "selling_points": [
                {
                    "fact_id": "legacy-fact-1",
                    "text": "规范事实",
                    "source": "user",
                    "source_ref": None,
                }
            ],
        },
        schema_version=1,
    )
    _project, rebound = BrandProjectService(app, assets).replace_binding(
        project.project_id,
        brand_id="brand-legacy-fact",
        expected_context_snapshot_id=snapshot.context_snapshot_id,
        expected_domain_revision=1,
    )
    assert rebound.payload["project_brief"]["selling_points"] == [
        {
            "fact_id": "legacy-fact-1",
            "text": "规范事实",
            "source": "user",
            "source_ref": None,
        }
    ]


def test_read_apis_and_resolver_preserve_every_row_in_both_databases(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    brand = assets.create_brand_kit(
        {
            "brand_id": "brand-zero-write",
            "brand_name": "零写品牌",
            "primary_color": "#112233",
            "secondary_color": "#445566",
        }
    )
    project, snapshot = BrandProjectService(app, assets).create_project(
        "零写项目", "只读验证", brand_id=brand["resource_id"]
    )
    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app)
    monkeypatch.setattr(app_center_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(assets_v2_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", False)
    monkeypatch.setattr(assets_v2_api.api_config, "asset_center_v2_enabled", True)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    api.include_router(assets_v2_api.router, prefix="/api")
    client = TestClient(api)
    before = (_database_rows(app.db_path), _database_rows(assets.db_path))
    for _ in range(3):
        assert client.get("/api/content-projects").status_code == 200
        assert client.get(f"/api/content-projects/{project.project_id}").status_code == 200
        assert (
            client.get(f"/api/content-projects/{project.project_id}/context-snapshots").status_code
            == 200
        )
        assert client.get("/api/v2/domain/brands").status_code == 200
        assert (
            client.get("/api/v2/domain/brands/brand-zero-write/project-summary").status_code == 200
        )
        assert client.get("/api/v2/domain/brands/brand-zero-write/revisions/1").status_code == 200
        resolver = ProjectContextResolver(app, assets)
        resolver.resolve_for_run(project.project_id, snapshot.context_snapshot_id)
        resolver.resolve_v2_projection(project.project_id, snapshot.context_snapshot_id)
    assert (_database_rows(app.db_path), _database_rows(assets.db_path)) == before


def test_migration_upgrades_in_1_2_constraint_and_preserves_v2_rows(tmp_path):
    db_path = tmp_path / "migration.sqlite"
    repository = AppCenterRepository(db_path)
    project = repository.create_project("迁移项目", "保留 v2")
    snapshot = repository.save_context_snapshot(project.project_id, _v2_payload(), schema_version=2)
    run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "迁移"},
        idempotency_key="brand-project-migration-run",
        context_snapshot_id=snapshot.context_snapshot_id,
    )
    attempt = repository.create_attempt(run.app_run_id, task_id="task-migration")
    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("PRAGMA legacy_alter_table = ON")
        connection.execute(
            "UPDATE context_snapshots SET fingerprint = ? WHERE context_snapshot_id = ?",
            (_fingerprint(snapshot.payload), snapshot.context_snapshot_id),
        )
        connection.execute(
            """
            UPDATE app_schema_migrations
            SET checksum = ?
            WHERE migration_id = 'app-center-v1'
            """,
            ("sha256:4e52511c338b32266b38377cfb165bb0e9d527fa731cf5979ca9239bfe7fd9ca",),
        )
        connection.execute("ALTER TABLE context_snapshots RENAME TO context_snapshots_current")
        connection.execute(
            """
            CREATE TABLE context_snapshots (
              context_snapshot_id TEXT PRIMARY KEY,
              project_id TEXT NOT NULL REFERENCES content_projects(project_id),
              schema_version INTEGER NOT NULL DEFAULT 1
                CHECK (schema_version IN (1, 2)),
              payload_json TEXT NOT NULL,
              source_brand_id TEXT,
              source_brand_revision_id TEXT,
              fingerprint TEXT NOT NULL,
              created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("INSERT INTO context_snapshots SELECT * FROM context_snapshots_current")
        connection.execute("DROP TABLE context_snapshots_current")
        connection.commit()

    migrate_app_center(db_path)
    migrated = AppCenterRepository(db_path)
    assert migrated.get_context_snapshot(snapshot.context_snapshot_id).payload == _v2_payload()
    assert migrated.get_app_run(run.app_run_id).context_snapshot_id == snapshot.context_snapshot_id
    assert (
        migrated.get_attempt(attempt.attempt_id).context_snapshot_id == snapshot.context_snapshot_id
    )
    assets = AssetLibraryRepository(tmp_path / "migration-assets")
    restarted = AppCenterRepository(db_path, asset_repository=assets)
    resolved = ProjectContextResolver(restarted, assets).resolve_for_run(
        project.project_id, snapshot.context_snapshot_id
    )
    assert resolved.source_schema_version == 2
    with sqlite3.connect(db_path) as connection:
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE name = 'context_snapshots'"
        ).fetchone()[0]
        assert "schema_version IN (1, 2, 3)" in table_sql
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
