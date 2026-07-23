import asyncio
import hashlib
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from PIL import Image

from api.routers import app_center as app_center_router
from api.routers import publish_v2 as publish_v2_router
from api.schemas.app_center import CarouselPageRetryRequest
from pixelle_video.app_center.carousel import (
    CAROUSEL_HEIGHT,
    CAROUSEL_WIDTH,
    CarouselRenderError,
    DouyinCarouselExecutor,
    DouyinCarouselRenderer,
    resolve_registered_asset,
)
from pixelle_video.app_center.llm_port import FakeLLMPort
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.runner import AppRunner, ExecutorOutput, RelatedArtifactOutput
from pixelle_video.services.publish.core_repository import PublishCoreRepository
from pixelle_video.services.publish.package_service import PublishPackageService


def _asset(tmp_path):
    path = tmp_path / "asset.png"
    Image.new("RGB", (640, 480), (214, 152, 74)).save(path, format="PNG")
    return path


def _pages(asset_path, count=3, *, include_path=True):
    pages = [
        {
            "page_index": index,
            "dimensions": {"width_px": CAROUSEL_WIDTH, "height_px": CAROUSEL_HEIGHT},
            "text": f"第{index}页：门店短视频内容验证",
            "font_id": "noto-sans-sc-bold",
            "asset_refs": [f"asset-{index}"],
        }
        for index in range(1, count + 1)
    ]
    if include_path:
        for page in pages:
            page["asset_path"] = str(asset_path)
    return pages


@pytest.mark.parametrize("page_count", [3, 5, 8])
def test_renderer_exports_allowed_page_counts_and_stable_refs(tmp_path, page_count):
    renderer = DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path)
    content, file_refs = renderer.render_package(
        _pages(_asset(tmp_path), page_count),
        title="门店图文标题",
        description="这是图文描述",
        hashtags=["门店运营"],
        source_artifact_version_ids=["artifact-version-1"],
        run_ref="run/with unsafe chars",
    )

    assert content["artifact_type"] == "carousel_package"
    assert content["page_count"] == page_count
    assert content["publish_copy_required"] is True
    assert content["publish_v2_compatible"] is True
    assert [ref["file_key"] for ref in file_refs[:-1]] == [f"page-{i:02d}.png" for i in range(1, page_count + 1)]
    zip_ref = file_refs[-1]
    assert zip_ref["mime_type"] == "application/zip"
    zip_path = renderer.resolve_file_ref(zip_ref)
    assert "path" not in zip_ref
    assert zip_path.is_absolute()
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.namelist() == [f"page-{i:02d}.png" for i in range(1, page_count + 1)]
        for name in archive.namelist():
            with Image.open(archive.open(name)) as image:
                assert image.size == (CAROUSEL_WIDTH, CAROUSEL_HEIGHT)
    assert zip_ref["sha256"].startswith("sha256:")
    assert hashlib.sha256(zip_path.read_bytes()).hexdigest() == zip_ref["sha256"][7:]


def test_renderer_zip_bytes_are_reproducible_for_same_inputs(tmp_path):
    asset_path = _asset(tmp_path)
    renderer = DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path)
    first_content, first_refs = renderer.render_package(_pages(asset_path), run_ref="run-a")
    second_content, second_refs = renderer.render_package(_pages(asset_path), run_ref="run-b")
    assert first_content["export_manifest"]["zip_sha256"] == second_content["export_manifest"]["zip_sha256"]
    assert first_refs[-1]["sha256"] == second_refs[-1]["sha256"]


def test_renderer_keeps_selected_asset_visible_under_copy_overlay(tmp_path):
    asset_path = _asset(tmp_path)
    renderer = DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path)
    renderer.render_package(_pages(asset_path, 3), run_ref="asset-visible")

    with Image.open(tmp_path / "exports" / "asset-visible" / "pages" / "page-01.png") as image:
        # The source image occupies y=155..775. A previous RGB draw call used a
        # 4-tuple and made this whole region flat beige, hiding the asset.
        assert image.getpixel((540, 300)) != (248, 245, 238)
        assert image.getpixel((540, 300))[0] < 245


def test_renderer_fails_closed_for_page_set_asset_font_and_overflow(tmp_path):
    renderer = DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path)
    asset_path = _asset(tmp_path)
    with pytest.raises(CarouselRenderError, match="只能是 3、5 或 8"):
        renderer.render_package(_pages(asset_path, 4), run_ref="invalid-count")
    missing = _pages(asset_path)
    missing[1]["asset_path"] = str(tmp_path / "missing.png")
    with pytest.raises(CarouselRenderError) as missing_error:
        renderer.render_package(missing, run_ref="missing-asset")
    assert missing_error.value.code == "ASSET_NOT_FOUND"
    bad_font = _pages(asset_path)
    bad_font[0]["font_id"] = "unregistered-font"
    with pytest.raises(CarouselRenderError) as font_error:
        renderer.render_package(bad_font, run_ref="missing-font")
    assert font_error.value.code == "FONT_MISSING"
    overflow = _pages(asset_path)
    overflow[0]["text"] = "超长" * 300
    with pytest.raises(CarouselRenderError) as overflow_error:
        renderer.render_package(overflow, run_ref="overflow")
    assert overflow_error.value.code == "TEXT_OVERFLOW"

    with pytest.raises(CarouselRenderError) as direct_path_error:
        DouyinCarouselRenderer(tmp_path / "untrusted").render_package(_pages(asset_path), run_ref="untrusted-path")
    assert direct_path_error.value.code == "ASSET_PATH_NOT_ALLOWED"

    outside_asset = tmp_path.parent / "carousel-outside.png"
    Image.new("RGB", (32, 32), (10, 20, 30)).save(outside_asset, format="PNG")
    outside = _pages(asset_path)
    outside[0]["asset_path"] = str(outside_asset)
    with pytest.raises(CarouselRenderError) as outside_error:
        renderer.render_package(outside, run_ref="outside-root")
    assert outside_error.value.code == "ASSET_OUTSIDE_ROOT"


def test_renderer_retry_isolates_page_and_requires_new_version(tmp_path):
    asset_path = _asset(tmp_path)
    renderer = DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path)
    renderer.render_package(_pages(asset_path), run_ref="retry-run")
    page_one = tmp_path / "exports" / "retry-run" / "pages" / "page-01.png"
    original_digest = hashlib.sha256(page_one.read_bytes()).hexdigest()
    changed_page = _pages(asset_path)[1] | {"text": "第二页的新版本文案"}
    retried = renderer.retry_page(changed_page, run_ref="retry-run", version_number=2)
    assert retried.path.name == "page-02-v2.png"
    assert page_one.exists()
    assert hashlib.sha256(page_one.read_bytes()).hexdigest() == original_digest
    with pytest.raises(CarouselRenderError) as version_error:
        renderer.retry_page(changed_page, run_ref="retry-run", version_number=0)
    assert version_error.value.code == "RETRY_VERSION_INVALID"


def test_carousel_executor_integrates_with_app_runner_and_review_lifecycle(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文项目", "生成抖音图文")
    source_artifact = repository.create_artifact(project.project_id, "selected_title", "来源标题")
    source_version = repository.append_artifact_version(
        source_artifact.artifact_id,
        content={"title": "门店亮点", "source": "selected_title"},
    )
    asset_path = _asset(tmp_path)
    run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.0.0",
        {
            "goal": "提升门店到店咨询",
            "pages": _pages(asset_path, include_path=False),
            "title": "图文标题",
            "description": "图文描述",
            "hashtags": ["门店运营"],
            "source_artifact_version_ids": [source_version.artifact_version_id],
        },
        idempotency_key="carousel-run-1",
    )
    renderer = DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path, asset_resolver=lambda _ref: asset_path)
    runner = AppRunner(
        repository,
        executors={"builtin.douyin-carousel": DouyinCarouselExecutor(renderer, repository=repository)},
        enforce_readiness=False,
    )
    result = asyncio.run(runner.run(run.app_run_id))
    assert result.state == "needs_review"
    artifact = repository.get_artifact(result.output_artifact_ids[0])
    assert artifact.artifact_type == "carousel_package"
    version = repository.list_artifact_versions(artifact.artifact_id)[0]
    assert version.content["page_count"] == 3
    assert len(version.file_refs) == 4
    assert all("path" not in file_ref and not Path(file_ref["relative_path"]).is_absolute() for file_ref in version.file_refs)
    output_artifacts = repository.list_artifacts(project.project_id)
    artifact_types = [item.artifact_type for item in output_artifacts]
    assert artifact_types.count("carousel_plan") == 1
    assert artifact_types.count("carousel_page") == 3
    assert artifact_types.count("carousel_package") == 1
    assert version.content["source_plan_artifact_version_id"].startswith("artifact_version_")
    assert all(item.startswith("artifact_version_") for item in version.content["page_artifact_version_ids"])
    assert runner.accept_output(result.app_run_id).state == "completed"


def test_carousel_executor_derives_publish_copy_from_trusted_sources(tmp_path):
    repository = AppCenterRepository(tmp_path / "publish-copy.sqlite")
    project = repository.create_project("发布文案映射", "从既有内容生成图文")
    title_artifact = repository.create_artifact(project.project_id, "selected_title", "标题")
    title_version = repository.append_artifact_version(title_artifact.artifact_id, content={"title": "来源标题", "hashtags": ["门店运营"]})
    copy_artifact = repository.create_artifact(project.project_id, "copywriting", "文案")
    copy_version = repository.append_artifact_version(
        copy_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "copywriting",
            "variants": [
                {"version_name": "版本1", "angle": "场景", "full_text": "来源文案正文到店了解", "hook": "来源", "body": "文案正文", "cta": "到店了解"},
                {"version_name": "版本2", "angle": "利益", "full_text": "来源文案正文马上行动", "hook": "来源", "body": "文案正文", "cta": "马上行动"},
                {"version_name": "版本3", "angle": "好奇", "full_text": "来源文案正文欢迎咨询", "hook": "来源", "body": "文案正文", "cta": "欢迎咨询"},
            ],
            "missing_facts": [],
            "risk_flags": [],
        },
    )
    run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.0.0",
        {
            "goal": "从可信来源生成",
            "pages": _pages(_asset(tmp_path), include_path=False),
            "source_artifact_version_ids": [title_version.artifact_version_id, copy_version.artifact_version_id],
        },
        idempotency_key="carousel-publish-copy-source-001",
    )
    asset_path = tmp_path / "asset.png"
    renderer = DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path, asset_resolver=lambda _ref: asset_path)
    result = asyncio.run(AppRunner(repository, executors={"builtin.douyin-carousel": DouyinCarouselExecutor(renderer, repository=repository)}, enforce_readiness=False).run(run.app_run_id))
    assert result.state == "needs_review", {"error_code": result.error_code, "diagnostic": result.diagnostic_json}
    package = repository.get_artifact(result.output_artifact_ids[0])
    version = repository.get_artifact_version(package.current_version_id)

    assert version.content["title"] == "来源标题"
    assert version.content["description"] == "来源文案正文到店了解"
    assert version.content["hashtags"] == ["门店运营"]


def test_carousel_executor_rejects_missing_or_cross_project_sources(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文项目", "来源校验")
    asset_path = _asset(tmp_path)
    base_payload = {"goal": "到店", "pages": _pages(asset_path, include_path=False), "source_artifact_version_ids": ["missing"]}
    missing_run = repository.create_app_run(project.project_id, "builtin.douyin-carousel", "1.0.0", base_payload, idempotency_key="missing-source")
    runner = AppRunner(
        repository,
        executors={"builtin.douyin-carousel": DouyinCarouselExecutor(
            DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path, asset_resolver=lambda _ref: asset_path),
            repository=repository,
        )},
        enforce_readiness=False,
    )
    missing_result = asyncio.run(runner.run(missing_run.app_run_id))
    assert missing_result.state == "failed"
    assert missing_result.error_code == "APP_EXECUTOR_FAILED"

    other_project = repository.create_project("其他项目", "隔离来源")
    other_artifact = repository.create_artifact(other_project.project_id, "selected_title", "其他标题")
    other_version = repository.append_artifact_version(other_artifact.artifact_id, content={"title": "其他"})
    cross_run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.0.0",
        {**base_payload, "source_artifact_version_ids": [other_version.artifact_version_id]},
        idempotency_key="cross-source",
    )
    cross_result = asyncio.run(runner.run(cross_run.app_run_id))
    assert cross_result.state == "failed"
    assert cross_result.error_code == "APP_EXECUTOR_FAILED"


def test_carousel_executor_rejects_direct_asset_path_even_with_renderer_root(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文项目", "资产边界")
    source_artifact = repository.create_artifact(project.project_id, "selected_title", "来源标题")
    source_version = repository.append_artifact_version(source_artifact.artifact_id, content={"title": "亮点"})
    asset_path = _asset(tmp_path)
    run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.0.0",
        {
            "goal": "到店",
            "pages": _pages(asset_path),
            "source_artifact_version_ids": [source_version.artifact_version_id],
        },
        idempotency_key="direct-asset-path",
    )
    renderer = DouyinCarouselRenderer(tmp_path / "exports", asset_root=tmp_path)
    runner = AppRunner(
        repository,
        executors={"builtin.douyin-carousel": DouyinCarouselExecutor(renderer, repository=repository)},
        enforce_readiness=False,
    )
    result = asyncio.run(runner.run(run.app_run_id))
    assert result.state == "failed"
    assert result.error_code == "APP_EXECUTOR_FAILED"


def test_registered_asset_resolver_accepts_ids_and_rejects_paths(monkeypatch, tmp_path):
    asset_path = _asset(tmp_path)

    class FakeAssetLibrary:
        def get_asset(self, asset_id):
            return {"asset_id": asset_id, "media_kind": "image", "status": "ready"} if asset_id == "known" else None

        def get_revision_path(self, asset_id):
            return asset_path if asset_id == "known" else None

    monkeypatch.setattr("pixelle_video.services.assets_v2.repository.AssetLibraryRepository", FakeAssetLibrary)
    assert resolve_registered_asset("asset:known") == asset_path
    assert resolve_registered_asset("/tmp/arbitrary.png") is None
    assert resolve_registered_asset("../known") is None


def test_runner_compensates_partial_related_artifact_persistence(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文项目", "产物回滚")

    class FailingRelatedExecutor:
        async def execute(self, _app_run):
            return ExecutorOutput(
                artifact_type="carousel_package",
                name="package",
                content={"schema_version": 1, "artifact_type": "carousel_package"},
                related_artifacts=[
                    RelatedArtifactOutput("plan", "carousel_plan", "plan", {"schema_version": 1, "artifact_type": "carousel_plan"}),
                    RelatedArtifactOutput("page:1", "carousel_page", "page", {"provider": "must-not-persist"}),
                ],
            )

    run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.0.0",
        {"goal": "回滚", "source_artifact_version_ids": ["source-v1"], "pages": []},
        idempotency_key="related-rollback",
    )
    runner = AppRunner(repository, executors={"builtin.douyin-carousel": FailingRelatedExecutor()}, enforce_readiness=False)
    result = asyncio.run(runner.run(run.app_run_id))
    assert result.state == "failed"
    assert result.output_artifact_ids == []
    assert repository.list_artifacts(project.project_id) == []


def test_carousel_executor_plans_pages_through_shared_llm_port(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文规划", "用已有事实生成图文")
    context_snapshot = repository.save_context_snapshot(project.project_id, {"brand_tone": "可信、克制"})
    source_artifact = repository.create_artifact(project.project_id, "selected_title", "来源标题")
    source_version = repository.append_artifact_version(source_artifact.artifact_id, content={"title": "门店亮点"})
    asset_path = _asset(tmp_path)
    llm = FakeLLMPort({
        "page_count": 3,
        "template_id": "template:clean-01",
        "missing_facts": [],
        "pages": [
            {"page_index": index, "purpose": "内容", "text": f"第{index}页", "asset_ref": "asset-1"}
            for index in range(1, 4)
        ],
    })
    run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.0.0",
        {
            "goal": "到店咨询",
            "page_count": 3,
            "asset_refs": ["asset-1"],
            "source_artifact_version_ids": [source_version.artifact_version_id],
        },
        idempotency_key="carousel-llm-plan",
        context_snapshot_id=context_snapshot.context_snapshot_id,
    )
    renderer = DouyinCarouselRenderer(
        tmp_path / "exports",
        asset_root=tmp_path,
        asset_resolver=lambda ref: asset_path if ref == "asset-1" else None,
    )
    runner = AppRunner(
        repository,
        executors={"builtin.douyin-carousel": DouyinCarouselExecutor(renderer, repository=repository, llm_port=llm)},
        enforce_readiness=False,
    )
    result = asyncio.run(runner.run(run.app_run_id))
    assert result.state == "needs_review"
    assert len(llm.requests) == 1
    request = llm.requests[0]
    assert request.app_id == "builtin.douyin-carousel"
    assert request.prompt_variables["asset_refs"] == ["asset-1"]
    assert request.context == {"brand_tone": "可信、克制"}
    package = repository.get_artifact(result.output_artifact_ids[0])
    package_version = repository.list_artifact_versions(package.artifact_id)[0]
    assert package_version.content["page_count"] == 3


def test_carousel_planner_rejects_model_asset_ref_not_in_input(tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文规划失败", "拒绝模型编造资产")
    source_artifact = repository.create_artifact(project.project_id, "selected_title", "来源标题")
    source_version = repository.append_artifact_version(source_artifact.artifact_id, content={"title": "门店亮点"})
    llm = FakeLLMPort({
        "page_count": 3,
        "template_id": "template:clean-01",
        "missing_facts": [],
        "pages": [
            {"page_index": index, "purpose": "内容", "text": f"第{index}页", "asset_ref": "asset-not-supplied"}
            for index in range(1, 4)
        ],
    })
    run = repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.0.0",
        {"goal": "到店", "page_count": 3, "asset_refs": ["asset-1"], "source_artifact_version_ids": [source_version.artifact_version_id]},
        idempotency_key="carousel-llm-invalid-ref",
    )
    runner = AppRunner(
        repository,
        executors={"builtin.douyin-carousel": DouyinCarouselExecutor(repository=repository, llm_port=llm)},
        enforce_readiness=False,
    )
    result = asyncio.run(runner.run(run.app_run_id))
    assert result.state == "failed"
    assert result.error_code == "STRUCTURED_OUTPUT_INVALID"
    assert [artifact.artifact_type for artifact in repository.list_artifacts(project.project_id)] == ["selected_title"]


def test_carousel_page_retry_creates_new_version_and_invalidates_publish_package(monkeypatch, tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文重试", "替换一页")
    source = repository.create_artifact(project.project_id, "selected_title", "标题")
    source_version = repository.append_artifact_version(source.artifact_id, content={"title": "门店"})
    run = repository.create_app_run(project.project_id, "builtin.douyin-carousel", "1.0.0", {"goal": "到店", "source_artifact_version_ids": [source_version.artifact_version_id], "pages": []}, idempotency_key="carousel-retry-run")
    asset_path = _asset(tmp_path)
    page_artifacts = []
    page_versions = []
    for index in range(1, 4):
        page = repository.create_artifact(project.project_id, "carousel_page", f"第{index}页", source_app_run_id=run.app_run_id)
        version = repository.append_artifact_version(
            page.artifact_id,
            content={"artifact_type": "carousel_page", "page_index": index, "text": f"第{index}页", "asset_refs": ["asset:known"]},
            file_refs=[{"file_key": f"page-{index:02d}.png", "kind": "image", "path": str(asset_path)}],
        )
        page_artifacts.append(page)
        page_versions.append(version)
    package_artifact = repository.create_artifact(project.project_id, "carousel_package", "图文包", source_app_run_id=run.app_run_id)
    package_version = repository.append_artifact_version(
        package_artifact.artifact_id,
        content={"artifact_type": "carousel_package", "page_count": 3, "page_artifact_version_ids": [item.artifact_version_id for item in page_versions]},
        file_refs=[{"file_key": f"page-{index:02d}.png", "kind": "image", "path": str(asset_path)} for index in range(1, 4)],
    )
    core = PublishCoreRepository(tmp_path / "publishing.sqlite")
    publish_service = PublishPackageService(repository, core, media_roots=(tmp_path,), carousel_root=tmp_path / "exports")
    old_package = publish_service.create_from_artifact_versions(project.project_id, [package_version.artifact_version_id])
    old_ref = next(
        artifact for artifact in repository.list_artifacts(project.project_id)
        if artifact.artifact_type == "publish_package_ref"
        and (repository.get_artifact_version(artifact.current_version_id).content or {}).get("package_id") == old_package.package_id
    )

    monkeypatch.setenv("PIXELLE_APP_CENTER_DOUYIN_CAROUSEL", "true")
    monkeypatch.setattr(app_center_router, "get_app_center_repository", lambda: repository)
    monkeypatch.setattr(publish_v2_router, "get_publish_core_repository", lambda: core)
    monkeypatch.setattr(publish_v2_router, "get_publish_package_service", lambda: publish_service)
    actual_renderer = DouyinCarouselRenderer
    monkeypatch.setattr(app_center_router, "DouyinCarouselRenderer", lambda asset_resolver=None: actual_renderer(tmp_path / "exports", asset_resolver=lambda _ref: asset_path))

    response = app_center_router.retry_carousel_page(page_artifacts[0].artifact_id, CarouselPageRetryRequest(text="重试后的第一页", asset_refs=["asset:known"]))

    assert response["page_artifact_version"]["version_number"] == 2
    assert response["package_artifact_version"]["version_number"] == 2
    assert core.get_package(old_package.package_id).invalidated_at is not None
    old_ref_current = repository.get_artifact(old_ref.artifact_id)
    old_ref_content = repository.get_artifact_version(old_ref_current.current_version_id).content or {}
    assert old_ref_content["invalidated_at"] is not None
    assert old_ref_content["invalidation_reason"] == "CAROUSEL_ARTIFACT_VERSION_REPLACED"
    assert response["publish_package"]["package_id"] != old_package.package_id

    class FailingPublishService:
        def create_from_artifact_versions(self, *_args, **_kwargs):
            raise RuntimeError("injected publish failure")

        def invalidate_publish_package_ref(self, _package):
            return None

    page_version_count = len(repository.list_artifact_versions(page_artifacts[0].artifact_id))
    package_version_count = len(repository.list_artifact_versions(package_artifact.artifact_id))
    monkeypatch.setattr(publish_v2_router, "get_publish_package_service", lambda: FailingPublishService())
    with pytest.raises(HTTPException) as retry_error:
        app_center_router.retry_carousel_page(
            page_artifacts[0].artifact_id,
            CarouselPageRetryRequest(text="故障重试", asset_refs=["asset:known"]),
        )
    assert retry_error.value.status_code == 409
    assert retry_error.value.detail == "CAROUSEL_RETRY_FAILED"
    assert len(repository.list_artifact_versions(page_artifacts[0].artifact_id)) == page_version_count
    assert len(repository.list_artifact_versions(package_artifact.artifact_id)) == package_version_count


def test_carousel_page_retry_is_blocked_when_feature_flag_is_off(monkeypatch):
    monkeypatch.setattr(app_center_router, "get_app", lambda _app_id: {"enabled": False})

    with pytest.raises(HTTPException) as error:
        app_center_router.retry_carousel_page(
            "artifact_page_1",
            CarouselPageRetryRequest(text="不应执行", asset_refs=["asset:known"]),
        )

    assert error.value.status_code == 409
    assert error.value.detail == "APP_NOT_READY"


def test_carousel_package_download_is_independent_of_publish_v2_flag(monkeypatch, tmp_path):
    repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = repository.create_project("图文导出", "发布 V2 关闭仍可导出")
    package = repository.create_artifact(project.project_id, "carousel_package", "图文包")
    export_root = tmp_path / "carousel"
    export_file = export_root / "run-1" / "carousel-package.zip"
    export_file.parent.mkdir(parents=True)
    export_file.write_bytes(b"zip-fixture")
    repository.append_artifact_version(
        package.artifact_id,
        content={"artifact_type": "carousel_package", "page_count": 3},
        file_refs=[{"file_key": "carousel-package.zip", "relative_path": "run-1/carousel-package.zip", "kind": "zip", "mime_type": "application/zip"}],
    )
    monkeypatch.setattr(app_center_router, "get_app_center_repository", lambda: repository)
    monkeypatch.setattr(app_center_router, "get_data_path", lambda *_parts: export_root)
    monkeypatch.setenv("PIXELLE_PUBLISH_V2_ENABLED", "0")

    response = app_center_router.download_artifact_file(package.artifact_id, "carousel-package.zip")

    assert response.path == export_file
    assert response.media_type == "application/zip"
