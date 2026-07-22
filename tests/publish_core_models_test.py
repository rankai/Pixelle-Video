import hashlib

import pytest

from pixelle_video.services.publish.core_models import (
    ArtifactRef,
    MediaManifest,
    PlatformCopy,
    PublishPackageV2,
    PublishPolicy,
    PublishSource,
)


def _manifest(token: str = "asset_video") -> MediaManifest:
    return MediaManifest(sha256="sha256:" + "a" * 64, size_bytes=12, mime_type="video/mp4", path_token=token)


def _carousel_manifest(token: str = "asset_page") -> MediaManifest:
    return MediaManifest(sha256="sha256:" + "b" * 64, size_bytes=12, mime_type="image/png", path_token=token)


def _package(**overrides):
    values = {
        "package_id": "pkg_model_test",
        "project_id": "project_1",
        "source": PublishSource(kind="artifact_versions", artifact_ids=["a1"], artifact_version_ids=["v1"], source_revision="sha256:rev"),
        "artifact_refs": [ArtifactRef(artifact_id="a1", artifact_version_id="v1", artifact_type="video", content_fingerprint="sha256:content")],
        "video_manifest": _manifest(),
        "platform_copy": PlatformCopy(title="标题"),
        "policy": PublishPolicy(),
        "package_fingerprint": "sha256:" + hashlib.sha256(b"package").hexdigest(),
    }
    values.update(overrides)
    return PublishPackageV2(**values)


def test_source_is_exactly_one_artifact_or_legacy_session():
    with pytest.raises(ValueError, match="SOURCE_ARTIFACT_VERSION_REQUIRED"):
        PublishSource(kind="artifact_versions", source_revision="r1")
    with pytest.raises(ValueError, match="LEGACY_ARTIFACT_VERSIONS_FORBIDDEN"):
        PublishSource(kind="legacy_session", session_id="s1", artifact_version_ids=["v1"], source_revision="r1")


def test_package_requires_human_stop_and_references_source_version():
    with pytest.raises(ValueError, match="FINAL_PUBLISH_ACTION_NOT_ALLOWED"):
        PublishPolicy(allow_final_publish=True)
    with pytest.raises(ValueError, match="SOURCE_VERSION_NOT_REFERENCED"):
        _package(artifact_refs=[ArtifactRef(artifact_id="a1", artifact_version_id="other", artifact_type="video", content_fingerprint="sha256:content")])
    with pytest.raises(ValueError, match="COVER_ARTIFACT_REF_REQUIRED"):
        _package(cover_manifest=_manifest("asset_cover"))

    cover_ref = ArtifactRef(
        artifact_id="cover_1",
        artifact_version_id="cover_v1",
        artifact_type="cover",
        content_fingerprint="sha256:cover",
    )
    with pytest.raises(ValueError, match="COVER_ARTIFACT_REF_REQUIRED"):
        _package(
            source=PublishSource(
                kind="artifact_versions",
                artifact_ids=["a1", "cover_1"],
                artifact_version_ids=["v1", "cover_v1"],
                source_revision="sha256:rev",
            ),
            artifact_refs=[_package().artifact_refs[0], cover_ref],
        )
    with pytest.raises(ValueError, match="MULTIPLE_COVER_ARTIFACTS"):
        _package(
            source=PublishSource(
                kind="artifact_versions",
                artifact_ids=["a1", "cover_1", "cover_2"],
                artifact_version_ids=["v1", "cover_v1", "cover_v2"],
                source_revision="sha256:rev",
            ),
            artifact_refs=[
                _package().artifact_refs[0],
                cover_ref,
                cover_ref.model_copy(update={"artifact_id": "cover_2", "artifact_version_id": "cover_v2"}),
            ],
        )


def test_package_rejects_mixed_video_and_carousel_media_refs():
    with pytest.raises(ValueError, match="VIDEO_OR_CAROUSEL_ARTIFACT_REF_REQUIRED"):
        _package(
            source=PublishSource(
                kind="artifact_versions",
                artifact_ids=["a1", "carousel_1"],
                artifact_version_ids=["v1", "carousel_v1"],
                source_revision="sha256:rev",
            ),
            artifact_refs=[
                _package().artifact_refs[0],
                ArtifactRef(artifact_id="carousel_1", artifact_version_id="carousel_v1", artifact_type="carousel_package", content_fingerprint="sha256:carousel"),
            ],
        )

    with pytest.raises(ValueError, match="VIDEO_MANIFEST_FORBIDDEN_FOR_CAROUSEL"):
        _package(
            source=PublishSource(
                kind="artifact_versions",
                artifact_ids=["carousel_1"],
                artifact_version_ids=["carousel_v1"],
                source_revision="sha256:rev",
            ),
            artifact_refs=[ArtifactRef(artifact_id="carousel_1", artifact_version_id="carousel_v1", artifact_type="carousel_package", content_fingerprint="sha256:carousel")],
            carousel_manifests=[_carousel_manifest()],
        )
