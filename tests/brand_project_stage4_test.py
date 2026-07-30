from __future__ import annotations

import asyncio
import io
import sqlite3
import wave
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from api.app import app
from pixelle_video.app_center.brand_project import (
    BrandProjectService,
    ProjectContextResolver,
)
from pixelle_video.app_center.carousel import (
    CAROUSEL_HEIGHT,
    CAROUSEL_WIDTH,
    DouyinCarouselExecutor,
    DouyinCarouselRenderer,
)
from pixelle_video.app_center.ip_broadcast_adapter import (
    IpBroadcastAppAdapter,
    IpBroadcastBindingStore,
)
from pixelle_video.app_center.llm_port import FakeLLMPort
from pixelle_video.app_center.project_context import ProjectContextError
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.structured_apps import StructuredLLMExecutor
from pixelle_video.services.assets_v2.repository import AssetLibraryRepository
from pixelle_video.services.ip_broadcast_workflow import IpBroadcastSessionStore


def _image_bytes(color: str) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (24, 24), color).save(output, format="PNG")
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


def _copy_output() -> dict:
    variants = []
    for index, angle in enumerate(("利益", "好奇", "场景"), start=1):
        hook = f"活动入口{index}"
        body = "项目固定事实文案"
        cta = "到店了解"
        full_text = hook + body + cta
        variants.append(
            {
                "version_name": f"版本{index}",
                "angle": angle,
                "hook": hook,
                "body": body,
                "cta": cta,
                "full_text": full_text,
                "word_count": len(full_text),
                "estimated_seconds": max(1, (len(full_text) + 3) // 4),
            }
        )
    return {"variants": variants, "missing_facts": [], "risk_flags": []}


def _title_output() -> dict:
    return {
        "candidates": [
            {
                "title": f"项目标题第{index}种",
                "angle": "场景",
                "objective": "click",
                "length": len(f"项目标题第{index}种"),
                "banned_matches": [],
                "risk_labels": ["无"],
            }
            for index in range(1, 6)
        ],
        "missing_facts": [],
        "risk_flags": [],
    }


def _stage4_project(tmp_path: Path):
    assets = AssetLibraryRepository(tmp_path / "assets")
    repository = AppCenterRepository(tmp_path / "app-center.sqlite", asset_repository=assets)
    old_logo = _upload(assets, "image", _image_bytes("#AA00AA"), name="old-logo")
    old_bgm = _upload(assets, "audio", _audio_bytes(800), name="old-bgm")
    new_logo = _upload(assets, "image", _image_bytes("#00AA66"), name="new-logo")
    new_bgm = _upload(assets, "audio", _audio_bytes(1_600), name="new-bgm")
    content_image = _upload(assets, "image", _image_bytes("#D6984A"), name="content-image")
    assets.create_brand_kit(
        {
            "brand_id": "brand-stage4",
            "brand_name": "同步前品牌",
            "logo_asset_id": old_logo["asset_id"],
            "default_bgm_asset_id": old_bgm["asset_id"],
            "primary_color": "#112233",
            "secondary_color": "#445566",
            "font_family": "noto-sans-sc-bold",
            "default_subtitle_style": "readable_v2",
            "ending_card_text": "同步前结尾",
            "store_address": "企业旧地址",
            "phone": "021-00000000",
            "coupon_phrase": "到店礼",
        }
    )
    project, old_snapshot = BrandProjectService(repository, assets).create_project(
        "Stage4 项目",
        "到店",
        brand_id="brand-stage4",
        expected_domain_revision=1,
        project_overrides={
            "phone": "仅本项目电话",
            "ending_card_text": "仅本项目结尾",
        },
    )
    return (
        repository,
        assets,
        project,
        old_snapshot,
        old_logo,
        old_bgm,
        new_logo,
        new_bgm,
        content_image,
    )


def _server_create_run(
    repository: AppCenterRepository,
    resolver: ProjectContextResolver,
    *,
    project_id: str,
    app_id: str,
    app_version: str,
    payload: dict,
    idempotency_key: str,
    expected_context_snapshot_id: str | None = None,
):
    snapshot_id = repository.resolve_run_context_snapshot(
        project_id,
        payload,
        expected_context_snapshot_id=expected_context_snapshot_id,
    )
    resolver.resolve_for_run(project_id, snapshot_id)
    return repository.create_app_run(
        project_id,
        app_id,
        app_version,
        repository.canonicalize_run_input(
            payload,
            project_id=project_id,
            app_id=app_id,
            context_snapshot_id=snapshot_id,
        ),
        idempotency_key=idempotency_key,
        context_snapshot_id=snapshot_id,
    )


def _handoff_context_matrix(tmp_path: Path):
    repository = AppCenterRepository(tmp_path / "handoff-context.sqlite")
    project = repository.create_project("Handoff 项目", "上下文隔离")
    old_snapshot = repository.save_context_snapshot(
        project.project_id,
        {"store_name": "旧项目资料"},
    )
    old_run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "旧运行"},
        idempotency_key="handoff-old-run",
    )
    old_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "旧来源",
        source_app_run_id=old_run.app_run_id,
    )
    old_version = repository.append_artifact_version(
        old_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            **_copy_output(),
        },
    )
    legacy_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "无快照旧来源",
    )
    legacy_version = repository.append_artifact_version(
        legacy_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            **_copy_output(),
        },
    )
    new_snapshot = repository.save_context_snapshot(
        project.project_id,
        {"store_name": "新项目资料"},
    )
    new_target_run = repository.create_app_run(
        project.project_id,
        "builtin.viral-titles",
        "1.0.0",
        {"goal": "新目标运行"},
        idempotency_key="handoff-new-target-run",
    )
    new_source_run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "新来源运行"},
        idempotency_key="handoff-new-source-run",
    )
    new_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "新来源",
        source_app_run_id=new_source_run.app_run_id,
    )
    new_version = repository.append_artifact_version(
        new_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            **_copy_output(),
        },
    )
    other_project = repository.create_project("其他项目", "跨项目负例")
    repository.save_context_snapshot(
        other_project.project_id,
        {"store_name": "其他项目资料"},
    )
    other_run = repository.create_app_run(
        other_project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "跨项目来源"},
        idempotency_key="handoff-other-run",
    )
    other_artifact = repository.create_artifact(
        other_project.project_id,
        "copywriting",
        "跨项目来源",
        source_app_run_id=other_run.app_run_id,
    )
    other_version = repository.append_artifact_version(
        other_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            **_copy_output(),
        },
    )
    return {
        "repository": repository,
        "project": project,
        "old_snapshot": old_snapshot,
        "new_snapshot": new_snapshot,
        "old_run": old_run,
        "old_artifact": old_artifact,
        "old_version": old_version,
        "legacy_artifact": legacy_artifact,
        "legacy_version": legacy_version,
        "new_target_run": new_target_run,
        "new_version": new_version,
        "other_artifact": other_artifact,
        "other_version": other_version,
    }


def test_four_app_context_views_include_only_applicable_brand_fields(tmp_path):
    repository, assets, project, snapshot, *_ = _stage4_project(tmp_path)
    resolver = ProjectContextResolver(repository, assets)
    expected_fields = {
        "builtin.marketing-copy": {
            "display_name",
            "store_address",
            "phone",
            "coupon_phrase",
            "ending_card_text",
        },
        "builtin.viral-titles": {"display_name"},
        "builtin.douyin-carousel": {
            "display_name",
            "primary_color",
            "secondary_color",
            "font_family",
            "logo_ref",
            "ending_card_text",
            "coupon_phrase",
        },
        "builtin.digital-human-video": {
            "display_name",
            "store_address",
            "phone",
            "primary_color",
            "secondary_color",
            "font_family",
            "default_subtitle_style",
            "logo_ref",
            "default_bgm_ref",
            "ending_card_text",
            "coupon_phrase",
        },
    }
    for app_id, fields in expected_fields.items():
        context = resolver.resolve_for_application(
            project.project_id,
            snapshot.context_snapshot_id,
            app_id=app_id,
        )
        assert set(context["brand"]["values"]) == fields
        assert context["lineage"]["context_snapshot_id"] == snapshot.context_snapshot_id
        assert set(context["brand"]["overridden_fields"]).issubset(fields)


def test_sync_dual_run_and_typed_handoff_keep_fixed_provenance(tmp_path):
    (
        repository,
        assets,
        project,
        old_snapshot,
        _old_logo,
        _old_bgm,
        new_logo,
        new_bgm,
        _content_image,
    ) = _stage4_project(tmp_path)
    resolver = ProjectContextResolver(repository, assets)
    marketing_input = {
        "goal": "同步前运行",
        "product_or_service": "项目商品",
        "content_format": "oral",
        "length_bucket": "short_15s",
    }
    old_run = _server_create_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.marketing-copy",
        app_version="1.0.0",
        payload=marketing_input,
        idempotency_key="stage4-old-run",
    )
    source_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "同步前文案",
        source_app_run_id=old_run.app_run_id,
    )
    old_version = repository.append_artifact_version(
        source_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            "validation_facts": {
                "input": marketing_input,
                "context": resolver.resolve_for_application(
                    project.project_id,
                    old_snapshot.context_snapshot_id,
                    app_id="builtin.marketing-copy",
                ),
            },
            **_copy_output(),
        },
    )
    old_frozen = {
        "snapshot": deepcopy(
            repository.get_context_snapshot(old_snapshot.context_snapshot_id).__dict__
        ),
        "run": deepcopy(repository.get_app_run(old_run.app_run_id).__dict__),
        "version": deepcopy(
            repository.get_artifact_version(old_version.artifact_version_id).__dict__
        ),
    }

    assets.patch_brand_kit(
        "brand-stage4",
        {
            "brand_name": "同步后品牌",
            "logo_asset_id": new_logo["asset_id"],
            "default_bgm_asset_id": new_bgm["asset_id"],
            "primary_color": "#AABBCC",
            "secondary_color": "#DDEEFF",
            "store_address": "企业新地址",
            "phone": "企业新电话",
            "ending_card_text": "企业新结尾",
        },
    )
    synced = BrandProjectService(repository, assets).sync_brand(
        project.project_id,
        expected_context_snapshot_id=old_snapshot.context_snapshot_id,
        idempotency_key="stage4-brand-sync",
    )
    new_snapshot = repository.get_context_snapshot(synced["context_snapshot_id"])
    new_brand = new_snapshot.payload["brand_context"]
    assert new_brand["values"]["display_name"] == "同步后品牌"
    assert new_brand["values"]["phone"] == "仅本项目电话"
    assert new_brand["values"]["ending_card_text"] == "仅本项目结尾"
    assert new_brand["overridden_fields"] == ["ending_card_text", "phone"]

    new_run = _server_create_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.marketing-copy",
        app_version="1.0.0",
        payload={**marketing_input, "goal": "同步后运行"},
        idempotency_key="stage4-new-run",
        expected_context_snapshot_id=new_snapshot.context_snapshot_id,
    )
    new_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "同步后文案",
        source_app_run_id=new_run.app_run_id,
    )
    new_version = repository.append_artifact_version(
        new_artifact.artifact_id,
        content={"text": "同步后结果"},
    )
    assert old_version.context_snapshot_id == old_snapshot.context_snapshot_id
    assert new_version.context_snapshot_id == new_snapshot.context_snapshot_id
    assert (
        repository.get_context_snapshot(old_snapshot.context_snapshot_id).__dict__
        == old_frozen["snapshot"]
    )
    assert repository.get_app_run(old_run.app_run_id).__dict__ == old_frozen["run"]
    assert (
        repository.get_artifact_version(old_version.artifact_version_id).__dict__
        == old_frozen["version"]
    )

    title_payload = {
        "platform": "douyin",
        "objective": "click",
        "count": 5,
        "source_artifact_version_id": old_version.artifact_version_id,
    }
    title_run = _server_create_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.viral-titles",
        app_version="1.0.0",
        payload=title_payload,
        idempotency_key="stage4-old-source-title-run",
        expected_context_snapshot_id=new_snapshot.context_snapshot_id,
    )
    assert title_run.context_snapshot_id == old_snapshot.context_snapshot_id
    handoff = repository.create_handoff(
        project.project_id,
        source_artifact.artifact_id,
        old_version.artifact_version_id,
        "builtin.viral-titles",
        "1.0.0",
        [old_version.artifact_version_id],
        source_app_run_id=old_run.app_run_id,
        target_run_id=title_run.app_run_id,
        mapping_version=2,
    )
    assert handoff.source_context_snapshot_id == old_snapshot.context_snapshot_id
    assert handoff.target_context_snapshot_id == old_snapshot.context_snapshot_id
    with pytest.raises(ProjectContextError) as mixed:
        repository.resolve_run_context_snapshot(
            project.project_id,
            {
                "source_artifact_version_ids": [
                    old_version.artifact_version_id,
                    new_version.artifact_version_id,
                ]
            },
            expected_context_snapshot_id=new_snapshot.context_snapshot_id,
        )
    assert mixed.value.code == "PROJECT_CONTEXT_HANDOFF_MIXED"


def test_repository_handoff_context_matrix_fails_closed_and_keeps_legacy_rows_read_only(
    tmp_path,
):
    fixture = _handoff_context_matrix(tmp_path)
    repository = fixture["repository"]

    def handoff_count() -> int:
        with sqlite3.connect(repository.db_path) as conn:
            return conn.execute("SELECT COUNT(*) FROM artifact_handoffs").fetchone()[0]

    cases = [
        (
            {
                "project_id": fixture["project"].project_id,
                "source_artifact_id": fixture["old_artifact"].artifact_id,
                "source_artifact_version_id": fixture["old_version"].artifact_version_id,
                "target_app_id": "builtin.viral-titles",
                "target_app_version": "1.0.0",
                "artifact_version_ids": [fixture["old_version"].artifact_version_id],
                "target_run_id": fixture["new_target_run"].app_run_id,
                "mapping_version": 2,
            },
            "PROJECT_CONTEXT_HANDOFF_MIXED",
        ),
        (
            {
                "project_id": fixture["project"].project_id,
                "source_artifact_id": fixture["legacy_artifact"].artifact_id,
                "source_artifact_version_id": fixture["legacy_version"].artifact_version_id,
                "target_app_id": "builtin.viral-titles",
                "target_app_version": "1.0.0",
                "artifact_version_ids": [fixture["legacy_version"].artifact_version_id],
                "target_run_id": fixture["new_target_run"].app_run_id,
                "mapping_version": 2,
            },
            "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED",
        ),
        (
            {
                "project_id": fixture["project"].project_id,
                "source_artifact_id": fixture["other_artifact"].artifact_id,
                "source_artifact_version_id": fixture["other_version"].artifact_version_id,
                "target_app_id": "builtin.viral-titles",
                "target_app_version": "1.0.0",
                "artifact_version_ids": [fixture["other_version"].artifact_version_id],
                "mapping_version": 2,
            },
            "PROJECT_CONTEXT_CROSS_PROJECT_REF",
        ),
        (
            {
                "project_id": fixture["project"].project_id,
                "source_artifact_id": fixture["old_artifact"].artifact_id,
                "source_artifact_version_id": fixture["old_version"].artifact_version_id,
                "target_app_id": "builtin.viral-titles",
                "target_app_version": "1.0.0",
                "artifact_version_ids": [
                    fixture["old_version"].artifact_version_id,
                    fixture["new_version"].artifact_version_id,
                ],
                "mapping_version": 2,
            },
            "PROJECT_CONTEXT_HANDOFF_MIXED",
        ),
    ]
    for request, expected_code in cases:
        before = handoff_count()
        with pytest.raises(ProjectContextError) as exc:
            repository.create_handoff(**request)
        assert exc.value.code == expected_code
        assert handoff_count() == before

    legacy_handoff_id = "handoff_legacy_read_only"
    with sqlite3.connect(repository.db_path) as conn:
        conn.execute(
            """
            INSERT INTO artifact_handoffs(
                handoff_id, project_id, source_app_run_id,
                source_context_snapshot_id, source_artifact_id,
                source_artifact_version_id, target_app_id,
                target_app_version, target_run_id,
                target_context_snapshot_id, artifact_version_ids_json,
                mapping_version, created_at
            ) VALUES (?, ?, NULL, NULL, ?, ?, ?, ?, NULL, NULL, ?, 1, ?)
            """,
            (
                legacy_handoff_id,
                fixture["project"].project_id,
                fixture["legacy_artifact"].artifact_id,
                fixture["legacy_version"].artifact_version_id,
                "builtin.viral-titles",
                "1.0.0",
                f'["{fixture["legacy_version"].artifact_version_id}"]',
                "2026-07-30T00:00:00.000Z",
            ),
        )
    before_row = repository.get_handoff(legacy_handoff_id).__dict__
    listed = {
        item.handoff_id: item.__dict__
        for item in repository.list_handoffs(fixture["legacy_artifact"].artifact_id)
    }
    assert listed[legacy_handoff_id] == before_row
    assert before_row["source_context_snapshot_id"] is None
    assert before_row["target_context_snapshot_id"] is None
    assert repository.get_handoff(legacy_handoff_id).__dict__ == before_row


def test_public_append_keeps_legacy_null_but_new_typed_consumers_require_mapping(
    tmp_path,
):
    repository = AppCenterRepository(tmp_path / "legacy-public-append.sqlite")
    project = repository.create_project("旧产物项目", "验证显式映射边界")
    legacy_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "公开 API 写入的旧产物",
    )
    legacy_version = repository.append_artifact_version(
        legacy_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            **_copy_output(),
        },
    )
    assert legacy_version.context_snapshot_id is None
    assert legacy_version.source_app_run_id is None

    current_snapshot = repository.save_context_snapshot(
        project.project_id,
        {"store_name": "当前项目资料"},
    )
    with sqlite3.connect(repository.db_path) as conn:
        run_count = conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0]
        handoff_count = conn.execute("SELECT COUNT(*) FROM artifact_handoffs").fetchone()[0]

    with pytest.raises(ProjectContextError) as run_error:
        repository.create_app_run(
            project.project_id,
            "builtin.viral-titles",
            "1.0.0",
            {
                "goal": "消费无 provenance 的 typed source",
                "source_artifact_version_ids": [legacy_version.artifact_version_id],
            },
            idempotency_key="legacy-null-typed-run",
            context_snapshot_id=current_snapshot.context_snapshot_id,
        )
    assert run_error.value.code == "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED"

    with pytest.raises(ProjectContextError) as handoff_error:
        repository.create_handoff(
            project.project_id,
            legacy_artifact.artifact_id,
            legacy_version.artifact_version_id,
            "builtin.viral-titles",
            "1.0.0",
            [legacy_version.artifact_version_id],
            mapping_version=2,
        )
    assert handoff_error.value.code == "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED"
    with sqlite3.connect(repository.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0] == run_count
        assert conn.execute("SELECT COUNT(*) FROM artifact_handoffs").fetchone()[0] == handoff_count


def test_handoff_public_api_returns_stable_context_codes_without_writes(monkeypatch, tmp_path):
    fixture = _handoff_context_matrix(tmp_path)
    repository = fixture["repository"]
    monkeypatch.setattr(
        "api.routers.app_center.get_app_center_repository",
        lambda: repository,
    )
    client = TestClient(app)

    cases = [
        (
            {
                "project_id": fixture["project"].project_id,
                "source_artifact_id": fixture["old_artifact"].artifact_id,
                "source_artifact_version_id": fixture["old_version"].artifact_version_id,
                "target_app_id": "builtin.viral-titles",
                "target_app_version": "1.0.0",
                "artifact_version_ids": [fixture["old_version"].artifact_version_id],
                "target_run_id": fixture["new_target_run"].app_run_id,
                "mapping_version": 2,
            },
            "PROJECT_CONTEXT_HANDOFF_MIXED",
        ),
        (
            {
                "project_id": fixture["project"].project_id,
                "source_artifact_id": fixture["legacy_artifact"].artifact_id,
                "source_artifact_version_id": fixture["legacy_version"].artifact_version_id,
                "target_app_id": "builtin.viral-titles",
                "target_app_version": "1.0.0",
                "artifact_version_ids": [fixture["legacy_version"].artifact_version_id],
                "target_run_id": fixture["new_target_run"].app_run_id,
                "mapping_version": 2,
            },
            "PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED",
        ),
        (
            {
                "project_id": fixture["project"].project_id,
                "source_artifact_id": fixture["other_artifact"].artifact_id,
                "source_artifact_version_id": fixture["other_version"].artifact_version_id,
                "target_app_id": "builtin.viral-titles",
                "target_app_version": "1.0.0",
                "artifact_version_ids": [fixture["other_version"].artifact_version_id],
                "mapping_version": 2,
            },
            "PROJECT_CONTEXT_CROSS_PROJECT_REF",
        ),
        (
            {
                "project_id": fixture["project"].project_id,
                "source_artifact_id": fixture["old_artifact"].artifact_id,
                "source_artifact_version_id": fixture["old_version"].artifact_version_id,
                "target_app_id": "builtin.viral-titles",
                "target_app_version": "1.0.0",
                "artifact_version_ids": [
                    fixture["old_version"].artifact_version_id,
                    fixture["new_version"].artifact_version_id,
                ],
                "mapping_version": 2,
            },
            "PROJECT_CONTEXT_HANDOFF_MIXED",
        ),
    ]
    for payload, expected_code in cases:
        with sqlite3.connect(repository.db_path) as conn:
            before = conn.execute("SELECT COUNT(*) FROM artifact_handoffs").fetchone()[0]
        response = client.post("/api/artifact-handoffs", json=payload)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == expected_code
        with sqlite3.connect(repository.db_path) as conn:
            after = conn.execute("SELECT COUNT(*) FROM artifact_handoffs").fetchone()[0]
        assert after == before


def test_create_app_run_repository_enforces_current_or_typed_source_context_and_replay(
    tmp_path,
):
    fixture = _handoff_context_matrix(tmp_path)
    repository = fixture["repository"]
    project = fixture["project"]

    replay = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "旧运行"},
        idempotency_key="handoff-old-run",
        context_snapshot_id=fixture["new_snapshot"].context_snapshot_id,
    )
    assert replay.app_run_id == fixture["old_run"].app_run_id
    assert replay.context_snapshot_id == fixture["old_snapshot"].context_snapshot_id

    with sqlite3.connect(repository.db_path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0]
    with pytest.raises(ProjectContextError) as stale:
        repository.create_app_run(
            project.project_id,
            "builtin.marketing-copy",
            "1.0.0",
            {"goal": "过期普通运行"},
            idempotency_key="stale-ordinary-context",
            context_snapshot_id=fixture["old_snapshot"].context_snapshot_id,
        )
    assert stale.value.code == "PROJECT_CONTEXT_CONFLICT"
    with sqlite3.connect(repository.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0] == before

    current_run = repository.create_app_run(
        project.project_id,
        "builtin.marketing-copy",
        "1.0.0",
        {"goal": "当前普通运行"},
        idempotency_key="current-ordinary-context",
    )
    assert current_run.context_snapshot_id == fixture["new_snapshot"].context_snapshot_id

    typed_old_run = repository.create_app_run(
        project.project_id,
        "builtin.viral-titles",
        "1.0.0",
        {
            "goal": "旧来源 typed run",
            "source_artifact_version_id": fixture["old_version"].artifact_version_id,
        },
        idempotency_key="typed-old-source-context",
        context_snapshot_id=fixture["new_snapshot"].context_snapshot_id,
    )
    assert typed_old_run.context_snapshot_id == fixture["old_snapshot"].context_snapshot_id


def test_create_app_run_public_api_enforces_repository_context_boundary(monkeypatch, tmp_path):
    fixture = _handoff_context_matrix(tmp_path)
    repository = fixture["repository"]
    project = fixture["project"]
    monkeypatch.setattr(
        "api.routers.app_center.get_app_center_repository",
        lambda: repository,
    )
    client = TestClient(app)

    with sqlite3.connect(repository.db_path) as conn:
        before = conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0]
    stale = client.post(
        "/api/app-runs",
        json={
            "project_id": project.project_id,
            "app_id": "builtin.marketing-copy",
            "app_version": "1.0.0",
            "input_payload": {"goal": "API 过期普通运行"},
            "idempotency_key": "api-stale-ordinary-context",
            "context_snapshot_id": fixture["old_snapshot"].context_snapshot_id,
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "PROJECT_CONTEXT_CONFLICT"
    with sqlite3.connect(repository.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM app_runs").fetchone()[0] == before

    typed_request = {
        "project_id": project.project_id,
        "app_id": "builtin.viral-titles",
        "app_version": "1.0.0",
        "input_payload": {
            "goal": "API 旧来源 typed run",
            "source_artifact_version_id": fixture["old_version"].artifact_version_id,
        },
        "idempotency_key": "api-typed-old-source-context",
        "context_snapshot_id": fixture["new_snapshot"].context_snapshot_id,
    }
    typed = client.post("/api/app-runs", json=typed_request)
    assert typed.status_code == 201
    assert typed.json()["context_snapshot_id"] == fixture["old_snapshot"].context_snapshot_id
    replay = client.post("/api/app-runs", json=typed_request)
    assert replay.status_code == 201
    assert replay.json()["app_run_id"] == typed.json()["app_run_id"]
    assert replay.json()["context_snapshot_id"] == fixture["old_snapshot"].context_snapshot_id


def test_text_prompts_use_resolved_fixed_application_context(tmp_path):
    repository, assets, project, snapshot, *_ = _stage4_project(tmp_path)
    resolver = ProjectContextResolver(repository, assets)
    marketing_run = _server_create_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.marketing-copy",
        app_version="1.0.0",
        payload={
            "goal": "吸引到店",
            "product_or_service": "项目商品",
            "content_format": "oral",
            "length_bucket": "short_15s",
        },
        idempotency_key="stage4-marketing-prompt",
    )
    marketing_port = FakeLLMPort(_copy_output())
    asyncio.run(
        StructuredLLMExecutor(
            repository,
            marketing_port,
            app_id="builtin.marketing-copy",
            context_resolver=resolver,
        ).execute(marketing_run)
    )
    marketing_context = marketing_port.requests[0].context
    assert marketing_context["lineage"]["context_snapshot_id"] == snapshot.context_snapshot_id
    assert marketing_context["brand"]["values"]["phone"] == "仅本项目电话"
    assert "primary_color" not in marketing_context["brand"]["values"]

    source_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "提示词来源文案",
        source_app_run_id=marketing_run.app_run_id,
    )
    source_version = repository.append_artifact_version(
        source_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            "validation_facts": {"input": {}, "context": marketing_context},
            **_copy_output(),
        },
    )
    titles_run = _server_create_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.viral-titles",
        app_version="1.0.0",
        payload={
            "platform": "douyin",
            "objective": "click",
            "count": 5,
            "source_artifact_version_id": source_version.artifact_version_id,
        },
        idempotency_key="stage4-title-prompt",
    )
    title_port = FakeLLMPort(_title_output())
    asyncio.run(
        StructuredLLMExecutor(
            repository,
            title_port,
            app_id="builtin.viral-titles",
            context_resolver=resolver,
        ).execute(titles_run)
    )
    assert set(title_port.requests[0].context["brand"]["values"]) == {"display_name"}


def test_carousel_and_digital_local_delivery_consume_pinned_logo_colors_and_bgm(
    tmp_path,
):
    (
        repository,
        assets,
        project,
        snapshot,
        _old_logo,
        old_bgm,
        _new_logo,
        _new_bgm,
        content_image,
    ) = _stage4_project(tmp_path)
    resolver = ProjectContextResolver(repository, assets)
    source_run = _server_create_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.marketing-copy",
        app_version="1.0.0",
        payload={
            "goal": "图文来源",
            "product_or_service": "项目商品",
            "content_format": "carousel",
            "length_bucket": "short_15s",
        },
        idempotency_key="stage4-carousel-source",
    )
    source_artifact = repository.create_artifact(
        project.project_id,
        "copywriting",
        "图文来源",
        source_app_run_id=source_run.app_run_id,
    )
    source_version = repository.append_artifact_version(
        source_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            "validation_facts": {"input": {}, "context": {}},
            **_copy_output(),
        },
    )
    pages = [
        {
            "page_index": index,
            "purpose": "content",
            "text": f"第{index}页项目内容",
            "asset_refs": ["content-image"],
            "font_id": "noto-sans-sc-bold",
            "dimensions": {
                "width_px": CAROUSEL_WIDTH,
                "height_px": CAROUSEL_HEIGHT,
            },
        }
        for index in range(1, 4)
    ]
    carousel_run = _server_create_run(
        repository,
        resolver,
        project_id=project.project_id,
        app_id="builtin.douyin-carousel",
        app_version="1.0.0",
        payload={
            "goal": "生成品牌图文",
            "source_artifact_version_ids": [source_version.artifact_version_id],
            "page_count": 3,
            "template_id": "template:clean-01",
            "pages": pages,
        },
        idempotency_key="stage4-carousel-render",
    )
    content_path = assets.get_revision_path(content_image["asset_id"])
    assert content_path is not None
    renderer = DouyinCarouselRenderer(
        tmp_path / "carousel-output",
        asset_resolver=lambda _ref: content_path,
    )
    carousel_output = asyncio.run(
        DouyinCarouselExecutor(
            renderer,
            repository=repository,
            context_resolver=resolver,
        ).execute(carousel_run)
    )
    manifest = carousel_output.content["delivery_manifest"]["brand_render"]
    assert manifest["context_snapshot_id"] == snapshot.context_snapshot_id
    assert manifest["primary_color"] == "#112233"
    assert manifest["secondary_color"] == "#445566"
    assert manifest["logo_applied"] is True
    page_path = renderer.resolve_file_ref(carousel_output.file_refs[0])
    with Image.open(page_path).convert("RGB") as rendered:
        assert rendered.getpixel((1, 1)) == (17, 34, 51)
        assert rendered.getpixel((1, 1_000)) == (68, 85, 102)
        assert rendered.getpixel((1_005, 77)) != (17, 34, 51)

    sessions = IpBroadcastSessionStore(tmp_path / "sessions")
    adapter = IpBroadcastAppAdapter(
        repository,
        session_store=sessions,
        binding_store=IpBroadcastBindingStore(tmp_path / "bindings.json"),
        enforce_feature_flag=False,
        trusted_roots=[tmp_path / "digital-output"],
        context_resolver=resolver,
    )
    handle = adapter.create_or_resume(
        project.project_id,
        {
            "source_mode": "blank_project",
            "goal": "生成品牌口播",
            "source_artifact_version_ids": [],
        },
        idempotency_key="stage4-digital-local",
    )
    assert handle.run.context_snapshot_id == snapshot.context_snapshot_id
    expected_bgm_path = resolver.resolve_exact_asset_path(
        snapshot.payload["brand_context"]["values"]["default_bgm_ref"]
    )
    assert handle.session.state["bgm_path"] == str(expected_bgm_path)
    result = asyncio.run(adapter.execute_local(handle.run.app_run_id))
    assert result.run.state == "needs_review"
    versions = {}
    for artifact_id in result.run.output_artifact_ids:
        artifact = repository.get_artifact(artifact_id)
        versions[artifact.artifact_type] = repository.get_artifact_version(
            artifact.current_version_id
        )
    video_version = versions["video"]
    cover_version = versions["cover"]
    assert video_version.context_snapshot_id == snapshot.context_snapshot_id
    receipt = video_version.content["brand_delivery"]
    assert receipt["audio_bed"]["applied"] is True
    assert (
        receipt["audio_bed"]["asset_ref"]
        == snapshot.payload["brand_context"]["values"]["default_bgm_ref"]
    )
    assert receipt["audio_bed"]["input_sha256"] == receipt["audio_bed"]["output_sha256"]
    assert receipt["cover"]["logo_overlay"]["applied"] is True
    assert receipt["overridden_fields"] == ["ending_card_text", "phone"]
    cover_path = Path(tmp_path / "digital-output") / cover_version.file_refs[0]["relative_path"]
    with Image.open(cover_path).convert("RGB") as cover:
        assert cover.getpixel((1, 1)) == (17, 34, 51)
        assert cover.getpixel((1, 300)) == (68, 85, 102)
    staged_bgm = next(ref for ref in video_version.file_refs if ref["kind"] == "audio")
    staged_bgm_path = Path(tmp_path / "digital-output") / staged_bgm["relative_path"]
    expected_old_bgm = assets.get_revision_path(old_bgm["asset_id"])
    assert expected_old_bgm is not None
    assert staged_bgm_path.read_bytes() == expected_old_bgm.read_bytes()
    accepted = adapter.accept_local_outputs(result.run.app_run_id)
    assert accepted.run.state == "completed"
    assert accepted.session.step_status == {step: "done" for step in range(1, 7)}
    replay = adapter.accept_local_outputs(result.run.app_run_id)
    assert replay.run.state == "completed"
    assert replay.session.step_status == {step: "done" for step in range(1, 7)}


def test_schema_contains_artifact_and_handoff_context_provenance_columns(tmp_path):
    repository = AppCenterRepository(tmp_path / "schema.sqlite")
    with sqlite3.connect(repository.db_path) as connection:
        artifact_version_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(artifact_versions)")
        }
        handoff_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(artifact_handoffs)")
        }
    assert {"source_app_run_id", "context_snapshot_id"}.issubset(artifact_version_columns)
    assert {
        "source_context_snapshot_id",
        "target_context_snapshot_id",
    }.issubset(handoff_columns)
