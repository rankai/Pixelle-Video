from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.ip_broadcast import router
from pixelle_video.models.ip_broadcast import HotTopicsResult
from pixelle_video.services.ip_broadcast_workflow import (
    IpBroadcastSessionStore,
    run_ip_broadcast_step,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    return TestClient(app)


def test_create_ip_broadcast_session_returns_default_state():
    client = _client()

    response = client.post("/api/ip-broadcast/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"]
    assert payload["current_step"] == 1
    assert payload["completed_steps"] == 0
    assert payload["next_action"]["key"] == "source"
    assert payload["step_status"]["1"] == "pending"
    assert payload["artifacts"] == {}


def test_update_session_config_moves_ready_state_to_copywriting_step():
    client = _client()
    session_id = client.post("/api/ip-broadcast/sessions").json()["session_id"]

    response = client.patch(
        f"/api/ip-broadcast/sessions/{session_id}/config",
        json={"final_script": "这是一段老板口播文案。"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_step"] == 2
    assert payload["completed_steps"] == 1
    assert payload["next_action"]["key"] == "copywriting"
    assert payload["step_status"]["1"] == "done"
    assert payload["step_status"]["2"] == "ready"


async def test_run_source_step_uses_pasted_text_without_streamlit():
    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "paste",
            "source_text": "粘贴的原始口播文案。",
        },
    )

    result = await run_ip_broadcast_step(
        pixelle_video=None,
        session=session,
        step_key="source",
    )

    assert result is True
    assert session.state["final_script"] == "粘贴的原始口播文案。"
    assert session.step_status[1] == "done"
    assert session.step_status[2] == "ready"
    assert session.next_action()["key"] == "copywriting"


async def test_run_source_step_extracts_script_from_video(monkeypatch):
    class FakeExtractor:
        def __init__(self, api_key, base_url):
            self.api_key = api_key
            self.base_url = base_url

        async def extract(self, text):
            assert text == "https://v.douyin.com/test/"
            return "真实视频口播文案"

    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_workflow.VideoScriptExtractor",
        FakeExtractor,
    )

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "video_extract",
            "source_text": "https://v.douyin.com/test/",
        },
    )

    result = await run_ip_broadcast_step(
        pixelle_video=None,
        session=session,
        step_key="source",
    )

    assert result is True
    assert session.state["final_script"] == "真实视频口播文案"
    assert session.state["source_label"] == "视频提取"
    assert session.state["copywriting_confirmed"] is False


async def test_run_source_step_generates_script_from_industry_persona():
    class FakePixelleVideo:
        async def llm(self, prompt, response_type=None):
            assert "火锅店老板" in prompt
            assert response_type is None
            return "行业人设生成文案"

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "industry_persona",
            "industry_persona": "火锅店老板，十年重庆火锅经验",
            "selling_points": "牛油锅底现炒，鲜切黄牛肉",
            "target_customer": "附近上班族和家庭聚餐",
            "conversion_phrase": "到店报口令打九折",
        },
    )

    result = await run_ip_broadcast_step(
        pixelle_video=FakePixelleVideo(),
        session=session,
        step_key="source",
    )

    assert result is True
    assert session.state["final_script"] == "行业人设生成文案"
    assert session.state["source_label"] == "行业+人设"
    assert session.step_status[2] == "ready"


async def test_run_source_step_learns_ip_profile_and_stores_compact_results(monkeypatch):
    async def fake_fetch_latest(profile_url, limit=5):
        assert profile_url == "https://www.douyin.com/user/test"
        assert limit == 5
        return ["https://www.douyin.com/video/1", "https://www.douyin.com/video/2"]

    async def fake_extract_many(extractor, video_inputs, limit=5):
        assert video_inputs == ["https://www.douyin.com/video/1", "https://www.douyin.com/video/2"]
        return [
            type("Result", (), {"source": video_inputs[0], "script": "第一条口播", "error": "", "ok": True})(),
            type("Result", (), {"source": video_inputs[1], "script": "第二条口播", "error": "", "ok": True})(),
        ]

    class FakeExtractor:
        def __init__(self, api_key, base_url):
            pass

    class FakePixelleVideo:
        async def llm(self, prompt, response_type=None):
            assert "第一条口播" in prompt
            if response_type is HotTopicsResult:
                return HotTopicsResult(topics=["火锅店为什么要现炒锅底", "鲜切黄牛肉怎么选"])
            assert response_type is None
            assert "火锅店为什么要现炒锅底" in prompt
            return "根据学习选题生成的完整口播文案"

    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_workflow.fetch_latest_video_urls_from_profile",
        fake_fetch_latest,
    )
    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_workflow.extract_many_video_scripts",
        fake_extract_many,
    )
    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_workflow.VideoScriptExtractor",
        FakeExtractor,
    )

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "ip_learning",
            "source_text": "https://www.douyin.com/user/test",
        },
    )

    result = await run_ip_broadcast_step(
        pixelle_video=FakePixelleVideo(),
        session=session,
        step_key="source",
    )

    assert result is True
    assert session.state["ip_learning_summary"] == "已提取 2 条，失败 0 条"
    assert session.state["ip_learning_topics"] == ["火锅店为什么要现炒锅底", "鲜切黄牛肉怎么选"]
    assert session.state["final_script"] == "根据学习选题生成的完整口播文案"
    assert session.state["source_label"] == "IP学习"


async def test_run_voice_step_passes_runninghub_index_workflow_params():
    class FakePixelleVideo:
        def __init__(self):
            self.tts_kwargs = None

        async def tts(self, **kwargs):
            self.tts_kwargs = kwargs
            return "/tmp/ipb-index.mp3"

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "final_script": "测试声音克隆文案",
            "copywriting_confirmed": True,
            "tts_inference_mode": "comfyui",
            "tts_workflow": "runninghub/tts_index_custom.json",
            "tts_ref_audio_path": "/tmp/ref.wav",
            "tts_index_mode": "Auto",
            "tts_index_do_sample_mode": "off",
            "tts_temperature": 0.7,
            "tts_top_p": 0.85,
            "tts_top_k": 40,
            "tts_num_beams": 4,
            "tts_repetition_penalty": 8.5,
            "tts_length_penalty": 0.2,
            "tts_max_mel_tokens": 1600,
            "tts_max_tokens_per_sentence": 90,
            "tts_seed": 123,
        },
    )
    fake = FakePixelleVideo()

    result = await run_ip_broadcast_step(fake, session, "voice")

    assert result is True
    assert fake.tts_kwargs == {
        "text": "测试声音克隆文案",
        "inference_mode": "comfyui",
        "output_path": fake.tts_kwargs["output_path"],
        "workflow": "runninghub/tts_index_custom.json",
        "ref_audio": "/tmp/ref.wav",
        "mode": "Auto",
        "do_sample_mode": "off",
        "temperature": 0.7,
        "top_p": 0.85,
        "top_k": 40,
        "num_beams": 4,
        "repetition_penalty": 8.5,
        "length_penalty": 0.2,
        "max_mel_tokens": 1600,
        "max_tokens_per_sentence": 90,
        "seed": 123,
    }


async def test_run_voice_step_passes_runninghub_spark_workflow_params():
    class FakePixelleVideo:
        def __init__(self):
            self.tts_kwargs = None

        async def tts(self, **kwargs):
            self.tts_kwargs = kwargs
            return "/tmp/ipb-spark.mp3"

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "final_script": "测试 Spark 文案",
            "copywriting_confirmed": True,
            "tts_inference_mode": "comfyui",
            "tts_workflow": "runninghub/tts_spark.json",
            "tts_spark_gender": "female",
            "tts_spark_speed": "high",
            "tts_spark_pitch": "low",
            "tts_temperature": 0.6,
            "tts_top_p": 0.8,
            "tts_top_k": 25,
            "tts_max_new_tokens": 2400,
            "tts_do_sample": False,
        },
    )
    fake = FakePixelleVideo()

    result = await run_ip_broadcast_step(fake, session, "voice")

    assert result is True
    assert fake.tts_kwargs["workflow"] == "runninghub/tts_spark.json"
    assert fake.tts_kwargs["gender"] == "female"
    assert fake.tts_kwargs["speed"] == "high"
    assert fake.tts_kwargs["pitch"] == "low"
    assert fake.tts_kwargs["temperature"] == 0.6
    assert fake.tts_kwargs["top_p"] == 0.8
    assert fake.tts_kwargs["top_k"] == 25
    assert fake.tts_kwargs["max_new_tokens"] == 2400
    assert fake.tts_kwargs["do_sample"] is False


def test_artifact_download_rejects_unknown_artifact():
    client = _client()
    session_id = client.post("/api/ip-broadcast/sessions").json()["session_id"]

    response = client.get(f"/api/ip-broadcast/sessions/{session_id}/artifacts/not-found")

    assert response.status_code == 404
