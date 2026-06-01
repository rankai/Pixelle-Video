import inspect
from contextlib import nullcontext
from pathlib import Path

import pytest

from pixelle_video.services.tts_service import TTSService
from web.ip_broadcast import state
from web.ip_broadcast.modules import m3_runner, m3_tts_config, m3_voice, m3_voice_references


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


def test_render_m3_places_generate_button_after_configuration():
    source = inspect.getsource(m3_voice.render_m3_voice)

    assert source.index("_render_voice_preview(pixelle_video)") < source.index('"生成语音"')


def test_build_tts_kwargs_for_local_mode(monkeypatch):
    session = _session()
    session.update(
        {
            "ipb_m3_inference_mode": "local",
            "ipb_m3_voice": "zh-CN-XiaoxiaoNeural",
            "ipb_m3_speed": 1.4,
            "ipb_m3_pitch": 8,
            "ipb_m3_volume": 15,
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
        "pitch": 8,
        "volume": 15,
    }


def test_build_tts_kwargs_for_comfyui_index_mode_with_workflow_ref_and_sampling(monkeypatch, tmp_path):
    session = _session()
    ref = tmp_path / "ref.wav"
    ref.write_bytes(b"audio")
    session.update(
        {
            "ipb_m3_inference_mode": "comfyui",
            "ipb_m3_tts_workflow": "runninghub/tts_index2.json",
            "ipb_m3_ref_audio_path": str(ref),
            "ipb_m3_index_mode": "Auto",
            "ipb_m3_index_do_sample_mode": "on",
            "ipb_m3_temperature": 0.7,
            "ipb_m3_top_p": 0.85,
            "ipb_m3_top_k": 25,
            "ipb_m3_num_beams": 4,
            "ipb_m3_repetition_penalty": 8.5,
            "ipb_m3_length_penalty": 0.2,
            "ipb_m3_max_mel_tokens": 1600,
            "ipb_m3_max_tokens_per_sentence": 100,
            "ipb_m3_seed": 12345,
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
        "mode": "Auto",
        "do_sample_mode": "on",
        "temperature": 0.7,
        "top_p": 0.85,
        "top_k": 25,
        "num_beams": 4,
        "repetition_penalty": 8.5,
        "length_penalty": 0.2,
        "max_mel_tokens": 1600,
        "max_tokens_per_sentence": 100,
        "seed": 12345,
    }


def test_build_tts_kwargs_for_comfyui_edge_mode(monkeypatch):
    session = _session()
    session.update(
        {
            "ipb_m3_inference_mode": "comfyui",
            "ipb_m3_tts_workflow": "runninghub/tts_edge.json",
            "ipb_m3_workflow_voice": "[Chinese] zh-CN Xiaoxiao",
            "ipb_m3_workflow_speed": 1.3,
            "ipb_m3_workflow_pitch": 6,
        }
    )
    monkeypatch.setattr(m3_voice.st, "session_state", session)

    kwargs = m3_voice._build_tts_kwargs("正式文案", "/tmp/final.mp3")

    assert kwargs == {
        "text": "正式文案",
        "inference_mode": "comfyui",
        "output_path": "/tmp/final.mp3",
        "workflow": "runninghub/tts_edge.json",
        "voice": "[Chinese] zh-CN Xiaoxiao",
        "speed": 1.3,
        "pitch": 6,
    }


def test_build_tts_kwargs_for_comfyui_spark_mode(monkeypatch):
    session = _session()
    session.update(
        {
            "ipb_m3_inference_mode": "comfyui",
            "ipb_m3_tts_workflow": "runninghub/tts_spark.json",
            "ipb_m3_spark_gender": "female",
            "ipb_m3_spark_speed": "high",
            "ipb_m3_spark_pitch": "moderate",
            "ipb_m3_temperature": 0.65,
            "ipb_m3_top_k": 40,
            "ipb_m3_top_p": 0.92,
            "ipb_m3_max_new_tokens": 2200,
            "ipb_m3_do_sample": False,
            "ipb_m3_seed": 67890,
        }
    )
    monkeypatch.setattr(m3_voice.st, "session_state", session)

    kwargs = m3_voice._build_tts_kwargs("正式文案", "/tmp/final.mp3")

    assert kwargs == {
        "text": "正式文案",
        "inference_mode": "comfyui",
        "output_path": "/tmp/final.mp3",
        "workflow": "runninghub/tts_spark.json",
        "gender": "female",
        "speed": "high",
        "pitch": "moderate",
        "temperature": 0.65,
        "top_k": 40,
        "top_p": 0.92,
        "max_new_tokens": 2200,
        "do_sample": False,
        "seed": 67890,
    }


def test_reference_audio_notice_explains_non_clone_workflows():
    assert m3_tts_config.reference_audio_notice("runninghub/tts_edge.json") == (
        "当前 Edge TTS 工作流不使用参考音频；如需克隆声音，请切换到 Index 声音克隆工作流。"
    )
    assert m3_tts_config.reference_audio_notice("runninghub/tts_spark.json") == (
        "当前 Spark TTS 工作流按性别、语速、音调生成声音，不读取参考音频。"
    )
    assert m3_tts_config.reference_audio_notice("runninghub/tts_index2.json") == ""


@pytest.mark.asyncio
async def test_tts_service_passes_local_pitch_and_volume_to_edge_tts(monkeypatch, tmp_path):
    calls = []

    async def fake_edge_tts(**kwargs):
        calls.append(kwargs)
        return b"audio"

    monkeypatch.setattr("pixelle_video.services.tts_service.edge_tts", fake_edge_tts)
    output_path = tmp_path / "voice.mp3"
    service = TTSService({"comfyui": {"tts": {"inference_mode": "local", "local": {}}}})

    result = await service(
        text="正式文案",
        inference_mode="local",
        voice="zh-CN-XiaoxiaoNeural",
        speed=1.2,
        pitch=8,
        volume=15,
        output_path=str(output_path),
    )

    assert result == str(output_path)
    assert calls[0]["rate"] == "+19%"
    assert calls[0]["pitch"] == "+8Hz"
    assert calls[0]["volume"] == "+15%"


def test_select_reference_audio_sets_tts_reference_path(monkeypatch, tmp_path):
    session = _session()
    ref = tmp_path / "saved.wav"
    ref.write_bytes(b"audio")
    session["ipb_m3_ref_audio_id"] = "ref-1"
    monkeypatch.setattr(m3_voice.st, "session_state", session)

    m3_voice._set_selected_reference_audio_path({"ref-1": str(ref)})

    assert session["ipb_m3_ref_audio_path"] == str(ref)


def test_clear_recorded_reference_audio_removes_widget_state(monkeypatch):
    session = _session()
    session["ipb_m3_ref_audio_recorder"] = object()
    rerun_called = []
    monkeypatch.setattr(m3_voice_references.st, "session_state", session)
    monkeypatch.setattr(m3_voice_references, "safe_rerun", lambda: rerun_called.append(True))

    m3_voice._clear_recorded_reference_audio()

    assert "ipb_m3_ref_audio_recorder" not in session
    assert rerun_called == [True]


def test_apply_reference_audio_form_reset_selects_saved_reference_and_clears_inputs(monkeypatch):
    session = _session()
    session.update(
        {
            "_ipb_m3_ref_audio_saved_id": "ref-new",
            "ipb_m3_ref_audio_id": "ref-old",
            "ipb_m3_ref_audio_select": "ref-old",
            "ipb_m3_new_ref_audio_name": "老板原声",
            "ipb_m3_ref_audio_uploader_nonce": 2,
            "ipb_m3_ref_audio_recorder": object(),
        }
    )
    monkeypatch.setattr(m3_voice.st, "session_state", session)

    m3_voice._apply_reference_audio_form_reset()

    assert session["ipb_m3_ref_audio_id"] == "ref-new"
    assert session["ipb_m3_ref_audio_select"] == "ref-new"
    assert session["ipb_m3_new_ref_audio_name"] == ""
    assert session["ipb_m3_ref_audio_uploader_nonce"] == 3
    assert "ipb_m3_ref_audio_recorder" not in session
    assert "_ipb_m3_ref_audio_saved_id" not in session


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

    monkeypatch.setattr(m3_runner.st, "session_state", session)
    monkeypatch.setattr(m3_runner.st, "spinner", lambda _text: nullcontext())
    monkeypatch.setattr(m3_runner.st, "success", lambda _text: None)
    monkeypatch.setattr(m3_runner.st, "warning", lambda _text: None)
    monkeypatch.setattr(m3_runner.st, "error", lambda _text: None)
    monkeypatch.setattr(m3_voice.st, "audio", lambda path: audio_calls.append(path))
    monkeypatch.setattr(m3_runner, "run_async", lambda _coro: str(final_audio))
    monkeypatch.setattr(m3_runner, "get_temp_path", lambda _name: str(tmp_path / "target.mp3"))
    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_cache.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    monkeypatch.setattr(m3_runner, "safe_rerun", lambda: None)

    m3_voice._do_generate_voice(FakePixelleVideo())

    assert Path(session["ipb_m3_audio_path"]).read_bytes() == b"audio"
    assert audio_calls == []


@pytest.mark.asyncio
async def test_run_m3_failure_writes_error_notice_and_preserves_script(monkeypatch, tmp_path):
    session = _session()
    session["ipb_m2_output"] = "正式文案"
    notices = []
    monkeypatch.setattr(m3_runner.st, "session_state", session)
    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_cache.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    monkeypatch.setattr(m3_runner, "set_step_notice", lambda *args: notices.append(args))

    class FailingPixelleVideo:
        async def tts(self, **_kwargs):
            raise RuntimeError("TTS failed")

    ok = await m3_voice.run_m3(FailingPixelleVideo())

    assert ok is False
    assert session["ipb_step_status"][3] == "error"
    assert session["ipb_m2_output"] == "正式文案"
    assert notices[-1] == (3, "error", "TTS failed")


@pytest.mark.asyncio
async def test_run_m3_reuses_tts_cache_for_same_inputs(monkeypatch, tmp_path):
    session = _session()
    session["ipb_m2_output"] = "正式文案"
    session["ipb_m3_inference_mode"] = "local"
    source_audio = tmp_path / "generated.mp3"
    source_audio.write_bytes(b"audio")
    calls = []
    notices = []

    monkeypatch.setattr(m3_runner.st, "session_state", session)
    monkeypatch.setattr(m3_runner, "get_temp_path", lambda _name: str(tmp_path / _name))
    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_cache.get_data_path",
        lambda *parts: str(tmp_path.joinpath(*parts)),
    )
    monkeypatch.setattr(m3_runner, "set_step_notice", lambda *args: notices.append(args))

    class FakePixelleVideo:
        async def tts(self, **_kwargs):
            calls.append(_kwargs)
            return str(source_audio)

    assert await m3_runner.run_m3(FakePixelleVideo()) is True
    first_cached_path = session["ipb_m3_audio_path"]
    session["ipb_m3_audio_path"] = ""

    assert await m3_runner.run_m3(FakePixelleVideo()) is True

    assert len(calls) == 1
    assert session["ipb_m3_audio_path"] == first_cached_path
    assert notices[-1] == (3, "success", "已复用上次生成结果")
