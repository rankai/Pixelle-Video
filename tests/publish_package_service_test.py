import pytest
from PIL import Image

from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.services.publish.core_models import PlatformCopy
from pixelle_video.services.publish.core_repository import PublishCoreRepository
from pixelle_video.services.publish.package_service import (
    PublishPackageBuildError,
    PublishPackageService,
)


def test_package_service_snapshots_artifact_versions_and_preflights_media(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("门店", "发布验证")
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"00000000ftypisom-video")
    cover_path = tmp_path / "cover.png"
    cover_path.write_bytes(b"\x89PNG\r\n\x1a\ncover")
    video = app.create_artifact(project.project_id, "video", "视频")
    cover = app.create_artifact(project.project_id, "cover", "封面")
    video_version = app.append_artifact_version(video.artifact_id, file_refs=[{"path": str(video_path)}])
    cover_version = app.append_artifact_version(cover.artifact_id, file_refs=[{"path": str(cover_path)}])
    service = PublishPackageService(app, PublishCoreRepository(tmp_path / "publishing.sqlite"), media_roots=(tmp_path,))

    package = service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_version.artifact_version_id])
    same_package = service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_version.artifact_version_id])

    assert package.source.artifact_version_ids == [video_version.artifact_version_id, cover_version.artifact_version_id]
    assert package.video_manifest.size_bytes == video_path.stat().st_size
    assert package.cover_manifest is not None
    assert package.policy.human_confirmation_required is True
    assert package.policy.allow_final_publish is False
    assert same_package.package_id == package.package_id
    assert same_package.package_fingerprint == package.package_fingerprint
    video_path.write_bytes(b"00000000ftypisom-mutated")
    with pytest.raises(PublishPackageBuildError, match="MEDIA_HASH_MISMATCH"):
        service.verify_package(package)


def test_legacy_and_artifact_sources_share_canonical_package_identity_and_ref(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("口播门店", "跨来源 handoff")
    video_path = tmp_path / "canonical.mp4"
    video_path.write_bytes(b"00000000ftypisom-canonical")
    cover_path = tmp_path / "canonical.png"
    cover_path.write_bytes(b"\x89PNG\r\n\x1a\ncanonical")
    video = app.create_artifact(project.project_id, "video", "视频")
    cover = app.create_artifact(project.project_id, "cover", "封面")
    video_version = app.append_artifact_version(video.artifact_id, file_refs=[{"path": str(video_path)}])
    cover_version = app.append_artifact_version(cover.artifact_id, file_refs=[{"path": str(cover_path)}])
    core = PublishCoreRepository(tmp_path / "publishing.sqlite")
    service = PublishPackageService(app, core, media_roots=(tmp_path,))
    copy = PlatformCopy(title="门店标题", description="门店描述", hashtags=["门店"])

    legacy_package = service.create_from_legacy_session(
        "legacy-canonical-1",
        project_id=project.project_id,
        video_path=video_path,
        cover_path=cover_path,
        platform_copy=copy,
    )
    artifact_package = service.create_from_artifact_versions(
        project.project_id,
        [video_version.artifact_version_id, cover_version.artifact_version_id],
        platform_copy=copy,
    )

    assert legacy_package.package_id == artifact_package.package_id
    assert legacy_package.package_fingerprint == artifact_package.package_fingerprint
    refs = [item for item in app.list_artifacts(project.project_id) if item.artifact_type == "publish_package_ref"]
    assert len(refs) == 1

    video_v2_path = tmp_path / "canonical-v2.mp4"
    video_v2_path.write_bytes(b"00000000ftypisom-canonical-v2")
    video_v2 = app.append_artifact_version(video.artifact_id, file_refs=[{"path": str(video_v2_path)}], source="rendered")
    replacement = service.create_from_artifact_versions(project.project_id, [video_v2.artifact_version_id, cover_version.artifact_version_id], platform_copy=copy)
    assert replacement.package_id != legacy_package.package_id
    assert core.get_package(legacy_package.package_id).invalidated_at is not None
    legacy_ref = next(item for item in app.list_artifacts(project.project_id, include_archived=True) if item.artifact_type == "publish_package_ref" and (app.get_artifact_version(item.current_version_id).content or {}).get("package_id") == legacy_package.package_id)
    assert (app.get_artifact_version(legacy_ref.current_version_id).content or {}).get("invalidated_at")


def test_publish_copy_artifact_is_canonicalized_and_empty_or_mismatch_fails_closed(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("口播门店", "发布文案 handoff")
    video_path = tmp_path / "copy.mp4"
    video_path.write_bytes(b"00000000ftypisom-copy")
    cover_path = tmp_path / "copy.png"
    cover_path.write_bytes(b"\x89PNG\r\n\x1a\ncopy")
    video = app.create_artifact(project.project_id, "video", "视频")
    cover = app.create_artifact(project.project_id, "cover", "封面")
    publish_copy = app.create_artifact(project.project_id, "publish_copy", "发布文案")
    video_version = app.append_artifact_version(video.artifact_id, file_refs=[{"path": str(video_path)}])
    cover_version = app.append_artifact_version(cover.artifact_id, file_refs=[{"path": str(cover_path)}])
    copy_version = app.append_artifact_version(publish_copy.artifact_id, content={"artifact_type": "publish_copy", "title": "从 artifact 读取", "description": "发布描述", "hashtags": ["门店"]})
    service = PublishPackageService(app, PublishCoreRepository(tmp_path / "publishing.sqlite"), media_roots=(tmp_path,))

    package = service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_version.artifact_version_id, copy_version.artifact_version_id])
    assert package.platform_copy.title == "从 artifact 读取"
    assert package.platform_copy.hashtags == ["门店"]

    empty = app.create_artifact(project.project_id, "publish_copy", "空文案")
    empty_version = app.append_artifact_version(empty.artifact_id, content={"artifact_type": "publish_copy", "title": "", "description": "", "hashtags": []})
    with pytest.raises(PublishPackageBuildError, match="ARTIFACT_PUBLISH_COPY_INVALID"):
        service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_version.artifact_version_id, empty_version.artifact_version_id])

    blank_hashtag = app.create_artifact(project.project_id, "publish_copy", "空话题")
    blank_hashtag_version = app.append_artifact_version(blank_hashtag.artifact_id, content={"artifact_type": "publish_copy", "title": "标题", "description": "描述", "hashtags": ["  "]})
    with pytest.raises(PublishPackageBuildError, match="ARTIFACT_PUBLISH_COPY_INVALID"):
        service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_version.artifact_version_id, blank_hashtag_version.artifact_version_id])

    duplicate = app.create_artifact(project.project_id, "publish_copy", "重复文案")
    duplicate_version = app.append_artifact_version(duplicate.artifact_id, content={"artifact_type": "publish_copy", "title": "第二份", "description": "重复", "hashtags": []})
    with pytest.raises(PublishPackageBuildError, match="MULTIPLE_PUBLISH_COPY_ARTIFACTS"):
        service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_version.artifact_version_id, copy_version.artifact_version_id, duplicate_version.artifact_version_id])

    with pytest.raises(PublishPackageBuildError, match="PUBLISH_COPY_MISMATCH"):
        service.create_from_artifact_versions(
            project.project_id,
            [video_version.artifact_version_id, cover_version.artifact_version_id, copy_version.artifact_version_id],
            platform_copy=PlatformCopy(title="不一致"),
        )


def test_new_artifact_version_invalidates_old_package_and_ref(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("口播门店", "版本 handoff")
    video_path = tmp_path / "versioned.mp4"
    video_path.write_bytes(b"00000000ftypisom-v1")
    cover_path = tmp_path / "versioned.png"
    cover_path.write_bytes(b"\x89PNG\r\n\x1a\nversioned")
    video = app.create_artifact(project.project_id, "video", "视频")
    cover = app.create_artifact(project.project_id, "cover", "封面")
    first_video = app.append_artifact_version(video.artifact_id, file_refs=[{"path": str(video_path)}])
    cover_version = app.append_artifact_version(cover.artifact_id, file_refs=[{"path": str(cover_path)}])
    core = PublishCoreRepository(tmp_path / "publishing.sqlite")
    service = PublishPackageService(app, core, media_roots=(tmp_path,))
    first = service.create_from_artifact_versions(project.project_id, [first_video.artifact_version_id, cover_version.artifact_version_id])

    second_video_path = tmp_path / "versioned-v2.mp4"
    second_video_path.write_bytes(b"00000000ftypisom-v2")
    second_video = app.append_artifact_version(video.artifact_id, file_refs=[{"path": str(second_video_path)}], source="rendered")
    second = service.create_from_artifact_versions(
        project.project_id,
        [second_video.artifact_version_id, cover_version.artifact_version_id],
    )

    assert second.package_id != first.package_id
    assert core.get_package(first.package_id).invalidated_at is not None
    old_ref = next(item for item in app.list_artifacts(project.project_id, include_archived=True) if item.artifact_type == "publish_package_ref" and (app.get_artifact_version(item.current_version_id).content or {}).get("package_id") == first.package_id)
    assert (app.get_artifact_version(old_ref.current_version_id).content or {}).get("invalidated_at")

    with pytest.raises(PublishPackageBuildError, match="PUBLISH_PACKAGE_STALE"):
        service.create_from_artifact_versions(project.project_id, [first_video.artifact_version_id, cover_version.artifact_version_id])
    assert core.get_package(second.package_id).invalidated_at is None
    active_ref = next(item for item in app.list_artifacts(project.project_id) if item.artifact_type == "publish_package_ref" and (app.get_artifact_version(item.current_version_id).content or {}).get("package_id") == second.package_id)
    assert not (app.get_artifact_version(active_ref.current_version_id).content or {}).get("invalidated_at")


def test_shared_artifact_same_version_does_not_invalidate_distinct_package(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("口播门店", "同版本不同封面")
    video_path = tmp_path / "shared.mp4"
    video_path.write_bytes(b"00000000ftypisom-shared")
    cover_a_path = tmp_path / "cover-a.png"
    cover_a_path.write_bytes(b"\x89PNG\r\n\x1a\ncover-a")
    cover_b_path = tmp_path / "cover-b.png"
    cover_b_path.write_bytes(b"\x89PNG\r\n\x1a\ncover-b")
    video = app.create_artifact(project.project_id, "video", "视频")
    cover_a = app.create_artifact(project.project_id, "cover", "封面 A")
    cover_b = app.create_artifact(project.project_id, "cover", "封面 B")
    video_version = app.append_artifact_version(video.artifact_id, file_refs=[{"path": str(video_path)}])
    cover_a_version = app.append_artifact_version(cover_a.artifact_id, file_refs=[{"path": str(cover_a_path)}])
    cover_b_version = app.append_artifact_version(cover_b.artifact_id, file_refs=[{"path": str(cover_b_path)}])
    service = PublishPackageService(app, PublishCoreRepository(tmp_path / "publishing.sqlite"), media_roots=(tmp_path,))

    first = service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_a_version.artifact_version_id])
    second = service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_b_version.artifact_version_id])

    assert first.package_id != second.package_id
    assert service.core_repository.get_package(first.package_id).invalidated_at is None
    assert service.core_repository.get_package(second.package_id).invalidated_at is None
    replay = service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_a_version.artifact_version_id])
    assert replay.package_id == first.package_id


def test_platform_copy_change_invalidates_previous_package_and_ref(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("口播门店", "文案版本替换")
    video_path = tmp_path / "copy-change.mp4"
    video_path.write_bytes(b"00000000ftypisom-copy-change")
    cover_path = tmp_path / "copy-change.png"
    cover_path.write_bytes(b"\x89PNG\r\n\x1a\ncopy-change")
    video = app.create_artifact(project.project_id, "video", "视频")
    cover = app.create_artifact(project.project_id, "cover", "封面")
    video_version = app.append_artifact_version(video.artifact_id, file_refs=[{"path": str(video_path)}])
    cover_version = app.append_artifact_version(cover.artifact_id, file_refs=[{"path": str(cover_path)}])
    service = PublishPackageService(app, PublishCoreRepository(tmp_path / "publishing.sqlite"), media_roots=(tmp_path,))

    first = service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_version.artifact_version_id], platform_copy=PlatformCopy(title="T1"))
    second = service.create_from_artifact_versions(project.project_id, [video_version.artifact_version_id, cover_version.artifact_version_id], platform_copy=PlatformCopy(title="T2"))

    assert first.package_id != second.package_id
    assert service.core_repository.get_package(first.package_id).invalidated_at is not None
    old_ref = next(item for item in app.list_artifacts(project.project_id, include_archived=True) if item.artifact_type == "publish_package_ref" and (app.get_artifact_version(item.current_version_id).content or {}).get("package_id") == first.package_id)
    assert (app.get_artifact_version(old_ref.current_version_id).content or {}).get("invalidated_at")


def test_package_service_rejects_missing_video_and_untrusted_media(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("门店", "发布验证")
    cover = app.create_artifact(project.project_id, "cover", "封面")
    cover_path = tmp_path / "cover.png"
    cover_path.write_bytes(b"\x89PNG\r\n\x1a\ncover")
    version = app.append_artifact_version(cover.artifact_id, file_refs=[{"path": str(cover_path)}])
    service = PublishPackageService(app, PublishCoreRepository(tmp_path / "publishing.sqlite"), media_roots=(tmp_path / "other",))
    with pytest.raises(PublishPackageBuildError, match="VIDEO_ARTIFACT_REQUIRED"):
        service.create_from_artifact_versions(project.project_id, [version.artifact_version_id])


def test_package_service_builds_carousel_publish_package_and_app_ref(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("图文门店", "发布图文")
    page_versions = []
    for index in range(1, 4):
        path = tmp_path / f"page-{index:02d}.png"
        Image.new("RGB", (1080, 1440), (index * 20, 80, 120)).save(path, format="PNG")
        page = app.create_artifact(project.project_id, "carousel_page", f"第{index}页")
        page_versions.append(app.append_artifact_version(
            page.artifact_id,
            content={"schema_version": 1, "artifact_type": "carousel_page", "page_index": index, "text": f"第{index}页"},
            file_refs=[{"file_key": path.name, "kind": "image", "mime_type": "image/png", "path": str(path)}],
        ))
    package_artifact = app.create_artifact(project.project_id, "carousel_package", "图文包")
    package_version = app.append_artifact_version(
        package_artifact.artifact_id,
        content={
            "schema_version": 1,
            "artifact_type": "carousel_package",
            "page_count": 3,
            "page_artifact_version_ids": [item.artifact_version_id for item in page_versions],
            "title": "门店图文标题",
            "description": "门店图文描述",
            "hashtags": ["门店运营"],
        },
    )
    service = PublishPackageService(app, PublishCoreRepository(tmp_path / "publishing.sqlite"), media_roots=(tmp_path,))

    publish_package = service.create_from_artifact_versions(project.project_id, [package_version.artifact_version_id])

    assert publish_package.video_manifest is None
    assert len(publish_package.carousel_manifests or []) == 3
    assert {item.artifact_type for item in publish_package.artifact_refs} == {"carousel_package", "carousel_page"}
    ref_artifacts = [item for item in app.list_artifacts(project.project_id) if item.artifact_type == "publish_package_ref"]
    assert len(ref_artifacts) == 1
    ref_version = app.list_artifact_versions(ref_artifacts[0].artifact_id)[0]
    assert ref_version.content["package_id"] == publish_package.package_id
    service.verify_package(publish_package)


def test_carousel_package_replacement_invalidates_previous_snapshot(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("图文门店", "重试图文")
    page_versions = []
    for index in range(1, 4):
        path = tmp_path / f"replace-page-{index:02d}.png"
        Image.new("RGB", (1080, 1440), (index * 30, 90, 130)).save(path, format="PNG")
        page = app.create_artifact(project.project_id, "carousel_page", f"第{index}页")
        page_versions.append(app.append_artifact_version(page.artifact_id, content={"artifact_type": "carousel_page", "page_index": index}, file_refs=[{"kind": "image", "path": str(path)}]))
    package_artifact = app.create_artifact(project.project_id, "carousel_package", "图文包")
    first_version = app.append_artifact_version(package_artifact.artifact_id, content={"artifact_type": "carousel_package", "page_count": 3, "page_artifact_version_ids": [item.artifact_version_id for item in page_versions]})
    service = PublishPackageService(app, PublishCoreRepository(tmp_path / "publishing.sqlite"), media_roots=(tmp_path,))
    first_package = service.create_from_artifact_versions(project.project_id, [first_version.artifact_version_id])

    replacement_page = app.append_artifact_version(page_versions[0].artifact_id, content={"artifact_type": "carousel_page", "page_index": 1, "text": "重试版本"}, file_refs=[{"kind": "image", "path": str(tmp_path / "replace-page-01.png")}], source="rendered")
    second_version = app.append_artifact_version(package_artifact.artifact_id, content={"artifact_type": "carousel_package", "page_count": 3, "page_artifact_version_ids": [replacement_page.artifact_version_id, page_versions[1].artifact_version_id, page_versions[2].artifact_version_id]})
    second_package = service.create_from_artifact_versions(project.project_id, [second_version.artifact_version_id], supersedes_package_id=first_package.package_id)

    assert service.core_repository.get_package(first_package.package_id).invalidated_at is not None
    assert second_package.package_id != first_package.package_id
    assert second_package.invalidated_at is None
    old_ref = next(
        artifact for artifact in app.list_artifacts(project.project_id)
        if artifact.artifact_type == "publish_package_ref"
        and (app.get_artifact_version(artifact.current_version_id).content or {}).get("package_id") == first_package.package_id
    )
    old_ref_content = app.get_artifact_version(old_ref.current_version_id).content or {}
    assert old_ref_content["invalidated_at"] is not None


def test_package_service_rejects_duplicate_carousel_page_versions(tmp_path):
    app = AppCenterRepository(tmp_path / "app.sqlite")
    project = app.create_project("图文门店", "拒绝重复页")
    page = app.create_artifact(project.project_id, "carousel_page", "第一页")
    page_version = app.append_artifact_version(
        page.artifact_id,
        content={"artifact_type": "carousel_page", "page_index": 1},
        file_refs=[{"kind": "image", "path": str(tmp_path / "page.png")}],
    )
    package = app.create_artifact(project.project_id, "carousel_package", "图文包")
    package_version = app.append_artifact_version(
        package.artifact_id,
        content={"artifact_type": "carousel_package", "page_count": 3, "page_artifact_version_ids": [page_version.artifact_version_id, page_version.artifact_version_id]},
    )
    service = PublishPackageService(app, PublishCoreRepository(tmp_path / "publishing.sqlite"), media_roots=(tmp_path,))

    with pytest.raises(PublishPackageBuildError, match="CAROUSEL_PAGE_ARTIFACT_INVALID"):
        service.create_from_artifact_versions(project.project_id, [package_version.artifact_version_id])
