"""Build immutable PUB-2 publish packages from application-center artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from pixelle_video.app_center.models import Artifact, ArtifactVersion
from pixelle_video.app_center.repository import AppCenterRepository
from pixelle_video.utils.os_util import get_data_path

from .core_models import (
    ArtifactRef,
    PlatformCopy,
    PublishPackageV2,
    PublishPolicy,
    PublishSource,
    utc_now,
)
from .core_repository import PublishCoreRepository
from .media_preflight import MediaPreflightError, preflight_media, verify_manifest


class PublishPackageBuildError(ValueError):
    """A trusted artifact set cannot become a publishable package."""


PathResolver = Callable[[Artifact, ArtifactVersion, str], str | Path | None]


class PublishPackageService:
    """Create package snapshots without exposing local paths to API consumers.

    The default resolver only understands internal artifact file references. A
    desktop/session resolver can be injected for legacy sessions; its result is
    still passed through the same trusted-root and hash preflight.
    """

    def __init__(
        self,
        app_repository: AppCenterRepository,
        core_repository: PublishCoreRepository,
        *,
        media_roots: Iterable[Path] | None = None,
        path_resolver: PathResolver | None = None,
        carousel_root: str | Path | None = None,
    ):
        self.app_repository = app_repository
        self.core_repository = core_repository
        self.media_roots = tuple(media_roots or ())
        self.path_resolver = path_resolver
        self.carousel_root = Path(carousel_root or get_data_path("app_center", "carousel")).resolve()

    def create_from_artifact_versions(
        self,
        project_id: str,
        artifact_version_ids: list[str],
        *,
        package_id: str | None = None,
        platform_copy: PlatformCopy | None = None,
        supersedes_package_id: str | None = None,
    ) -> PublishPackageV2:
        if not artifact_version_ids or len(set(artifact_version_ids)) != len(artifact_version_ids):
            raise PublishPackageBuildError("SOURCE_ARTIFACT_VERSION_REQUIRED")
        requested_version_ids = list(artifact_version_ids)
        versions: list[tuple[Artifact, ArtifactVersion]] = []
        seen_version_ids: set[str] = set()
        for version_id in requested_version_ids:
            if version_id in seen_version_ids:
                raise PublishPackageBuildError("SOURCE_ARTIFACT_VERSION_DUPLICATE")
            try:
                version = self.app_repository.get_artifact_version(version_id)
                artifact = self.app_repository.get_artifact(version.artifact_id)
            except Exception as exc:  # repository-specific NotFound is intentionally not leaked
                raise PublishPackageBuildError("SOURCE_ARTIFACT_VERSION_NOT_FOUND") from exc
            if version.project_id != project_id or artifact.project_id != project_id:
                raise PublishPackageBuildError("SOURCE_PROJECT_MISMATCH")
            versions.append((artifact, version))
            seen_version_ids.add(version_id)
            if artifact.artifact_type == "carousel_package":
                page_ids = (version.content or {}).get("page_artifact_version_ids") or []
                if not isinstance(page_ids, list) or not page_ids:
                    raise PublishPackageBuildError("CAROUSEL_PAGE_ARTIFACTS_REQUIRED")
                for page_id in page_ids:
                    if not isinstance(page_id, str) or not page_id.strip() or page_id in seen_version_ids:
                        raise PublishPackageBuildError("CAROUSEL_PAGE_ARTIFACT_INVALID")
                    try:
                        page_version = self.app_repository.get_artifact_version(page_id)
                        page_artifact = self.app_repository.get_artifact(page_version.artifact_id)
                    except Exception as exc:
                        raise PublishPackageBuildError("CAROUSEL_PAGE_ARTIFACT_NOT_FOUND") from exc
                    if page_version.project_id != project_id or page_artifact.project_id != project_id or page_artifact.artifact_type != "carousel_page":
                        raise PublishPackageBuildError("CAROUSEL_PAGE_ARTIFACT_INVALID")
                    versions.append((page_artifact, page_version))
                    seen_version_ids.add(page_id)

        artifact_refs = [
            ArtifactRef(
                artifact_id=artifact.artifact_id,
                artifact_version_id=version.artifact_version_id,
                artifact_type=_normalize_artifact_type(artifact.artifact_type),
                content_fingerprint=version.content_fingerprint,
            )
            for artifact, version in versions
        ]
        has_carousel = any(artifact.artifact_type == "carousel_package" for artifact, _ in versions)
        video_manifest = None if has_carousel else self._manifest_for(versions, "video")
        carousel_manifests = self._carousel_manifests_for(versions) if has_carousel else None
        cover_manifest = self._manifest_for(versions, "cover", required=False) if not has_carousel else None
        artifact_copy = self._copy_from_artifacts(versions)
        if artifact_copy is not None and platform_copy is not None and artifact_copy != platform_copy:
            raise PublishPackageBuildError("PUBLISH_COPY_MISMATCH")
        effective_copy = platform_copy or artifact_copy or self._copy_from_carousel(versions) or PlatformCopy()
        source_version_ids = [version.artifact_version_id for _, version in versions]
        source_artifact_ids = [artifact.artifact_id for artifact, _ in versions]
        source_revision = _fingerprint(
            {
                "project_id": project_id,
                "artifact_version_ids": source_version_ids,
                "content_fingerprints": [version.content_fingerprint for _, version in versions],
            }
        )
        if has_carousel:
            package_fingerprint = _fingerprint(
                {
                    "project_id": project_id,
                    "source": {
                        "kind": "artifact_versions",
                        "artifact_ids": source_artifact_ids,
                        "artifact_version_ids": source_version_ids,
                        "source_revision": source_revision,
                    },
                    "artifact_refs": [item.model_dump(mode="json") for item in artifact_refs],
                    "video_manifest": None,
                    "carousel_manifests": [item.model_dump(mode="json") for item in carousel_manifests or []],
                    "cover_manifest": None,
                    "platform_copy": effective_copy.model_dump(mode="json"),
                    "policy": PublishPolicy().model_dump(mode="json"),
                }
            )
        else:
            package_fingerprint = _canonical_package_fingerprint(
                project_id,
                video_manifest=video_manifest,
                cover_manifest=cover_manifest,
                platform_copy=effective_copy,
        )
        superseded = None
        if supersedes_package_id:
            try:
                superseded = self.core_repository.get_package(supersedes_package_id)
            except Exception as exc:
                raise PublishPackageBuildError("SUPERSEDED_PACKAGE_NOT_FOUND") from exc
            if superseded.project_id != project_id:
                raise PublishPackageBuildError("SUPERSEDED_PACKAGE_PROJECT_MISMATCH")
        package = PublishPackageV2(
            package_id=package_id or f"pkg_{package_fingerprint.removeprefix('sha256:')[:32]}",
            project_id=project_id,
            source=PublishSource(
                kind="artifact_versions",
                artifact_ids=source_artifact_ids,
                artifact_version_ids=source_version_ids,
                source_revision=source_revision,
            ),
            artifact_refs=artifact_refs,
            video_manifest=video_manifest,
            carousel_manifests=carousel_manifests,
            cover_manifest=cover_manifest,
            platform_copy=effective_copy,
            policy=PublishPolicy(),
            package_fingerprint=package_fingerprint,
        )
        created = self.core_repository.create_package(package)
        if created.invalidated_at:
            raise PublishPackageBuildError("PUBLISH_PACKAGE_STALE")
        if superseded:
            invalidation_reason = "CAROUSEL_ARTIFACT_VERSION_REPLACED" if has_carousel else "ARTIFACT_VERSION_REPLACED"
            invalidated = self.core_repository.invalidate_package(superseded.package_id, invalidation_reason)
            self.invalidate_publish_package_ref(invalidated)
        current_versions_by_artifact = dict(zip(source_artifact_ids, source_version_ids, strict=True))
        for prior in self.core_repository.list_packages_for_project(project_id):
            if prior.package_id == created.package_id or prior.invalidated_at:
                continue
            prior_versions_by_artifact = self._package_source_versions(prior, project_id)
            if not prior_versions_by_artifact:
                continue
            shared_artifact_ids = set(current_versions_by_artifact) & set(prior_versions_by_artifact)
            version_changed = any(current_versions_by_artifact[item] != prior_versions_by_artifact[item] for item in shared_artifact_ids)
            same_source_set = set(current_versions_by_artifact) == set(prior_versions_by_artifact)
            canonical_content_changed = same_source_set and prior.package_fingerprint != created.package_fingerprint
            if not version_changed and not canonical_content_changed:
                continue
            invalidation_reason = (
                "CAROUSEL_ARTIFACT_VERSION_REPLACED"
                if has_carousel or bool(prior.carousel_manifests)
                else "ARTIFACT_VERSION_REPLACED"
            )
            invalidated = self.core_repository.invalidate_package(prior.package_id, invalidation_reason)
            self.invalidate_publish_package_ref(invalidated)
        self.ensure_publish_package_ref(created, source_artifact_version_ids=source_version_ids)
        return created

    def create_from_legacy_session(
        self,
        session_id: str,
        *,
        project_id: str,
        video_path: str | Path,
        cover_path: str | Path | None = None,
        platform_copy: PlatformCopy | None = None,
        package_id: str | None = None,
    ) -> PublishPackageV2:
        """Compatibility adapter for V1 sessions; no arbitrary API path flow."""

        if not session_id.strip():
            raise PublishPackageBuildError("LEGACY_SESSION_REQUIRED")
        try:
            video_manifest = preflight_media(video_path, kind="video", roots=self.media_roots or None)
            cover_manifest = preflight_media(cover_path, kind="cover", roots=self.media_roots or None) if cover_path else None
        except MediaPreflightError as exc:
            raise PublishPackageBuildError(exc.code) from exc
        source_revision = _fingerprint({"session_id": session_id, "video": video_manifest.model_dump(mode="json"), "cover": cover_manifest.model_dump(mode="json") if cover_manifest else None})
        package_fingerprint = _canonical_package_fingerprint(
            project_id,
            video_manifest=video_manifest,
            cover_manifest=cover_manifest,
            platform_copy=platform_copy or PlatformCopy(),
        )
        package = PublishPackageV2(
            package_id=package_id or f"pkg_{package_fingerprint.removeprefix('sha256:')[:32]}",
            project_id=project_id,
            source=PublishSource(kind="legacy_session", session_id=session_id, source_revision=source_revision),
            artifact_refs=[
                ArtifactRef(artifact_id=f"legacy_{session_id}", artifact_version_id=f"legacy_{session_id}", artifact_type="video", content_fingerprint=video_manifest.sha256),
                *([ArtifactRef(artifact_id=f"legacy_{session_id}_cover", artifact_version_id=f"legacy_{session_id}_cover", artifact_type="cover", content_fingerprint=cover_manifest.sha256)] if cover_manifest else []),
            ],
            video_manifest=video_manifest,
            cover_manifest=cover_manifest,
            platform_copy=platform_copy or PlatformCopy(),
            policy=PublishPolicy(),
            package_fingerprint=package_fingerprint,
        )
        return self.core_repository.create_package(package)

    def verify_package(self, package: PublishPackageV2) -> None:
        """Re-resolve and re-hash every media file immediately before use."""
        if package.invalidated_at:
            raise PublishPackageBuildError("PUBLISH_PACKAGE_STALE")
        if package.source.kind != "artifact_versions":
            raise PublishPackageBuildError("LEGACY_SESSION_REVERIFY_UNAVAILABLE")
        for reference in package.artifact_refs:
            if reference.artifact_type == "carousel_package":
                try:
                    if not package.carousel_manifests:
                        raise PublishPackageBuildError("CAROUSEL_MANIFEST_REQUIRED")
                    page_versions: list[tuple[Artifact, ArtifactVersion]] = []
                    for page_ref in package.artifact_refs:
                        if page_ref.artifact_type != "carousel_page":
                            continue
                        page_version = self.app_repository.get_artifact_version(page_ref.artifact_version_id)
                        page_artifact = self.app_repository.get_artifact(page_ref.artifact_id)
                        page_versions.append((page_artifact, page_version))
                    page_versions.sort(key=lambda item: int((item[1].content or {}).get("page_index") or 0))
                    for index, manifest in enumerate(package.carousel_manifests):
                        page = next(((artifact, version, item) for artifact, version in page_versions for item in version.file_refs if item.get("sha256") == manifest.sha256), None)
                        if page is None and index < len(page_versions):
                            artifact, version = page_versions[index]
                            file_ref = next((item for item in version.file_refs if item.get("kind") == "image"), None)
                            page = (artifact, version, file_ref) if file_ref else None
                        if not page:
                            raise PublishPackageBuildError("CAROUSEL_FILE_REF_NOT_FOUND")
                        artifact, version, file_ref = page
                        verify_manifest(self._resolve_file_ref(artifact, version, file_ref), manifest, roots=self.media_roots or None)
                except MediaPreflightError as exc:
                    raise PublishPackageBuildError(exc.code) from exc
                continue
            if reference.artifact_type not in {"video", "cover"}:
                continue
            try:
                version = self.app_repository.get_artifact_version(reference.artifact_version_id)
                artifact = self.app_repository.get_artifact(reference.artifact_id)
                path = self._resolve_path(artifact, version, reference.artifact_type)
                manifest = package.video_manifest if reference.artifact_type == "video" else package.cover_manifest
                if manifest is None:
                    raise PublishPackageBuildError("MEDIA_MANIFEST_REQUIRED")
                verify_manifest(path, manifest, roots=self.media_roots or None)
            except MediaPreflightError as exc:
                raise PublishPackageBuildError(exc.code) from exc

    def resolve_media_path(self, package: PublishPackageV2, kind: str) -> Path:
        """Resolve one trusted package asset for an internal platform adapter.

        Absolute paths never cross the HTTP boundary.  They are resolved only
        after the immutable package has been re-verified against its artifact
        version and trusted media roots.
        """

        if kind not in {"video", "cover"}:
            raise PublishPackageBuildError("MEDIA_KIND_UNSUPPORTED")
        if package.source.kind != "artifact_versions":
            raise PublishPackageBuildError("LEGACY_SESSION_REVERIFY_UNAVAILABLE")
        reference = next((item for item in package.artifact_refs if item.artifact_type == kind), None)
        if reference is None:
            raise PublishPackageBuildError(f"{kind.upper()}_ARTIFACT_REQUIRED")
        try:
            version = self.app_repository.get_artifact_version(reference.artifact_version_id)
            artifact = self.app_repository.get_artifact(reference.artifact_id)
        except Exception as exc:
            raise PublishPackageBuildError("SOURCE_ARTIFACT_VERSION_NOT_FOUND") from exc
        path = Path(self._resolve_path(artifact, version, kind)).resolve()
        manifest = package.video_manifest if kind == "video" else package.cover_manifest
        if manifest is None:
            raise PublishPackageBuildError("MEDIA_MANIFEST_REQUIRED")
        try:
            verify_manifest(path, manifest, roots=self.media_roots or None)
        except MediaPreflightError as exc:
            raise PublishPackageBuildError(exc.code) from exc
        return path

    def _manifest_for(
        self,
        versions: list[tuple[Artifact, ArtifactVersion]],
        kind: str,
        *,
        required: bool = True,
    ):
        matches = [(artifact, version) for artifact, version in versions if _normalize_artifact_type(artifact.artifact_type) == kind]
        if len(matches) > 1:
            raise PublishPackageBuildError(f"MULTIPLE_{kind.upper()}_ARTIFACTS")
        if not matches:
            if required:
                raise PublishPackageBuildError(f"{kind.upper()}_ARTIFACT_REQUIRED")
            return None
        artifact, version = matches[0]
        path = self._resolve_path(artifact, version, kind)
        try:
            return preflight_media(path, kind=kind, roots=self.media_roots or None)
        except MediaPreflightError as exc:
            raise PublishPackageBuildError(exc.code) from exc

    def _carousel_manifests_for(self, versions: list[tuple[Artifact, ArtifactVersion]]) -> list:
        pages = [(artifact, version) for artifact, version in versions if artifact.artifact_type == "carousel_page"]
        packages = [(artifact, version) for artifact, version in versions if artifact.artifact_type == "carousel_package"]
        if len(packages) != 1 or not pages:
            raise PublishPackageBuildError("CAROUSEL_PAGE_ARTIFACTS_REQUIRED")
        package_content = packages[0][1].content or {}
        expected_count = package_content.get("page_count")
        pages.sort(key=lambda item: int((item[1].content or {}).get("page_index") or 0))
        indexes = [(item[1].content or {}).get("page_index") for item in pages]
        if expected_count not in {3, 5, 8} or indexes != list(range(1, expected_count + 1)):
            raise PublishPackageBuildError("CAROUSEL_PAGE_SET_INVALID")
        manifests = []
        for artifact, version in pages:
            file_refs = [item for item in version.file_refs if item.get("kind") == "image"]
            if len(file_refs) != 1:
                raise PublishPackageBuildError("CAROUSEL_PAGE_FILE_REQUIRED")
            try:
                manifests.append(preflight_media(self._resolve_file_ref(artifact, version, file_refs[0]), kind="cover", roots=self.media_roots or None))
            except MediaPreflightError as exc:
                raise PublishPackageBuildError(exc.code) from exc
        return manifests

    @staticmethod
    def _copy_from_artifacts(versions: list[tuple[Artifact, ArtifactVersion]]) -> PlatformCopy | None:
        matches = [(artifact, version) for artifact, version in versions if _normalize_artifact_type(artifact.artifact_type) == "publish_copy"]
        if not matches:
            return None
        if len(matches) > 1:
            raise PublishPackageBuildError("MULTIPLE_PUBLISH_COPY_ARTIFACTS")
        _artifact, version = matches[0]
        content = version.content or {}
        if not isinstance(content, dict):
            raise PublishPackageBuildError("ARTIFACT_PUBLISH_COPY_INVALID")
        title_value = content.get("title", "")
        description_value = content.get("description", "")
        hashtags_value = content.get("hashtags", [])
        if not isinstance(title_value, str) or not isinstance(description_value, str) or not isinstance(hashtags_value, list) or not all(isinstance(item, str) for item in hashtags_value):
            raise PublishPackageBuildError("ARTIFACT_PUBLISH_COPY_INVALID")
        normalized_hashtags = [item.strip() for item in hashtags_value]
        if any(not item for item in normalized_hashtags):
            raise PublishPackageBuildError("ARTIFACT_PUBLISH_COPY_INVALID")
        try:
            copy = PlatformCopy(
                title=title_value.strip(),
                description=description_value.strip(),
                hashtags=normalized_hashtags,
            )
        except (TypeError, ValueError) as exc:
            raise PublishPackageBuildError("ARTIFACT_PUBLISH_COPY_INVALID") from exc
        if not copy.title and not copy.description and not copy.hashtags:
            raise PublishPackageBuildError("ARTIFACT_PUBLISH_COPY_INVALID")
        return copy

    @staticmethod
    def _copy_from_carousel(versions: list[tuple[Artifact, ArtifactVersion]]) -> PlatformCopy | None:
        for artifact, version in versions:
            if artifact.artifact_type != "carousel_package":
                continue
            content = version.content or {}
            try:
                return PlatformCopy(title=str(content.get("title") or ""), description=str(content.get("description") or ""), hashtags=[str(item) for item in content.get("hashtags") or []])
            except ValueError as exc:
                raise PublishPackageBuildError("PLATFORM_COPY_INVALID") from exc
        return None

    def _resolve_file_ref(self, artifact: Artifact, version: ArtifactVersion, file_ref: dict[str, Any]) -> str | Path:
        if self.path_resolver:
            path = self.path_resolver(artifact, version, "carousel_page")
        else:
            path = file_ref.get("path") or file_ref.get("local_path") or file_ref.get("relative_path")
            if isinstance(path, str) and not Path(path).is_absolute():
                candidate = self.carousel_root / path
                if candidate.is_file():
                    path = candidate
        if not path:
            raise PublishPackageBuildError("MEDIA_PATH_REQUIRED")
        return path

    def ensure_publish_package_ref(self, package: PublishPackageV2, *, source_artifact_version_ids: list[str] | None = None):
        source_version_ids = list(source_artifact_version_ids or package.source.artifact_version_ids)
        if not source_version_ids:
            return None
        for artifact in self.app_repository.list_artifacts(package.project_id):
            if artifact.artifact_type != "publish_package_ref" or not artifact.current_version_id:
                continue
            version = self.app_repository.get_artifact_version(artifact.current_version_id)
            if (version.content or {}).get("package_id") == package.package_id:
                return version
        artifact = self.app_repository.create_artifact(package.project_id, "publish_package_ref", "发布包引用")
        return self.app_repository.append_artifact_version(
            artifact.artifact_id,
            content={
                "schema_version": 1,
                "artifact_type": "publish_package_ref",
                "package_id": package.package_id,
                "publishing_schema_version": package.schema_version,
                "package_fingerprint": package.package_fingerprint,
                "source_artifact_version_ids": source_version_ids,
                "platform_copy": package.platform_copy.model_dump(mode="json"),
                "invalidated_at": package.invalidated_at,
            },
            source="generated",
        )

    def _package_source_versions(self, package: PublishPackageV2, project_id: str) -> dict[str, str]:
        if package.source.kind == "artifact_versions":
            return dict(zip(package.source.artifact_ids, package.source.artifact_version_ids, strict=True))
        for artifact in self.app_repository.list_artifacts(project_id, include_archived=True):
            if artifact.artifact_type != "publish_package_ref" or not artifact.current_version_id:
                continue
            version = self.app_repository.get_artifact_version(artifact.current_version_id)
            content = version.content or {}
            if content.get("package_id") != package.package_id or content.get("invalidated_at"):
                continue
            mapping: dict[str, str] = {}
            for artifact_version_id in content.get("source_artifact_version_ids") or []:
                try:
                    source_version = self.app_repository.get_artifact_version(artifact_version_id)
                except Exception:
                    continue
                mapping[source_version.artifact_id] = source_version.artifact_version_id
            return mapping
        return {}

    def invalidate_publish_package_ref(self, package: PublishPackageV2):
        """Append an invalidation version to the app-center reference, preserving history."""
        if package.invalidated_at is None:
            return None
        for artifact in self.app_repository.list_artifacts(package.project_id, include_archived=True):
            if artifact.artifact_type != "publish_package_ref" or not artifact.current_version_id:
                continue
            current = self.app_repository.get_artifact_version(artifact.current_version_id)
            content = dict(current.content or {})
            if content.get("package_id") != package.package_id:
                continue
            if content.get("invalidated_at"):
                return current
            content["invalidated_at"] = package.invalidated_at or utc_now()
            content["invalidation_reason"] = package.invalidation_reason or "PACKAGE_INVALIDATED"
            return self.app_repository.append_artifact_version(
                artifact.artifact_id,
                content=content,
                file_refs=current.file_refs,
                source="rendered",
            )
        return None

    def _resolve_path(self, artifact: Artifact, version: ArtifactVersion, kind: str) -> str | Path:
        if self.path_resolver:
            path = self.path_resolver(artifact, version, kind)
        else:
            path = _path_from_file_refs(version.file_refs)
        if not path:
            raise PublishPackageBuildError("MEDIA_PATH_REQUIRED")
        return path


def _path_from_file_refs(file_refs: list[dict[str, Any]]) -> str | Path | None:
    for reference in file_refs:
        for key in ("path", "local_path", "relative_path"):
            value = reference.get(key)
            if isinstance(value, (str, Path)) and str(value).strip():
                return value
    return None


def _normalize_artifact_type(value: str) -> str:
    aliases = {"video_render": "video", "video_output": "video", "image": "cover", "cover_image": "cover"}
    normalized = aliases.get(value, value)
    if normalized not in {"video", "cover", "publish_copy", "carousel_package", "carousel_page"}:
        raise PublishPackageBuildError("ARTIFACT_TYPE_UNSUPPORTED")
    return normalized


def _fingerprint(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _canonical_package_fingerprint(
    project_id: str,
    *,
    video_manifest,
    cover_manifest,
    platform_copy: PlatformCopy,
) -> str:
    """Fingerprint the immutable delivery identity, not its source representation.

    A legacy session and an application-center artifact can describe the same
    media/copy.  Source kind, session IDs, paths and upstream revisions remain
    audit/binding facts, but must not create a second publish package for the
    same final delivery content.
    """

    return _fingerprint(
        {
            "project_id": project_id,
            "publishing_schema_version": 2,
            "video_sha256": video_manifest.sha256 if video_manifest else None,
            "cover_sha256": cover_manifest.sha256 if cover_manifest else None,
            "publish_copy": platform_copy.model_dump(mode="json"),
        }
    )
