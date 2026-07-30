import asyncio
import hashlib

import pytest
from PIL import Image

from pixelle_video.app_center.carousel import (
    CAROUSEL_PROMPT_VERSION_V2,
    CarouselRenderError,
    DouyinCarouselExecutor,
    DouyinCarouselRenderer,
)
from pixelle_video.app_center.llm_port import FakeLLMPort
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.runner import AppRunner


def _context_payload():
    return {
        "schema_version": 2,
        "subject_type": "store",
        "store_or_brand": {
            "name": "街角咖啡",
            "industry": "咖啡餐饮",
            "address": None,
            "contact": None,
        },
        "offer": {
            "name": "午后咖啡套餐",
            "category": "饮品套餐",
            "price_facts": [],
            "promotion_facts": [],
        },
        "audience": {"primary": "附近上班族", "scenes": ["午后休息"]},
        "selling_points": [
            {
                "fact_id": "selling-1",
                "text": "现磨咖啡",
                "source": "user",
                "source_ref": None,
            }
        ],
        "proof_points": [],
        "required_facts": [],
        "forbidden_claims": ["全城第一"],
        "asset_refs": [],
        "brand_revision_ref": None,
    }


def _v2_payload(project_id, context_id, source_version_id, asset_ref):
    return {
        "schema_version": 2,
        "app_id": "builtin.douyin-carousel",
        "input_schema_ref": "douyin-carousel-input.v2",
        "project_id": project_id,
        "context_snapshot_id": context_id,
        "task_brief": {
            "goal": "吸引附近上班族到店",
            "page_count": 3,
            "template_id": "template:clean-01",
            "asset_refs": [asset_ref],
            "cover_hook": "午后咖啡怎么选",
            "cta": "收藏后到店体验",
            "publish_description": "午后现磨咖啡选择",
            "hashtags": ["咖啡", "门店"],
        },
        "style_ref": {
            "style_id": "carousel.store_recommendation",
            "version": 1,
        },
        "custom_style_reference": None,
        "source_artifact_version_ids": [source_version_id],
    }


def _context_bound_selected_title(
    repository,
    *,
    project_id,
    context_snapshot_id,
    title,
    idempotency_key,
):
    source_run = repository.create_app_run(
        project_id,
        "builtin.viral-titles",
        "1.0.0",
        {"goal": "生成已选标题"},
        idempotency_key=idempotency_key,
        context_snapshot_id=context_snapshot_id,
    )
    source = repository.create_artifact(
        project_id,
        "selected_title",
        title,
        source_app_run_id=source_run.app_run_id,
    )
    source_version = repository.append_artifact_version(
        source.artifact_id,
        content={
            "artifact_type": "selected_title",
            "title": title,
        },
    )
    assert source_version.context_snapshot_id == context_snapshot_id
    return source_version


def test_carousel_v2_uses_pinned_context_style_source_and_asset_revision(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("咖啡图文", "吸引附近上班族到店")
    snapshot = repository.save_context_snapshot(
        project.project_id, _context_payload(), schema_version=2
    )
    source_version = _context_bound_selected_title(
        repository,
        project_id=project.project_id,
        context_snapshot_id=snapshot.context_snapshot_id,
        title="午后咖啡怎么选",
        idempotency_key="carousel-v2-title-source-001",
    )
    asset_ref = "asset:coffee@revision-coffee-2"
    asset_path = tmp_path / "coffee.png"
    Image.new("RGB", (640, 480), (115, 72, 45)).save(asset_path, format="PNG")
    port = FakeLLMPort(
        {
            "page_count": 3,
            "template_id": "template:clean-01",
            "missing_facts": [],
            "pages": [
                {
                    "page_index": index,
                    "purpose": "场景" if index == 1 else "卖点",
                    "text": f"第{index}页：现磨咖啡",
                    "asset_ref": asset_ref,
                }
                for index in range(1, 4)
            ],
        }
    )
    run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.1.0",
        _v2_payload(
            project.project_id,
            snapshot.context_snapshot_id,
            source_version.artifact_version_id,
            asset_ref,
        ),
        idempotency_key="carousel-v2-run-001",
        context_snapshot_id=snapshot.context_snapshot_id,
    )
    runner = AppRunner(
        repository,
        executors={
            "builtin.douyin-carousel": DouyinCarouselExecutor(
                DouyinCarouselRenderer(
                    tmp_path / "exports",
                    asset_resolver=lambda ref: asset_path if ref == asset_ref else None,
                ),
                repository=repository,
                llm_port=port,
            )
        },
        enforce_readiness=False,
    )

    result = asyncio.run(runner.run(run.app_run_id))

    assert result.state == "needs_review"
    assert port.requests[0].input_schema_ref == "douyin-carousel-input.v2"
    assert port.requests[0].prompt_version == CAROUSEL_PROMPT_VERSION_V2
    assert "每页只承载一个主要信息" in port.requests[0].trusted_style_rules
    assert port.requests[0].prompt_variables["asset_refs"] == [asset_ref]
    package = next(
        item
        for item in repository.list_artifacts(project.project_id)
        if item.artifact_type == "carousel_package"
    )
    package_version = repository.get_artifact_version(package.current_version_id)
    assert package_version.content["title"] == "午后咖啡怎么选"
    assert package_version.content["description"] == "午后现磨咖啡选择"
    assert package_version.content["hashtags"] == ["咖啡", "门店"]


def test_carousel_v2_custom_style_reference_cannot_import_facts(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文", "到店")
    snapshot = repository.save_context_snapshot(
        project.project_id, _context_payload(), schema_version=2
    )
    source_version = _context_bound_selected_title(
        repository,
        project_id=project.project_id,
        context_snapshot_id=snapshot.context_snapshot_id,
        title="标题",
        idempotency_key="carousel-v2-invalid-style-title-source",
    )
    payload = _v2_payload(
        project.project_id,
        snapshot.context_snapshot_id,
        source_version.artifact_version_id,
        "asset:known",
    )
    text = "模仿短句表达，但不要采用其中的价格和销量"
    payload["style_ref"] = None
    payload["custom_style_reference"] = {
        "text": text,
        "content_fingerprint": f"sha256:{hashlib.sha256(text.encode()).hexdigest()}",
        "facts_imported": True,
    }
    run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.1.0",
        payload,
        idempotency_key="carousel-v2-invalid-style",
        context_snapshot_id=snapshot.context_snapshot_id,
    )

    with pytest.raises(CarouselRenderError) as error:
        asyncio.run(
            DouyinCarouselExecutor(
                repository=repository,
                llm_port=FakeLLMPort({}),
            ).execute(run)
        )

    assert error.value.code == "CAROUSEL_STYLE_INVALID"
