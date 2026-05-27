from contextlib import nullcontext

import pytest

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
    def __init__(self, portrait_path, media_type="image"):
        self._portrait_path = portrait_path
        self._media_type = media_type

    def get_portrait_path(self, _portrait_id):
        return str(self._portrait_path)

    def get_portrait_media_type(self, _portrait_id):
        return self._media_type


class FakeDigitalHumanService:
    def __init__(self, output_path):
        self._output_path = output_path
        self.calls = []

    def generate(self, **_kwargs):
        self.calls.append(_kwargs)
        return str(self._output_path)


class FakePixelleVideo:
    pass


def test_portrait_image_preview_html_uses_fixed_height(tmp_path):
    image_path = tmp_path / "portrait.png"
    image_path.write_bytes(b"image")

    html = m4_digital_human._build_portrait_image_html(
        str(image_path),
        label="老板形象",
        height=96,
    )

    assert "height:96px" in html
    assert "object-fit:cover" in html
    assert "data:image/png;base64" in html


def test_portrait_video_preview_html_uses_fixed_height():
    html = m4_digital_human._build_portrait_video_placeholder_html(
        label="闭口视频",
        height=96,
    )

    assert "height:96px" in html
    assert "视频形象" in html
    assert "闭口视频" in html


def test_portrait_card_text_matches_template_card_spacing():
    html = m4_digital_human._build_portrait_card_text_html(
        title="老板形象",
        subtitle="图片形象",
    )

    assert html.count("min-height:20px") >= 2
    assert "padding:8px 2px 2px" in html


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


def test_ai_app_workflow_rejects_video_portrait_before_runninghub_call(monkeypatch, tmp_path):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    audio_path = tmp_path / "voice.mp3"
    portrait_path = tmp_path / "portrait.mp4"
    output_path = tmp_path / "dh.mp4"
    audio_path.write_bytes(b"audio")
    portrait_path.write_bytes(b"video")
    session.update(
        {
            "ipb_m3_audio_path": str(audio_path),
            "ipb_m4_portrait_id": "portrait-1",
            "ipb_m4_workflow": "workflows/runninghub/digital_talk_image_prompt.json",
        }
    )
    errors = []
    notices = []

    monkeypatch.setattr(m4_digital_human.st, "session_state", session)
    monkeypatch.setattr(m4_digital_human.st, "warning", lambda text: errors.append(text))
    monkeypatch.setattr(m4_digital_human.st, "error", lambda text: errors.append(text))
    monkeypatch.setattr(m4_digital_human, "set_step_notice", lambda *args: notices.append(args))
    monkeypatch.setattr(m4_digital_human, "get_temp_path", lambda _name: str(output_path))
    monkeypatch.setattr(
        m4_digital_human,
        "_get_portrait_svc",
        lambda _pixelle_video: FakePortraitService(portrait_path, media_type="video"),
    )
    fake_dh_svc = FakeDigitalHumanService(output_path)
    monkeypatch.setattr(
        m4_digital_human,
        "_get_dh_svc",
        lambda _pixelle_video: fake_dh_svc,
    )

    m4_digital_human._do_generate_video(FakePixelleVideo())

    assert fake_dh_svc.calls == []
    assert session["ipb_step_status"][4] == "error"
    assert any("只支持图片形象" in message for message in errors)
    assert notices[-1][0] == 4


def test_generate_digital_human_error_closes_loading_and_shows_single_step_notice(monkeypatch, tmp_path):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    audio_path = tmp_path / "voice.mp3"
    portrait_path = tmp_path / "portrait.png"
    output_path = tmp_path / "dh.mp4"
    audio_path.write_bytes(b"audio")
    portrait_path.write_bytes(b"image")
    session.update(
        {
            "ipb_m3_audio_path": str(audio_path),
            "ipb_m4_portrait_id": "portrait-1",
        }
    )
    errors = []
    notices = []
    loading_calls = []

    monkeypatch.setattr(m4_digital_human.st, "session_state", session)
    monkeypatch.setattr(m4_digital_human.st, "spinner", lambda _text: nullcontext())
    monkeypatch.setattr(m4_digital_human.st, "warning", lambda _text: None)
    monkeypatch.setattr(m4_digital_human.st, "error", lambda text: errors.append(text))
    class FakeLoading:
        def empty(self):
            loading_calls.append("empty")

    monkeypatch.setattr(m4_digital_human, "show_global_loading", lambda _text: FakeLoading())
    monkeypatch.setattr(m4_digital_human, "set_step_notice", lambda *args: notices.append(args))
    monkeypatch.setattr(m4_digital_human, "get_temp_path", lambda _name: str(output_path))
    monkeypatch.setattr(m4_digital_human, "safe_rerun", lambda: None)
    monkeypatch.setattr(m4_digital_human, "run_async", lambda _coro: (_ for _ in ()).throw(RuntimeError("HTTP 401")))
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

    assert session["ipb_step_status"][4] == "error"
    assert errors == []
    assert notices[-1] == (4, "error", "HTTP 401")
    assert loading_calls == ["empty"]


async def _raise_digital_human_error(**_kwargs):
    raise RuntimeError("digital human failed")


@pytest.mark.asyncio
async def test_run_m4_failure_writes_error_notice_and_preserves_audio(monkeypatch, tmp_path):
    session = AttrDict()
    state.init_ip_broadcast_state(session)
    audio_path = tmp_path / "voice.mp3"
    portrait_path = tmp_path / "portrait.png"
    audio_path.write_bytes(b"audio")
    portrait_path.write_bytes(b"image")
    session.update(
        {
            "ipb_m3_audio_path": str(audio_path),
            "ipb_m4_portrait_id": "portrait-1",
        }
    )
    notices = []

    monkeypatch.setattr(m4_digital_human.st, "session_state", session)
    monkeypatch.setattr(m4_digital_human, "set_step_notice", lambda *args: notices.append(args))
    monkeypatch.setattr(
        m4_digital_human,
        "_get_portrait_svc",
        lambda _pixelle_video: FakePortraitService(portrait_path),
    )

    class FailingDigitalHumanService:
        generate = staticmethod(_raise_digital_human_error)

    monkeypatch.setattr(
        m4_digital_human,
        "_get_dh_svc",
        lambda _pixelle_video: FailingDigitalHumanService(),
    )

    ok = await m4_digital_human.run_m4(FakePixelleVideo())

    assert ok is False
    assert session["ipb_step_status"][4] == "error"
    assert session["ipb_m3_audio_path"] == str(audio_path)
    assert notices[-1] == (4, "error", "digital human failed")
