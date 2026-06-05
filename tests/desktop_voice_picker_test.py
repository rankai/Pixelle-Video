from pathlib import Path

APP_SOURCE = Path("desktop/src/App.tsx").read_text()
API_SOURCE = Path("desktop/src/api.ts").read_text()


def _function_source(name: str) -> str:
    marker = f"function {name}("
    start = APP_SOURCE.index(marker)
    next_function = APP_SOURCE.find("\nfunction ", start + len(marker))
    return APP_SOURCE[start:] if next_function == -1 else APP_SOURCE[start:next_function]


def test_system_voice_picker_requires_confirmation_before_patching():
    source = _function_source("SystemVoicePickerModal")

    assert "pendingVoice" in source
    assert "pendingSpeed" in source
    assert "confirmSelection" in source
    assert "确认使用" in source
    assert "onClick={() => setPendingVoice(voice.value)}" in source
    assert "onClick={confirmSelection}" in source


def test_system_voice_picker_can_preview_selected_voice():
    source = _function_source("SystemVoicePickerModal")

    assert "previewVoice" in source
    assert "synthesizeTtsPreview" in API_SOURCE
    assert "试听音色" in source
    assert "ProtectedMedia kind=\"audio\"" in source
    assert "previewError" in source


def test_voice_asset_upload_modal_mentions_audio_should_be_under_30_seconds():
    source = _function_source("VoiceAssetModal")

    assert "建议上传 30 秒以内" in source
    assert "背景安静" in source
    assert "说话清晰" in APP_SOURCE
