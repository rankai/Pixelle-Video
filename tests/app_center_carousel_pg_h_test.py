"""PG-H contract E2E: title/source -> carousel -> PublishPackage -> publish center."""

import asyncio

from PIL import Image

from pixelle_video.app_center.carousel import DouyinCarouselExecutor, DouyinCarouselRenderer
from pixelle_video.app_center.llm_port import FakeLLMPort
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.app_center.runner import AppRunner
from pixelle_video.services.publish.account_models import PublishPlatform
from pixelle_video.services.publish.account_repository import PublishAccountRepository
from pixelle_video.services.publish.core_repository import PublishCoreRepository
from pixelle_video.services.publish.package_service import PublishPackageService


def test_pg_h_title_to_carousel_to_publish_center_contract_e2e(tmp_path):
    app_repository = AppCenterRepository(tmp_path / "app.sqlite")
    project = app_repository.create_project("PG-H 门店", "将标题做成抖音图文")
    title_artifact = app_repository.create_artifact(project.project_id, "selected_title", "已选标题")
    title_version = app_repository.append_artifact_version(
        title_artifact.artifact_id,
        content={"artifact_type": "selected_title", "title": "门店到店咨询的三个理由"},
    )
    asset_path = tmp_path / "registered-asset.png"
    Image.new("RGB", (640, 480), (210, 120, 80)).save(asset_path, format="PNG")
    llm = FakeLLMPort(
        {
            "page_count": 3,
            "template_id": "template:clean-01",
            "missing_facts": [],
            "pages": [
                {"page_index": index, "purpose": "卖点", "text": f"第{index}页：门店内容", "asset_ref": "asset:registered"}
                for index in range(1, 4)
            ],
        }
    )
    run = app_repository.create_app_run(
        project.project_id,
        "builtin.douyin-carousel",
        "1.0.0",
        {
            "goal": project.primary_goal,
            "page_count": 3,
            "asset_refs": ["asset:registered"],
            "source_artifact_version_ids": [title_version.artifact_version_id],
        },
        idempotency_key="pg-h-title-carousel-e2e",
    )
    renderer = DouyinCarouselRenderer(
        tmp_path / "carousel-exports",
        asset_root=tmp_path,
        asset_resolver=lambda ref: asset_path if ref == "asset:registered" else None,
    )
    runner = AppRunner(
        app_repository,
        executors={"builtin.douyin-carousel": DouyinCarouselExecutor(renderer, repository=app_repository, llm_port=llm)},
        enforce_readiness=False,
    )

    result = asyncio.run(runner.run(run.app_run_id))

    assert result.state == "needs_review"
    package_artifact = next(item for item in app_repository.list_artifacts(project.project_id) if item.artifact_type == "carousel_package")
    package_version = app_repository.get_artifact_version(package_artifact.current_version_id)
    assert package_version.content["title"] == "门店到店咨询的三个理由"
    assert package_version.content["description"] == ""
    assert package_version.content["hashtags"] == []
    assert package_version.content["title"]
    core_repository = PublishCoreRepository(tmp_path / "publishing.sqlite")
    package_service = PublishPackageService(app_repository, core_repository, media_roots=(tmp_path,), carousel_root=tmp_path / "carousel-exports")
    publish_package = package_service.create_from_artifact_versions(project.project_id, [package_version.artifact_version_id])
    package_service.verify_package(publish_package)

    refs = [item for item in app_repository.list_artifacts(project.project_id) if item.artifact_type == "publish_package_ref"]
    assert len(refs) == 1
    ref_content = app_repository.get_artifact_version(refs[0].current_version_id).content or {}
    assert ref_content["package_id"] == publish_package.package_id
    assert ref_content["source_artifact_version_ids"] == publish_package.source.artifact_version_ids

    account = PublishAccountRepository(core_repository.db_path).create_account(PublishPlatform.DOUYIN, "PG-H 账号", "profile_pg_h")
    publish_run, replay = core_repository.create_run(publish_package.package_id, account.account_id, PublishPlatform.DOUYIN, "pg-h-publish-run-001")

    assert replay is False
    assert publish_run.state.value == "queued"
    assert publish_run.human_confirmation_required is True
    assert publish_run.human_confirmed is False
