from pixelle_video.services import portrait_service


def test_save_portrait_video_asset_preserves_media_type(monkeypatch, tmp_path):
    monkeypatch.setattr(
        portrait_service,
        "get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    svc = portrait_service.PortraitService()

    info = svc.save_portrait("闭口视频", b"video", "mp4")

    assert info.media_type == "video"
    assert info.asset_path().endswith(".mp4")
    assert info.image_path() == info.asset_path()


def test_legacy_manifest_without_media_type_defaults_to_image(monkeypatch, tmp_path):
    monkeypatch.setattr(
        portrait_service,
        "get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    portraits_dir = tmp_path / "portraits"
    portraits_dir.mkdir(parents=True)
    (portraits_dir / "old.png").write_bytes(b"image")
    (portraits_dir / "portraits.json").write_text(
        '[{"portrait_id": "old", "name": "旧图片", "filename": "old.png", "created_at": "2026-01-01 00:00:00"}]',
        encoding="utf-8",
    )

    [info] = portrait_service.PortraitService().list_portraits()

    assert info.media_type == "image"
