from contextlib import nullcontext

from web.ip_broadcast import state
from web.ip_broadcast.modules import m4_digital_human


class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key, value):
        self[key] = value


class FakePortraitService:
    def __init__(self, portrait_path):
        self._portrait_path = portrait_path

    def get_portrait_path(self, _portrait_id):
        return str(self._portrait_path)

    def get_portrait_media_type(self, _portrait_id):
        return "image"


class FakeDigitalHumanService:
    def __init__(self, output_path):
        self._output_path = output_path
        self.calls = []

    def generate(self, **_kwargs):
        self.calls.append(_kwargs)
        return str(self._output_path)


class FakePixelleVideo:
    pass


def test_generate_digital_human_does_not_render_immediate_duplicate_video(monkeypatch, tmp_path):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    audio_path = tmp_path / "voice.mp3"
    portrait_path = tmp_path / "portrait.png"
    output_path = tmp_path / "dh.mp4"
    audio_path.write_bytes(b"audio")
    portrait_path.write_bytes(b"image")
    output_path.write_bytes(b"video")
    session.update(
        {
            "ipb_m3_audio_path": str(audio_path),
            "ipb_m4_portrait_id": "portrait-1",
        }
    )
    video_calls = []

    monkeypatch.setattr(m4_digital_human.st, "session_state", session)
    monkeypatch.setattr(m4_digital_human.st, "spinner", lambda _text: nullcontext())
    monkeypatch.setattr(m4_digital_human.st, "success", lambda _text: None)
    monkeypatch.setattr(m4_digital_human.st, "warning", lambda _text: None)
    monkeypatch.setattr(m4_digital_human.st, "error", lambda _text: None)
    monkeypatch.setattr(m4_digital_human.st, "video", lambda path: video_calls.append(path))
    def fake_run_async(coro):
        return coro

    monkeypatch.setattr(m4_digital_human, "run_async", fake_run_async)
    monkeypatch.setattr(m4_digital_human, "get_temp_path", lambda _name: str(output_path))
    monkeypatch.setattr(m4_digital_human, "safe_rerun", lambda: None)
    monkeypatch.setattr(
        m4_digital_human,
        "_get_portrait_svc",
        lambda _pixelle_video: FakePortraitService(portrait_path),
    )
    fake_dh_svc = FakeDigitalHumanService(output_path)
    monkeypatch.setattr(
        m4_digital_human,
        "_get_dh_svc",
        lambda _pixelle_video: fake_dh_svc,
    )

    m4_digital_human._do_generate_video(FakePixelleVideo())

    assert session["ipb_m4_dh_video_path"] == str(output_path)
    assert video_calls == []
    assert fake_dh_svc.calls[0]["workflow"] == session["ipb_m4_workflow"]
