from pixelle_video.services.portrait_service import PortraitService
from pixelle_video.services.voice_reference_service import VoiceReferenceService


def test_portrait_service_rejects_invalid_extension(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.portrait_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    svc = PortraitService()

    try:
        svc.save_portrait("bad", b"image", "../png")
    except ValueError as e:
        assert "Invalid file extension" in str(e)
    else:
        raise AssertionError("Expected invalid portrait extension to be rejected")


def test_portrait_service_rejects_oversized_image(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.portrait_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    monkeypatch.setattr("pixelle_video.services.portrait_service.MAX_PORTRAIT_IMAGE_BYTES", 4)
    svc = PortraitService()

    try:
        svc.save_portrait("big", b"image", "png")
    except ValueError as e:
        assert "exceeds size limit" in str(e)
    else:
        raise AssertionError("Expected oversized portrait to be rejected")


def test_voice_reference_service_rejects_oversized_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.voice_reference_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    monkeypatch.setattr("pixelle_video.services.voice_reference_service.MAX_VOICE_REFERENCE_BYTES", 4)
    svc = VoiceReferenceService()

    try:
        svc.save_reference("big", b"audio", "mp3")
    except ValueError as e:
        assert "exceeds size limit" in str(e)
    else:
        raise AssertionError("Expected oversized reference audio to be rejected")


def test_voice_reference_delete_does_not_delete_outside_library(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "pixelle_video.services.voice_reference_service.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    svc = VoiceReferenceService()
    outside = tmp_path / "outside.mp3"
    outside.write_bytes(b"outside")
    manifest = tmp_path / "voice_references" / "voice_references.json"
    manifest.write_text(
        '[{"reference_id":"bad","name":"bad","filename":"../outside.mp3","created_at":"2026-01-01"}]',
        encoding="utf-8",
    )

    assert svc.delete_reference("bad") is True
    assert outside.exists()
