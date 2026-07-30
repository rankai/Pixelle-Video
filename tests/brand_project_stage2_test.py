from __future__ import annotations

import io
import sqlite3
import wave
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

import api.routers.app_center as app_center_api
from pixelle_video.app_center.brand_project import (
    BrandProjectService,
    ProjectContextResolver,
    default_project_brief,
)
from pixelle_video.app_center.migration import migrate_app_center
from pixelle_video.app_center.project_context import ProjectContextError
from pixelle_video.app_center.repository import (
    AppCenterRepository,
    IdempotencyConflict,
)
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository


def _repositories(tmp_path: Path) -> tuple[AppCenterRepository, AssetLibraryRepository]:
    assets = AssetLibraryRepository(tmp_path / "assets")
    app = AppCenterRepository(tmp_path / "app.sqlite", asset_repository=assets)
    return app, assets


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


def _image_bytes(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 20), color).save(output, format="PNG")
    return output.getvalue()


def _audio_bytes(frames: int) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16_000)
        audio.writeframes(b"\x00\x00" * frames)
    return output.getvalue()


def _upload(
    repository: AssetLibraryRepository,
    kind: str,
    payload: bytes,
    *,
    name: str,
) -> dict:
    suffix = "png" if kind == "image" else "wav"
    session = repository.create_upload_session(f"{name}.{suffix}", len(payload), kind)
    repository.append_upload_chunk(session["upload_id"], payload)
    return repository.finalize_upload(session["upload_id"])


def _append_revision(
    repository: AssetLibraryRepository,
    asset_id: str,
    kind: str,
    temporary: Path,
) -> dict:
    if kind == "image":
        temporary.write_bytes(_image_bytes("#ABCDEF"))
        filename = "new-revision.png"
    else:
        temporary.write_bytes(_audio_bytes(1_600))
        filename = "new-revision.wav"
    result = repository.create_revision_from_path(
        asset_id,
        filename,
        temporary,
        allow_duplicate=True,
    )
    assert result is not None
    return result


def _brand(
    assets: AssetLibraryRepository,
    *,
    brand_id: str,
    logo_id: str | None = None,
    bgm_id: str | None = None,
) -> dict:
    return assets.create_brand_kit(
        {
            "brand_id": brand_id,
            "brand_name": "同步前品牌",
            "logo_asset_id": logo_id,
            "default_bgm_asset_id": bgm_id,
            "primary_color": "#112233",
            "secondary_color": "#445566",
            "ending_card_text": "品牌结尾",
            "store_address": "旧地址",
            "phone": "021-00000000",
        }
    )


def _v2_payload() -> dict:
    return {
        "schema_version": 2,
        "subject_type": "store",
        "store_or_brand": {
            "name": "旧项目门店",
            "industry": "零售",
            "address": "项目地址",
            "contact": "项目电话",
        },
        "offer": {
            "name": "旧商品",
            "category": "零售",
            "price_facts": [],
            "promotion_facts": [],
        },
        "audience": {"primary": "附近顾客", "scenes": ["下班"]},
        "selling_points": [],
        "proof_points": [],
        "required_facts": [],
        "forbidden_claims": [],
        "asset_refs": [],
        "brand_revision_ref": "brand:brand-legacy-sync@1",
    }


def test_project_material_update_preserves_pinned_brand_and_supports_override_restore(
    tmp_path,
):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-material")
    service = BrandProjectService(app, assets)
    project, original = service.create_project(
        "夏日项目",
        "提升到店",
        brand_id="brand-material",
        expected_domain_revision=1,
    )
    assets.patch_brand_kit(
        "brand-material",
        {"brand_name": "资产库新名称", "store_address": "资产库新地址"},
    )
    brief = deepcopy(original.payload["project_brief"])
    brief["offer"]["name"] = "冰咖啡"
    overridden_project, overridden = service.update_project_material(
        project.project_id,
        expected_context_snapshot_id=original.context_snapshot_id,
        project_brief=brief,
        project_overrides={"store_address": "快闪店地址"},
    )
    assert overridden_project.brand_id == "brand-material"
    assert overridden.payload["brand_context"]["domain_revision"] == 1
    assert overridden.payload["brand_context"]["values"]["display_name"] == "同步前品牌"
    assert overridden.payload["brand_context"]["values"]["store_address"] == "快闪店地址"
    assert overridden.payload["brand_context"]["overridden_fields"] == ["store_address"]
    assert overridden.payload["project_brief"]["offer"]["name"] == "冰咖啡"

    _project, restored = service.update_project_material(
        project.project_id,
        expected_context_snapshot_id=overridden.context_snapshot_id,
        project_brief=brief,
        project_overrides={},
    )
    assert restored.payload["brand_context"]["domain_revision"] == 1
    assert restored.payload["brand_context"]["values"]["store_address"] == "旧地址"
    assert restored.payload["brand_context"]["overridden_fields"] == []


def test_project_material_update_conflict_and_unsupported_override_are_zero_write(tmp_path):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-material-conflict")
    service = BrandProjectService(app, assets)
    project, snapshot = service.create_project(
        "冲突项目",
        "获客",
        brand_id="brand-material-conflict",
        expected_domain_revision=1,
    )
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as conflict:
        service.update_project_material(
            project.project_id,
            expected_context_snapshot_id="stale-context",
            project_brief=snapshot.payload["project_brief"],
            project_overrides={},
        )
    assert conflict.value.code == "PROJECT_CONTEXT_CONFLICT"
    assert _database_rows(app.db_path) == before

    with pytest.raises(ProjectContextError) as untrusted:
        service.update_project_material(
            project.project_id,
            expected_context_snapshot_id=snapshot.context_snapshot_id,
            project_brief=snapshot.payload["project_brief"],
            project_overrides={"logo_ref": None},
        )
    assert untrusted.value.code == "PROJECT_BRAND_CONTEXT_UNTRUSTED"
    assert _database_rows(app.db_path) == before


def test_brand_sync_preview_is_read_only_and_reports_updates_and_preserved_overrides(
    tmp_path,
):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-preview")
    project, snapshot = BrandProjectService(app, assets).create_project(
        "预览项目",
        "到店",
        brand_id="brand-preview",
        expected_domain_revision=1,
        project_overrides={"ending_card_text": "仅本项目结尾"},
    )
    assets.patch_brand_kit(
        "brand-preview",
        {
            "brand_name": "同步后品牌",
            "ending_card_text": "品牌新结尾",
            "store_address": "新地址",
        },
    )
    before = (_database_rows(app.db_path), _database_rows(assets.db_path))
    preview = BrandProjectService(app, assets).preview_brand_sync(
        project.project_id,
        expected_context_snapshot_id=snapshot.context_snapshot_id,
    )
    assert preview["status"] == "changes_available"
    assert preview["has_changes"] is True
    changes = {item["field"]: item["status"] for item in preview["changes"]}
    assert changes["display_name"] == "updated"
    assert changes["store_address"] == "updated"
    assert changes["ending_card_text"] == "preserved_project_override"
    assert (_database_rows(app.db_path), _database_rows(assets.db_path)) == before


def test_brand_sync_appends_v3_preserves_project_material_and_historical_objects(tmp_path):
    app, assets = _repositories(tmp_path)
    old_logo = _upload(assets, "image", _image_bytes("#112233"), name="old-logo")
    old_bgm = _upload(assets, "audio", _audio_bytes(800), name="old-bgm")
    new_logo = _upload(assets, "image", _image_bytes("#445566"), name="new-logo")
    new_bgm = _upload(assets, "audio", _audio_bytes(1_200), name="new-bgm")
    _brand(
        assets,
        brand_id="brand-sync",
        logo_id=old_logo["asset_id"],
        bgm_id=old_bgm["asset_id"],
    )
    brief = default_project_brief("套餐", "促进到店")
    brief["selling_points"] = [{"fact_id": "sell-1", "text": "项目卖点", "source": "user"}]
    project, old_snapshot = BrandProjectService(app, assets).create_project(
        "同步项目",
        "促进到店",
        brand_id="brand-sync",
        expected_domain_revision=1,
        project_overrides={"ending_card_text": "活动专用结尾"},
        project_brief=brief,
    )
    old_run = app.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "历史运行"},
        idempotency_key="stage2-historical-run",
        context_snapshot_id=old_snapshot.context_snapshot_id,
    )
    old_artifact = app.create_artifact(
        project.project_id,
        "brief",
        "历史产物",
        source_app_run_id=old_run.app_run_id,
    )
    old_version = app.append_artifact_version(
        old_artifact.artifact_id,
        content={"text": "历史结果"},
    )
    frozen = {
        "snapshot": deepcopy(old_snapshot.__dict__),
        "run": deepcopy(old_run.__dict__),
        "artifact": deepcopy(app.get_artifact(old_artifact.artifact_id).__dict__),
        "version": deepcopy(old_version.__dict__),
    }
    assets.patch_brand_kit(
        "brand-sync",
        {
            "brand_name": "同步后品牌",
            "logo_asset_id": new_logo["asset_id"],
            "default_bgm_asset_id": new_bgm["asset_id"],
            "ending_card_text": "品牌同步后结尾",
            "primary_color": "#AABBCC",
        },
    )

    result = BrandProjectService(app, assets).sync_brand(
        project.project_id,
        expected_context_snapshot_id=old_snapshot.context_snapshot_id,
        idempotency_key="stage2-sync-apply",
    )
    assert result["result_code"] == "PROJECT_BRAND_SYNC_APPLIED"
    assert result["changes_committed"] is True
    current = app.get_context_snapshot(result["context_snapshot_id"])
    assert current.schema_version == 3
    assert current.payload["project_brief"] == brief
    brand_context = current.payload["brand_context"]
    assert brand_context["domain_revision"] == 2
    assert brand_context["values"]["display_name"] == "同步后品牌"
    assert brand_context["values"]["ending_card_text"] == "活动专用结尾"
    assert brand_context["overridden_fields"] == ["ending_card_text"]
    assert brand_context["values"]["logo_ref"]["asset_id"] == new_logo["asset_id"]
    assert brand_context["values"]["default_bgm_ref"]["asset_id"] == new_bgm["asset_id"]
    assert app.get_context_snapshot(old_snapshot.context_snapshot_id).__dict__ == frozen["snapshot"]
    assert app.get_app_run(old_run.app_run_id).__dict__ == frozen["run"]
    assert app.get_artifact(old_artifact.artifact_id).__dict__ == frozen["artifact"]
    assert app.get_artifact_version(old_version.artifact_version_id).__dict__ == frozen["version"]


def test_brand_sync_no_change_is_persistent_idempotent_and_does_not_append_snapshot(tmp_path):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-no-change")
    project, snapshot = BrandProjectService(app, assets).create_project(
        "无变化项目",
        "保持",
        brand_id="brand-no-change",
        expected_domain_revision=1,
    )
    service = BrandProjectService(app, assets)
    before_project = app.get_project(project.project_id)
    before_snapshot_rows = len(_database_rows(app.db_path)["context_snapshots"])
    first = service.sync_brand(
        project.project_id,
        expected_context_snapshot_id=snapshot.context_snapshot_id,
        idempotency_key="stage2-no-change",
    )
    restarted = BrandProjectService(
        AppCenterRepository(app.db_path, asset_repository=assets),
        assets,
    )
    second = restarted.sync_brand(
        project.project_id,
        expected_context_snapshot_id=snapshot.context_snapshot_id,
        idempotency_key="stage2-no-change",
    )
    assert first == second
    assert first["result_code"] == "PROJECT_BRAND_SYNC_NO_CHANGE"
    assert first["changes_committed"] is False
    assert len(_database_rows(app.db_path)["context_snapshots"]) == before_snapshot_rows
    assert app.get_project(project.project_id) == before_project
    with pytest.raises(IdempotencyConflict):
        service.sync_brand(
            project.project_id,
            expected_context_snapshot_id=None,
            idempotency_key="stage2-no-change",
        )


@pytest.mark.parametrize("schema_version", [1, 2])
def test_brand_sync_explicitly_upgrades_v1_v2_without_mutating_legacy_snapshot(
    tmp_path, schema_version
):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-legacy-sync")
    project = app.create_project(
        f"v{schema_version} 旧项目",
        "兼容同步",
        brand_id="brand-legacy-sync",
    )
    if schema_version == 1:
        payload = {
            "store_name": "旧项目门店",
            "industry": "零售",
            "offer_name": "旧商品",
            "target_audience": "附近顾客",
            "selling_points": ["旧项目卖点"],
        }
    else:
        payload = _v2_payload()
    legacy = app.save_context_snapshot(
        project.project_id,
        payload,
        schema_version=schema_version,
        source_brand_id="brand-legacy-sync",
        source_brand_revision_id="1",
    )
    frozen = deepcopy(legacy.__dict__)
    assets.patch_brand_kit(
        "brand-legacy-sync",
        {"primary_color": "#AABBCC"},
    )
    result = BrandProjectService(app, assets).sync_brand(
        project.project_id,
        expected_context_snapshot_id=legacy.context_snapshot_id,
        idempotency_key=f"stage2-legacy-v{schema_version}",
    )
    synced = app.get_context_snapshot(result["context_snapshot_id"])
    assert synced.schema_version == 3
    assert synced.payload["project_brief"]["offer"]["name"] == "旧商品"
    assert synced.payload["brand_context"]["values"]["primary_color"] == "#AABBCC"
    assert app.get_context_snapshot(legacy.context_snapshot_id).__dict__ == frozen


def test_sync_conflict_archived_missing_revision_and_unbound_project_fail_closed(tmp_path):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-fail")
    project, snapshot = BrandProjectService(app, assets).create_project(
        "失败关闭",
        "保护历史",
        brand_id="brand-fail",
        expected_domain_revision=1,
    )
    service = BrandProjectService(app, assets)
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as conflict:
        service.sync_brand(
            project.project_id,
            expected_context_snapshot_id="stale-snapshot",
            idempotency_key="stage2-stale",
        )
    assert conflict.value.code == "PROJECT_CONTEXT_CONFLICT"
    assert _database_rows(app.db_path) == before

    assets.patch_brand_kit("brand-fail", {"status": "archived"})
    with pytest.raises(ProjectContextError) as archived:
        service.sync_brand(
            project.project_id,
            expected_context_snapshot_id=snapshot.context_snapshot_id,
            idempotency_key="stage2-archived",
        )
    assert archived.value.code == "PROJECT_BRAND_NOT_AVAILABLE"
    assert _database_rows(app.db_path) == before
    assert (
        ProjectContextResolver(app, assets)
        .resolve_for_run(project.project_id, snapshot.context_snapshot_id)
        .brand_summary["display_name"]
        == "同步前品牌"
    )

    assets.patch_brand_kit("brand-fail", {"status": "ready"})
    with sqlite3.connect(assets.db_path) as connection:
        connection.execute(
            "DELETE FROM domain_revisions WHERE resource_kind = 'brand' AND resource_id = ?",
            ("brand-fail",),
        )
    with pytest.raises(ProjectContextError) as missing:
        service.sync_brand(
            project.project_id,
            expected_context_snapshot_id=snapshot.context_snapshot_id,
            idempotency_key="stage2-missing",
        )
    assert missing.value.code == "PROJECT_BRAND_REVISION_NOT_FOUND"
    assert _database_rows(app.db_path) == before

    unbound = app.create_project("旧项目", "中性结果")
    unbound_before = _database_rows(app.db_path)
    assert service.preview_brand_sync(unbound.project_id)["status"] == "unbound"
    with pytest.raises(ProjectContextError) as not_bound:
        service.sync_brand(
            unbound.project_id,
            expected_context_snapshot_id=None,
            idempotency_key="stage2-unbound",
        )
    assert not_bound.value.code == "PROJECT_BRAND_NOT_BOUND"
    assert not_bound.value.message == "这个项目尚未关联品牌，请先选择品牌包"
    assert _database_rows(app.db_path) == unbound_before


def test_preview_api_reports_archived_and_missing_brand_revision_without_hiding_history(
    monkeypatch, tmp_path
):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-preview-errors")
    project, snapshot = BrandProjectService(app, assets).create_project(
        "错误态摘要",
        "保留历史品牌资料",
        brand_id="brand-preview-errors",
        expected_domain_revision=1,
    )
    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app)
    monkeypatch.setattr(app_center_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", True)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    client = TestClient(api)
    before = _database_rows(app.db_path)

    assets.patch_brand_kit("brand-preview-errors", {"status": "archived"})
    archived = client.get(
        f"/api/content-projects/{project.project_id}/brand-sync-preview",
        params={"expected_context_snapshot_id": snapshot.context_snapshot_id},
    )
    assert archived.status_code == 409
    assert archived.json()["detail"] == {
        "code": "PROJECT_BRAND_NOT_AVAILABLE",
        "message": "这个品牌当前不可用于新项目",
    }
    historical = client.get(f"/api/content-projects/{project.project_id}/context-snapshots")
    assert historical.status_code == 200
    assert historical.json()["payload"]["brand_context"]["values"]["display_name"] == "同步前品牌"
    assert _database_rows(app.db_path) == before

    assets.patch_brand_kit("brand-preview-errors", {"status": "ready"})
    with sqlite3.connect(assets.db_path) as connection:
        connection.execute(
            "DELETE FROM domain_revisions WHERE resource_kind = 'brand' AND resource_id = ?",
            ("brand-preview-errors",),
        )
    missing = client.get(
        f"/api/content-projects/{project.project_id}/brand-sync-preview",
        params={"expected_context_snapshot_id": snapshot.context_snapshot_id},
    )
    assert missing.status_code == 409
    assert missing.json()["detail"] == {
        "code": "PROJECT_BRAND_REVISION_NOT_FOUND",
        "message": "品牌历史版本无法读取，请保留当前项目资料并联系支持",
    }
    assert _database_rows(app.db_path) == before


def test_sync_revalidates_concurrent_brand_update_before_appdb_commit(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-sync-race")
    project, snapshot = BrandProjectService(app, assets).create_project(
        "同步竞态",
        "保护快照",
        brand_id="brand-sync-race",
        expected_domain_revision=1,
    )
    assets.patch_brand_kit("brand-sync-race", {"brand_name": "第一次更新"})
    original_guard = assets.guard_domain_revision

    @contextmanager
    def update_before_guard(*args, **kwargs):
        assets.patch_brand_kit("brand-sync-race", {"brand_name": "并发第二次更新"})
        with original_guard(*args, **kwargs):
            yield

    monkeypatch.setattr(assets, "guard_domain_revision", update_before_guard)
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).sync_brand(
            project.project_id,
            expected_context_snapshot_id=snapshot.context_snapshot_id,
            idempotency_key="stage2-race",
        )
    assert exc.value.code == "PROJECT_CONTEXT_CONFLICT"
    assert _database_rows(app.db_path) == before


@pytest.mark.parametrize(
    ("field", "kind", "mutation", "expected_code"),
    [
        ("logo_ref", "image", "archive", "PROJECT_BRAND_ASSET_REVISION_MISSING"),
        ("logo_ref", "image", "new_revision", "PROJECT_CONTEXT_CONFLICT"),
        ("default_bgm_ref", "audio", "archive", "PROJECT_BRAND_ASSET_REVISION_MISSING"),
        ("default_bgm_ref", "audio", "new_revision", "PROJECT_CONTEXT_CONFLICT"),
    ],
)
def test_sync_media_guard_rejects_concurrent_archive_or_new_revision_without_appdb_writes(
    monkeypatch,
    tmp_path,
    field,
    kind,
    mutation,
    expected_code,
):
    app, assets = _repositories(tmp_path)
    logo = _upload(assets, "image", _image_bytes("#123456"), name="guard-logo")
    bgm = _upload(assets, "audio", _audio_bytes(800), name="guard-bgm")
    _brand(
        assets,
        brand_id="brand-media-guard",
        logo_id=logo["asset_id"],
        bgm_id=bgm["asset_id"],
    )
    project, snapshot = BrandProjectService(app, assets).create_project(
        "媒体竞态",
        "保护项目库",
        brand_id="brand-media-guard",
        expected_domain_revision=1,
    )
    assets.patch_brand_kit("brand-media-guard", {"brand_name": "等待同步"})
    target = logo if field == "logo_ref" else bgm
    original_guard = assets.guard_domain_revision

    @contextmanager
    def mutate_before_guard(*args, **kwargs):
        if mutation == "archive":
            assert assets.archive_asset(target["asset_id"]) is True
        else:
            _append_revision(
                assets,
                target["asset_id"],
                kind,
                tmp_path / f"{field}-{mutation}.{'png' if kind == 'image' else 'wav'}",
            )
        with original_guard(*args, **kwargs):
            yield

    monkeypatch.setattr(assets, "guard_domain_revision", mutate_before_guard)
    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).sync_brand(
            project.project_id,
            expected_context_snapshot_id=snapshot.context_snapshot_id,
            idempotency_key=f"stage2-{field}-{mutation}",
        )
    assert exc.value.code == expected_code
    assert _database_rows(app.db_path) == before


@pytest.mark.parametrize(
    ("field", "kind"),
    [
        ("logo_ref", "image"),
        ("default_bgm_ref", "audio"),
    ],
)
def test_sync_preserves_archived_historical_media_override_exact_revision(
    tmp_path,
    field,
    kind,
):
    app, assets = _repositories(tmp_path)
    override_asset = _upload(
        assets,
        kind,
        _image_bytes("#654321") if kind == "image" else _audio_bytes(1_000),
        name=f"override-{kind}",
    )
    _brand(assets, brand_id=f"brand-override-{kind}")
    override_ref = {
        "asset_id": override_asset["asset_id"],
        "asset_revision": assets.get_asset(override_asset["asset_id"])["current_revision_id"],
    }
    project, snapshot = BrandProjectService(app, assets).create_project(
        f"{kind} 覆盖项目",
        "保留历史覆盖",
        brand_id=f"brand-override-{kind}",
        expected_domain_revision=1,
        project_overrides={field: override_ref},
    )
    assert assets.archive_asset(override_asset["asset_id"]) is True
    assets.patch_brand_kit(
        f"brand-override-{kind}",
        {"brand_name": f"{kind} 同步后品牌"},
    )

    result = BrandProjectService(app, assets).sync_brand(
        project.project_id,
        expected_context_snapshot_id=snapshot.context_snapshot_id,
        idempotency_key=f"stage2-archived-override-{kind}",
    )
    synced = app.get_context_snapshot(result["context_snapshot_id"])
    assert synced.payload["brand_context"]["values"][field] == override_ref
    assert field in synced.payload["brand_context"]["overridden_fields"]


def test_new_media_override_must_be_current_ready_revision(tmp_path):
    app, assets = _repositories(tmp_path)
    logo = _upload(assets, "image", _image_bytes("#111111"), name="override-current")
    old_revision = assets.get_asset(logo["asset_id"])["current_revision_id"]
    _append_revision(
        assets,
        logo["asset_id"],
        "image",
        tmp_path / "override-current-v2.png",
    )
    _brand(assets, brand_id="brand-new-override")

    before = _database_rows(app.db_path)
    with pytest.raises(ProjectContextError) as exc:
        BrandProjectService(app, assets).create_project(
            "旧 revision 覆盖",
            "必须使用当前素材",
            brand_id="brand-new-override",
            expected_domain_revision=1,
            project_overrides={
                "logo_ref": {
                    "asset_id": logo["asset_id"],
                    "asset_revision": old_revision,
                }
            },
        )
    assert exc.value.code == "PROJECT_BRAND_ASSET_REVISION_MISSING"
    assert _database_rows(app.db_path) == before


def test_flag_off_blocks_preview_and_sync_but_keeps_v3_projection_readable(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-flag")
    project, snapshot = BrandProjectService(app, assets).create_project(
        "回滚项目",
        "可重启",
        brand_id="brand-flag",
        expected_domain_revision=1,
    )
    assets.patch_brand_kit("brand-flag", {"brand_name": "待同步品牌"})
    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app)
    monkeypatch.setattr(app_center_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", False)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    client = TestClient(api)
    before = (_database_rows(app.db_path), _database_rows(assets.db_path))
    read = client.get(f"/api/content-projects/{project.project_id}/context-snapshots")
    assert read.status_code == 200
    assert read.json()["projection_kind"] == "context_snapshot_v2"
    preview = client.get(
        f"/api/content-projects/{project.project_id}/brand-sync-preview",
        params={"expected_context_snapshot_id": snapshot.context_snapshot_id},
    )
    sync = client.post(
        f"/api/content-projects/{project.project_id}/brand-sync",
        json={
            "expected_context_snapshot_id": snapshot.context_snapshot_id,
            "idempotency_key": "stage2-flag-off",
        },
    )
    assert preview.status_code == 404
    assert sync.status_code == 404
    expected_disabled = {
        "detail": {
            "code": "BRAND_PROJECT_BOUNDARY_DISABLED",
            "message": "品牌项目功能当前未启用",
        }
    }
    assert preview.json() == expected_disabled
    assert sync.json() == expected_disabled
    assert (_database_rows(app.db_path), _database_rows(assets.db_path)) == before

    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", True)
    applied = client.post(
        f"/api/content-projects/{project.project_id}/brand-sync",
        json={
            "expected_context_snapshot_id": snapshot.context_snapshot_id,
            "idempotency_key": "stage2-flag-on",
        },
    )
    assert applied.status_code == 200
    restarted = AppCenterRepository(app.db_path, asset_repository=assets)
    resolved = ProjectContextResolver(restarted, assets).resolve_for_run(project.project_id)
    assert resolved.brand_summary["display_name"] == "待同步品牌"


def test_brand_sync_api_preview_apply_no_change_and_conflict_contract(monkeypatch, tmp_path):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-sync-api")
    project, snapshot = BrandProjectService(app, assets).create_project(
        "同步 API",
        "稳定契约",
        brand_id="brand-sync-api",
        expected_domain_revision=1,
    )
    assets.patch_brand_kit("brand-sync-api", {"brand_name": "API 新品牌"})
    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app)
    monkeypatch.setattr(app_center_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", True)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    client = TestClient(api)

    before_preview = (_database_rows(app.db_path), _database_rows(assets.db_path))
    preview = client.get(
        f"/api/content-projects/{project.project_id}/brand-sync-preview",
        params={"expected_context_snapshot_id": snapshot.context_snapshot_id},
    )
    assert preview.status_code == 200
    assert preview.json()["status"] == "changes_available"
    assert (_database_rows(app.db_path), _database_rows(assets.db_path)) == before_preview

    applied = client.post(
        f"/api/content-projects/{project.project_id}/brand-sync",
        json={
            "expected_context_snapshot_id": snapshot.context_snapshot_id,
            "idempotency_key": "stage2-api-apply",
        },
    )
    assert applied.status_code == 200
    assert applied.json()["result_code"] == "PROJECT_BRAND_SYNC_APPLIED"
    repeated = client.post(
        f"/api/content-projects/{project.project_id}/brand-sync",
        json={
            "expected_context_snapshot_id": snapshot.context_snapshot_id,
            "idempotency_key": "stage2-api-apply",
        },
    )
    assert repeated.json() == applied.json()
    current_snapshot_id = applied.json()["context_snapshot_id"]
    no_change = client.post(
        f"/api/content-projects/{project.project_id}/brand-sync",
        json={
            "expected_context_snapshot_id": current_snapshot_id,
            "idempotency_key": "stage2-api-no-change",
        },
    )
    assert no_change.status_code == 200
    assert no_change.json()["result_code"] == "PROJECT_BRAND_SYNC_NO_CHANGE"
    assert no_change.json()["changes_committed"] is False
    stale = client.post(
        f"/api/content-projects/{project.project_id}/brand-sync",
        json={
            "expected_context_snapshot_id": snapshot.context_snapshot_id,
            "idempotency_key": "stage2-api-stale",
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"] == {
        "code": "PROJECT_CONTEXT_CONFLICT",
        "message": "项目信息已在其他位置更新，请刷新后重试",
    }
    unbound = app.create_project("未绑定 API 项目", "准确错误")
    unbound_sync = client.post(
        f"/api/content-projects/{unbound.project_id}/brand-sync",
        json={
            "expected_context_snapshot_id": None,
            "idempotency_key": "stage2-api-unbound",
        },
    )
    assert unbound_sync.status_code == 409
    assert unbound_sync.json()["detail"] == {
        "code": "PROJECT_BRAND_NOT_BOUND",
        "message": "这个项目尚未关联品牌，请先选择品牌包",
    }


def test_stage3_project_material_api_and_unbound_create_are_explicit_v3(
    monkeypatch,
    tmp_path,
):
    app, assets = _repositories(tmp_path)
    _brand(assets, brand_id="brand-stage3-api")
    monkeypatch.setattr(app_center_api, "get_app_center_repository", lambda: app)
    monkeypatch.setattr(app_center_api, "get_asset_repository", lambda: assets)
    monkeypatch.setattr(app_center_api.api_config, "brand_project_boundary_v1_enabled", True)
    api = FastAPI()
    api.include_router(app_center_api.router, prefix="/api")
    client = TestClient(api)

    unbound = client.post(
        "/api/content-projects",
        json={"name": "无品牌活动", "primary_goal": "市场验证"},
    )
    assert unbound.status_code == 201
    assert unbound.json()["brand_id"] is None
    unbound_snapshot = client.get(
        f"/api/content-projects/{unbound.json()['project_id']}/context-snapshots"
    )
    assert unbound_snapshot.status_code == 200
    assert unbound_snapshot.json()["schema_version"] == 3
    assert unbound_snapshot.json()["payload"]["brand_context"] is None

    summary = assets.domain_snapshot_metadata("brand", "brand-stage3-api")
    branded = client.post(
        "/api/content-projects",
        json={
            "name": "品牌活动",
            "primary_goal": "提升到店",
            "brand_id": "brand-stage3-api",
            "expected_brand_domain_revision": summary["domain_revision"],
        },
    )
    assert branded.status_code == 201
    current = client.get(
        f"/api/content-projects/{branded.json()['project_id']}/context-snapshots"
    ).json()
    brief = deepcopy(current["payload"]["project_brief"])
    brief["offer"]["name"] = "新品冰咖啡"
    updated = client.post(
        f"/api/content-projects/{branded.json()['project_id']}/project-material",
        json={
            "expected_context_snapshot_id": current["context_snapshot_id"],
            "project_brief": brief,
            "project_overrides": {"ending_card_text": "仅本活动使用"},
        },
    )
    assert updated.status_code == 200
    assert updated.json()["payload"]["project_brief"]["offer"]["name"] == "新品冰咖啡"
    assert updated.json()["payload"]["brand_context"]["values"]["ending_card_text"] == (
        "仅本活动使用"
    )
    assert updated.json()["payload"]["brand_context"]["overridden_fields"] == ["ending_card_text"]

    before_stale = _database_rows(app.db_path)
    stale = client.post(
        f"/api/content-projects/{branded.json()['project_id']}/project-material",
        json={
            "expected_context_snapshot_id": current["context_snapshot_id"],
            "project_brief": brief,
            "project_overrides": {},
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "PROJECT_CONTEXT_CONFLICT"
    assert _database_rows(app.db_path) == before_stale


def test_stage2_migration_adds_idempotency_table_and_preserves_existing_rows(tmp_path):
    db_path = tmp_path / "stage2-migration.sqlite"
    repository = AppCenterRepository(db_path)
    project = repository.create_project("迁移前项目", "保留")
    run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "迁移保留"},
        idempotency_key="stage2-migration-run",
    )
    artifact = repository.create_artifact(
        project.project_id,
        "brief",
        "迁移前产物",
        source_app_run_id=run.app_run_id,
    )
    version = repository.append_artifact_version(
        artifact.artifact_id,
        content={"text": "迁移前结果"},
    )
    with sqlite3.connect(db_path) as connection:
        connection.execute("DROP TABLE brand_sync_requests")
        connection.execute(
            """
            UPDATE app_schema_migrations SET checksum = ?
            WHERE migration_id = 'app-center-v1'
            """,
            ("sha256:2742365a5f3b4599563f263753c2695d084968fde6873ed992b1634ba9be9004",),
        )
    migrate_app_center(db_path)
    restarted = AppCenterRepository(db_path)
    assert restarted.get_project(project.project_id).name == "迁移前项目"
    assert restarted.get_app_run(run.app_run_id).__dict__ == run.__dict__
    assert restarted.get_artifact_version(version.artifact_version_id).__dict__ == version.__dict__
    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        assert "brand_sync_requests" in tables
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
