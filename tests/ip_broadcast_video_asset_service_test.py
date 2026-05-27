from pathlib import Path

from pixelle_video.services.video_asset_service import VideoAssetService


def test_save_overlay_video_asset_persists_metadata_and_cover(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.video_asset_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )

    def fake_cover_extractor(video_path: str, output_path: str) -> str:
        assert Path(video_path).exists()
        Path(output_path).write_bytes(b"cover")
        return output_path

    svc = VideoAssetService(cover_extractor=fake_cover_extractor)

    info = svc.save_asset("案例视频", b"video", "mp4")

    assert info.name == "案例视频"
    assert info.filename.endswith(".mp4")
    assert info.size == 5
    assert Path(info.asset_path()).exists()
    assert Path(info.thumbnail_path()).exists()
    assert svc.list_assets()[0].asset_id == info.asset_id


def test_delete_overlay_video_asset_removes_video_and_cover(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.video_asset_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )

    def fake_cover_extractor(_video_path: str, output_path: str) -> str:
        Path(output_path).write_bytes(b"cover")
        return output_path

    svc = VideoAssetService(cover_extractor=fake_cover_extractor)
    info = svc.save_asset("案例视频", b"video", "mp4")

    assert svc.delete_asset(info.asset_id) is True

    assert not Path(info.asset_path()).exists()
    assert not Path(info.thumbnail_path()).exists()
    assert svc.list_assets() == []


def test_save_overlay_video_asset_rejects_path_like_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.video_asset_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    svc = VideoAssetService()

    try:
        svc.save_asset("bad", b"video", "../mp4")
    except ValueError as e:
        assert "Invalid file extension" in str(e)
    else:
        raise AssertionError("Expected invalid extension to be rejected")


def test_save_overlay_video_asset_rejects_oversized_file(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.video_asset_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    monkeypatch.setattr("pixelle_video.services.video_asset_service.MAX_VIDEO_ASSET_BYTES", 4)
    svc = VideoAssetService()

    try:
        svc.save_asset("too-large", b"video", "mp4")
    except ValueError as e:
        assert "exceeds size limit" in str(e)
    else:
        raise AssertionError("Expected oversized video to be rejected")


def test_video_asset_manifest_with_missing_fields_is_compatible(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.video_asset_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    svc = VideoAssetService()
    asset_path = tmp_path / "video_assets" / "overlay" / "legacy.mp4"
    asset_path.write_bytes(b"video")
    manifest = tmp_path / "video_assets" / "overlay" / "video_assets.json"
    manifest.write_text(
        '[{"asset_id":"legacy","name":"旧素材","filename":"legacy.mp4","created_at":"2026-01-01"}]',
        encoding="utf-8",
    )

    assets = svc.list_assets()

    assert len(assets) == 1
    assert assets[0].duration == 0.0
    assert assets[0].size == 0
    assert assets[0].thumbnail_filename == ""


def test_video_asset_corrupt_manifest_returns_empty_list(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.video_asset_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    svc = VideoAssetService()
    manifest = tmp_path / "video_assets" / "overlay" / "video_assets.json"
    manifest.write_text("{bad json", encoding="utf-8")

    assert svc.list_assets() == []


def test_delete_overlay_video_asset_does_not_delete_outside_library(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.video_asset_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    svc = VideoAssetService()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"outside")
    manifest = tmp_path / "video_assets" / "overlay" / "video_assets.json"
    manifest.write_text(
        '[{"asset_id":"bad","name":"bad","filename":"../../outside.mp4","created_at":"2026-01-01"}]',
        encoding="utf-8",
    )

    assert svc.delete_asset("bad") is True
    assert outside.exists()
