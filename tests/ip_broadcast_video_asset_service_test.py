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
