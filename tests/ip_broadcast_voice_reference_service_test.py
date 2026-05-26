from pixelle_video.services import voice_reference_service


def test_save_voice_reference_audio_persists_manifest(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_reference_service, "get_data_path", lambda *parts: str(tmp_path.joinpath(*parts)))

    svc = voice_reference_service.VoiceReferenceService()
    info = svc.save_reference("老板原声", b"audio", "wav")

    assert info.name == "老板原声"
    assert info.filename.endswith(".wav")
    assert info.exists()

    [loaded] = voice_reference_service.VoiceReferenceService().list_references()
    assert loaded.reference_id == info.reference_id
    assert loaded.name == "老板原声"


def test_save_voice_reference_rejects_unsupported_extensions(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_reference_service, "get_data_path", lambda *parts: str(tmp_path.joinpath(*parts)))

    svc = voice_reference_service.VoiceReferenceService()

    try:
        svc.save_reference("bad", b"text", "txt")
    except ValueError as exc:
        assert "Unsupported voice reference extension" in str(exc)
    else:
        raise AssertionError("unsupported extension should raise")
