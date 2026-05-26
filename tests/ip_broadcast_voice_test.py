from contextlib import nullcontext

from web.ip_broadcast import state
from web.ip_broadcast.modules import m3_voice


class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key, value):
        self[key] = value


class FakePixelleVideo:
    class TTS:
        def __call__(self, **_kwargs):
            return object()

    tts = TTS()


def _session():
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    return session


def test_build_tts_kwargs_for_local_mode(monkeypatch):
    session = _session()
    session.update(
        {
            "ipb_m3_inference_mode": "local",
            "ipb_m3_voice": "zh-CN-XiaoxiaoNeural",
            "ipb_m3_speed": 1.4,
        }
    )
    monkeypatch.setattr(m3_voice.st, "session_state", session)

    kwargs = m3_voice._build_tts_kwargs("正式文案", "/tmp/final.mp3")

    assert kwargs == {
        "text": "正式文案",
        "inference_mode": "local",
        "output_path": "/tmp/final.mp3",
        "voice": "zh-CN-XiaoxiaoNeural",
        "speed": 1.4,
    }


def test_build_tts_kwargs_for_comfyui_mode_with_workflow_and_ref(monkeypatch, tmp_path):
    session = _session()
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"audio")
    session.update(
        {
            "ipb_m3_inference_mode": "comfyui",
            "ipb_m3_tts_workflow": "runninghub/tts_index2.json",
            "ipb_m3_ref_audio_path": str(ref),
        }
    )
    monkeypatch.setattr(m3_voice.st, "session_state", session)

    kwargs = m3_voice._build_tts_kwargs("正式文案", "/tmp/final.mp3")

    assert kwargs == {
        "text": "正式文案",
        "inference_mode": "comfyui",
        "output_path": "/tmp/final.mp3",
        "workflow": "runninghub/tts_index2.json",
        "ref_audio": str(ref),
    }


def test_preview_generation_uses_separate_output_path(monkeypatch, tmp_path):
    session = _session()
    session["ipb_m3_audio_path"] = "/tmp/existing-final.mp3"
    session["ipb_m3_inference_mode"] = "local"
    monkeypatch.setattr(m3_voice.st, "session_state", session)

    output = m3_voice._build_preview_output_path()

    assert output != session["ipb_m3_audio_path"]
    assert output.endswith(".mp3")


def test_generate_voice_does_not_render_immediate_duplicate_audio(monkeypatch, tmp_path):
    session = _session()
    final_audio = tmp_path / "final.mp3"
    final_audio.write_bytes(b"audio")
    session.update(
        {
            "ipb_m2_output": "正式文案",
            "ipb_m3_inference_mode": "local",
        }
    )
    audio_calls = []

    monkeypatch.setattr(m3_voice.st, "session_state", session)
    monkeypatch.setattr(m3_voice.st, "spinner", lambda _text: nullcontext())
    monkeypatch.setattr(m3_voice.st, "success", lambda _text: None)
    monkeypatch.setattr(m3_voice.st, "warning", lambda _text: None)
    monkeypatch.setattr(m3_voice.st, "error", lambda _text: None)
    monkeypatch.setattr(m3_voice.st, "audio", lambda path: audio_calls.append(path))
    monkeypatch.setattr(m3_voice, "run_async", lambda _coro: str(final_audio))
    monkeypatch.setattr(m3_voice, "get_temp_path", lambda _name: str(tmp_path / "target.mp3"))
    monkeypatch.setattr(m3_voice, "safe_rerun", lambda: None)

    m3_voice._do_generate_voice(FakePixelleVideo())

    assert session["ipb_m3_audio_path"] == str(final_audio)
    assert audio_calls == []
