import asyncio

from web.ip_broadcast import state
from web.ip_broadcast.modules import m3_runner, m3_voice, m4_digital_human


class AttrDict(dict):
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key, value):
        self[key] = value


class FakePixelleVideo:
    def __init__(self, audio_path=None):
        self.audio_path = audio_path
        self.tts_calls = []

    async def tts(self, **kwargs):
        self.tts_calls.append(kwargs)
        return str(self.audio_path)


class FakePortraitService:
    def __init__(self, portrait_path):
        self._portrait_path = portrait_path

    def get_portrait_path(self, _portrait_id):
        return str(self._portrait_path)

    def get_portrait_media_type(self, _portrait_id):
        return "image"


class FakeDigitalHumanService:
    def __init__(self, output_path):
        self.output_path = output_path
        self.calls = []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return str(self.output_path)


def test_overlay_planning_does_not_split_tts_calls(monkeypatch, tmp_path):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    audio_path = tmp_path / "full.mp3"
    audio_path.write_bytes(b"audio")
    state.set_final_script("第一段\n第二段\n第三段", session=session)
    session["ipb_storyboard_enabled"] = True
    session["ipb_overlay_enabled"] = True

    monkeypatch.setattr(m3_runner.st, "session_state", session)
    monkeypatch.setattr(m3_runner, "get_temp_path", lambda _name: str(audio_path))
    fake = FakePixelleVideo(audio_path)

    assert asyncio.run(m3_voice.run_m3(fake)) is True

    assert len(fake.tts_calls) == 1
    assert fake.tts_calls[0]["text"] == "第一段\n第二段\n第三段"
    assert session["ipb_m3_audio_path"] == str(audio_path)


def test_overlay_planning_does_not_split_digital_human_calls(monkeypatch, tmp_path):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    audio_path = tmp_path / "full.mp3"
    portrait_path = tmp_path / "portrait.png"
    output_path = tmp_path / "dh.mp4"
    for path in (audio_path, portrait_path, output_path):
        path.write_bytes(b"ok")
    state.set_final_script("第一段\n第二段\n第三段", session=session)
    session.update(
        {
            "ipb_storyboard_enabled": True,
            "ipb_overlay_enabled": True,
            "ipb_m3_audio_path": str(audio_path),
            "ipb_m4_portrait_id": "portrait-1",
        }
    )

    monkeypatch.setattr(m4_digital_human.st, "session_state", session)
    monkeypatch.setattr(
        m4_digital_human,
        "_get_portrait_svc",
        lambda _pixelle_video: FakePortraitService(portrait_path),
    )
    fake_dh = FakeDigitalHumanService(output_path)
    monkeypatch.setattr(m4_digital_human, "_get_dh_svc", lambda _pixelle_video: fake_dh)
    monkeypatch.setattr(m4_digital_human, "get_temp_path", lambda _name: str(output_path))

    assert asyncio.run(m4_digital_human.run_m4(FakePixelleVideo())) is True

    assert len(fake_dh.calls) == 1
    assert fake_dh.calls[0]["audio_path"] == str(audio_path)
    assert session["ipb_m4_dh_video_path"] == str(output_path)
