import hashlib
import json
from pathlib import Path

from api.config import api_config
from api.schemas.asset_library_v2 import (
    AssetRevisionContract,
    LibraryItemContract,
    LibraryItemKind,
    ResourceSnapshotContract,
    ResourceStatus,
    UploadSessionContract,
    UploadStatus,
)
from pixelle_video.services.asset_library_baseline import (
    BASELINE_SCHEMA_VERSION,
    backup_manifests,
    collect_baseline,
    restore_manifests,
)


def _write_fixture_data(root: Path) -> None:
    videos = root / "video_assets" / "overlay"
    videos.mkdir(parents=True)
    (videos / "video_assets.json").write_text(
        json.dumps(
            [
                {
                    "asset_id": "video-1",
                    "name": "门店环境",
                    "filename": "video-1.mp4",
                    "thumbnail_filename": "video-1_cover.jpg",
                }
            ]
        ),
        encoding="utf-8",
    )
    (videos / "video-1.mp4").write_bytes(b"fixture-video")
    (videos / "video-1_cover.jpg").write_bytes(b"fixture-poster")

    images = root / "image_assets"
    images.mkdir()
    (images / "image_assets.json").write_text(
        json.dumps(
            [
                {
                    "asset_id": "image-1",
                    "name": "产品主图",
                    "filename": "image-1.webp",
                }
            ]
        ),
        encoding="utf-8",
    )
    (images / "image-1.webp").write_bytes(b"fixture-image")


def test_stage0_contracts_are_strict_and_versionable():
    item = LibraryItemContract(
        resource_id="image-1",
        kind=LibraryItemKind.IMAGE,
        name="产品主图",
        status=ResourceStatus.READY,
        created_at="2026-07-17T00:00:00Z",
        updated_at="2026-07-17T00:00:00Z",
    )
    revision = AssetRevisionContract(
        revision_id="rev-1",
        asset_id="image-1",
        version=1,
        relative_path="image_assets/image-1.webp",
        mime_type="image/webp",
        bytes=13,
        sha256="a" * 64,
        created_at="2026-07-17T00:00:00Z",
    )
    snapshot = ResourceSnapshotContract(
        resource_kind=LibraryItemKind.IMAGE,
        resource_id=item.resource_id,
        revision_id=revision.revision_id,
        sha256=revision.sha256,
    )
    upload = UploadSessionContract(
        upload_id="upload-1",
        filename="image.webp",
        declared_bytes=13,
        received_bytes=13,
        status=UploadStatus.READY,
        target_kind=LibraryItemKind.IMAGE,
    )

    assert item.resource_id == snapshot.resource_id == revision.asset_id
    assert upload.status is UploadStatus.READY


def test_collect_baseline_records_manifest_and_file_checksums(tmp_path):
    _write_fixture_data(tmp_path)

    baseline = collect_baseline(tmp_path)

    assert baseline["schema_version"] == BASELINE_SCHEMA_VERSION
    video = next(item for item in baseline["manifests"] if item["resource_kind"] == "video")
    image = next(item for item in baseline["manifests"] if item["resource_kind"] == "image")
    assert video["record_count"] == 1
    assert video["legacy_ids"] == ["video-1"]
    assert "video_assets/overlay/video-1.mp4" in video["referenced_files"]
    expected_video_sha = hashlib.sha256((tmp_path / "video_assets/overlay/video-1.mp4").read_bytes()).hexdigest()
    assert video["referenced_file_checksums"]["video_assets/overlay/video-1.mp4"] == expected_video_sha
    assert image["record_count"] == 1
    assert baseline["missing_files"] == []
    assert baseline["rollback"]["original_files_untouched"] is True


def test_backup_manifests_is_reversible_and_does_not_modify_sources(tmp_path):
    _write_fixture_data(tmp_path)
    source_manifest = tmp_path / "image_assets" / "image_assets.json"
    before = source_manifest.read_bytes()

    backup_dir = tmp_path / "rollback"
    copied = backup_manifests(tmp_path, backup_dir)

    assert any(item["relative_path"] == "image_assets/image_assets.json" for item in copied)
    assert (backup_dir / "image_assets" / "image_assets.json").read_bytes() == before
    assert source_manifest.read_bytes() == before
    assert (backup_dir / "manifest-backup-index.json").is_file()

    source_manifest.write_text("[]", encoding="utf-8")
    restored = restore_manifests(tmp_path, backup_dir)

    assert "image_assets/image_assets.json" in restored
    assert source_manifest.read_bytes() == before


def test_asset_center_v2_defaults_on_after_gate_c(tmp_path):
    assert api_config.asset_center_v2_enabled is True
