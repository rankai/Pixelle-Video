from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.ip_broadcast import _session_store, router
from pixelle_video.models.ip_broadcast import HotTopicsResult
from pixelle_video.prompts.ip_broadcast import build_rewrite_prompt
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


def test_rewrite_prompt_requires_local_business_owner_voice_and_segments():
    prompt = build_rewrite_prompt(
        source_text="原文",
        style_prompt="自然口播",
        word_count=220,
        business_goal="团购转化",
        script_structure=["优惠钩子", "套餐内容", "适合人群", "下单引导"],
        intent_note="99元双人火锅套餐",
    )

    assert "本地生活" in prompt
    assert "老板" in prompt
    assert "3-6" in prompt
    assert "不要添加小标题" in prompt
    assert "不要夸大" in prompt
    assert "行动指引" in prompt


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


async def test_industry_persona_prompt_uses_business_goal_structure():
    class FakePixelleVideo:
        def __init__(self):
            self.prompt = ""

        async def llm(self, prompt, response_type=None):
            self.prompt = prompt
            assert response_type is None
            return "团购转化生成文案"

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "industry_persona",
            "industry_persona": "重庆火锅店老板",
            "selling_points": "双人牛油火锅套餐 99 元",
            "business_goal_name": "团购转化",
            "business_script_structure": ["优惠钩子", "套餐内容", "适合人群", "下单引导"],
            "business_intent_note": "99元双人火锅套餐，下班两个人来吃很划算",
            "word_count": 150,
            "style_prompt": "强转化、节奏快、信息清楚",
        },
    )
    fake = FakePixelleVideo()

    result = await run_ip_broadcast_step(fake, session, "source")

    assert result is True
    assert "团购转化" in fake.prompt
    assert "优惠钩子 → 套餐内容 → 适合人群 → 下单引导" in fake.prompt
    assert "约150字" in fake.prompt
    assert "强转化、节奏快、信息清楚" in fake.prompt
    assert "99元双人火锅套餐，下班两个人来吃很划算" in fake.prompt


async def test_industry_persona_prompt_does_not_duplicate_legacy_type_when_goal_is_set():
    class FakePixelleVideo:
        def __init__(self):
            self.prompt = ""

        async def llm(self, prompt, response_type=None):
            self.prompt = prompt
            assert response_type is None
            return "门店探店生成文案"

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "industry_persona",
            "industry_persona": "火锅店老板",
            "selling_points": "牛油锅底、鲜切牛肉",
            "video_type": "种草带货",
            "copy_type": "促销转化型",
            "business_goal_name": "门店探店",
            "business_script_structure": ["场景引入", "核心卖点", "体验细节", "到店引导"],
        },
    )
    fake = FakePixelleVideo()

    result = await run_ip_broadcast_step(fake, session, "source")

    assert result is True
    assert "本条视频目标：门店探店" in fake.prompt
    assert "视频类型：种草带货" not in fake.prompt
    assert "文案风格：促销转化型" not in fake.prompt
    assert "不要添加小标题" in fake.prompt


async def test_copywriting_prompt_uses_business_goal_structure():
    class FakePixelleVideo:
        def __init__(self):
            self.prompt = ""

        async def llm(self, prompt, response_type=None):
            self.prompt = prompt
            assert response_type is None
            return "改写后的门店探店口播"

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "final_script": "这是一段原始探店口播。",
            "business_goal_name": "门店探店",
            "business_script_structure": ["场景引入", "核心卖点", "体验细节", "到店引导"],
            "business_intent_note": "重点讲下班后两个人到店吃很方便",
            "style_prompt": "像朋友推荐门店",
            "word_count": 180,
        },
    )
    fake = FakePixelleVideo()

    result = await run_ip_broadcast_step(fake, session, "copywriting")

    assert result is True
    assert "门店探店" in fake.prompt
    assert "场景引入 → 核心卖点 → 体验细节 → 到店引导" in fake.prompt
    assert "重点讲下班后两个人到店吃很方便" in fake.prompt
    assert "不要添加小标题" in fake.prompt
    assert session.state["copywriting_confirmed"] is True


async def test_copywriting_normalizes_long_output_into_paragraphs():
    class FakePixelleVideo:
        async def llm(self, prompt, response_type=None):
            assert response_type is None
            return (
                "你是不是也觉得下班后吃顿热乎火锅很麻烦。我们店把双人牛油套餐做到了99元。"
                "锅底每天现炒，黄牛肉当天鲜切。两个人来不用纠结点什么，按这个套餐就够吃。"
                "到店报口令还能送一份小吃，附近上班的朋友今天就可以来试试。"
            )

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "final_script": "火锅店双人套餐文案。",
            "business_script_structure": ["痛点开场", "套餐卖点", "到店引导"],
        },
    )

    result = await run_ip_broadcast_step(FakePixelleVideo(), session, "copywriting")

    assert result is True
    assert session.state["final_script"].count("\n") >= 2
    assert len([line for line in session.state["final_script"].splitlines() if line.strip()]) >= 3


async def test_copywriting_keeps_paragraphs_when_model_returns_short_single_block():
    class FakePixelleVideo:
        async def llm(self, prompt, response_type=None):
            assert response_type is None
            return "很多老板做短视频最大的问题是只讲产品不讲场景，顾客听完不知道为什么现在要来店里，正确做法是先讲痛点再讲套餐最后给到店理由"

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "final_script": "第一段原文。\n第二段原文。\n第三段原文。",
            "business_script_structure": ["痛点", "方案", "到店理由"],
        },
    )

    result = await run_ip_broadcast_step(FakePixelleVideo(), session, "copywriting")

    assert result is True
    assert len([line for line in session.state["final_script"].splitlines() if line.strip()]) == 3


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
    assert session.state["ip_learning_selected_topic"] == ""
    assert session.state["ip_learning_requires_topic_confirmation"] is True
    assert session.state["final_script"] == ""
    assert session.next_action()["key"] == "source"
    assert session.next_action()["label"] == "确认学习选题"
    assert session.step_status[1] == "ready"
    assert session.step_status[2] == "pending"
    assert session.notices[1]["kind"] == "info"
    assert session.notices[1]["message"] == "已生成候选选题，请先确认一个选题再生成口播文案。"


async def test_run_source_step_generates_script_after_ip_topic_confirmation(monkeypatch):
    async def fake_fetch_latest(profile_url, limit=5):
        raise AssertionError("confirmed topic should reuse extracted scripts")

    async def fake_extract_many(extractor, video_inputs, limit=5):
        raise AssertionError("confirmed topic should reuse extracted scripts")

    class FakePixelleVideo:
        async def llm(self, prompt, response_type=None):
            assert response_type is None
            assert "鲜切黄牛肉怎么选" in prompt
            assert "第一条口播" in prompt
            return "根据第二个学习选题生成的完整口播文案"

    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_workflow.fetch_latest_video_urls_from_profile",
        fake_fetch_latest,
    )
    monkeypatch.setattr(
        "pixelle_video.services.ip_broadcast_workflow.extract_many_video_scripts",
        fake_extract_many,
    )

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "ip_learning",
            "ip_learning_scripts": [{"source": "https://www.douyin.com/video/1", "script": "第一条口播"}],
            "ip_learning_topics": ["火锅店为什么要现炒锅底", "鲜切黄牛肉怎么选"],
            "ip_learning_selected_topic": "鲜切黄牛肉怎么选",
            "ip_learning_requires_topic_confirmation": True,
        },
    )

    result = await run_ip_broadcast_step(
        pixelle_video=FakePixelleVideo(),
        session=session,
        step_key="source",
    )

    assert result is True
    assert session.state["ip_learning_requires_topic_confirmation"] is False
    assert session.state["final_script"] == "根据第二个学习选题生成的完整口播文案"
    assert session.state["source_text"] == "根据第二个学习选题生成的完整口播文案"
    assert session.state["source_label"] == "IP学习"
    assert session.state["copywriting_confirmed"] is False


def _seed_ip_learning_outputs(session):
    session.update_config(
        {
            "source_mode": "ip_learning",
            "ip_profile_url": "https://www.douyin.com/user/old",
            "ip_manual_video_links": "https://www.douyin.com/video/old",
            "ip_learning_video_urls": ["https://www.douyin.com/video/old"],
            "ip_learning_scripts": [{"source": "old", "script": "old script"}],
            "ip_learning_errors": [{"source": "bad", "error": "failed"}],
            "ip_learning_topics": ["旧选题"],
            "ip_learning_selected_topic": "旧选题",
            "ip_learning_summary": "已提取 1 条，失败 1 条",
            "ip_learning_requires_topic_confirmation": True,
            "source_text": "旧的口播文案",
            "source_label": "IP学习",
            "final_script": "旧的口播文案",
            "copywriting_confirmed": True,
            "audio_path": "/tmp/old-audio.mp3",
            "digital_human_video_path": "/tmp/old-human.mp4",
            "final_video_path": "/tmp/old-final.mp4",
            "cover_path": "/tmp/old-cover.png",
            "publish_package": {"title": "旧发布包"},
            "platform_suggestions": {"douyin": {"title": "旧建议"}},
        }
    )


def _assert_ip_learning_outputs_cleared(session, *, source_text=""):
    assert session.state["ip_learning_video_urls"] == []
    assert session.state["ip_learning_scripts"] == []
    assert session.state["ip_learning_errors"] == []
    assert session.state["ip_learning_topics"] == []
    assert session.state["ip_learning_selected_topic"] == ""
    assert session.state["ip_learning_summary"] == ""
    assert session.state["ip_learning_requires_topic_confirmation"] is False
    assert session.state["source_text"] == source_text
    assert session.state["source_label"] == ""
    assert session.state["final_script"] == ""
    assert session.state["copywriting_confirmed"] is False
    assert session.state["audio_path"] == ""
    assert session.state["digital_human_video_path"] == ""
    assert session.state["final_video_path"] == ""
    assert session.state["cover_path"] == ""
    assert session.state["publish_package"] == {}
    assert session.state["platform_suggestions"] == {}


def test_ip_learning_profile_url_change_clears_cache_script_and_outputs():
    session = IpBroadcastSessionStore().create_session()
    _seed_ip_learning_outputs(session)

    session.update_config({"ip_profile_url": "https://www.douyin.com/user/new"})

    _assert_ip_learning_outputs_cleared(session)


@pytest.mark.asyncio
async def test_run_source_step_waiting_for_ip_topic_clears_stale_script():
    class FakePixelleVideo:
        async def llm(self, prompt, response_type=None):
            raise AssertionError("waiting for topic confirmation should not call LLM")

    store = IpBroadcastSessionStore()
    session = store.create_session()
    store.update_config(
        session.session_id,
        {
            "source_mode": "ip_learning",
            "ip_learning_scripts": [{"source": "https://www.douyin.com/video/1", "script": "第一条口播"}],
            "ip_learning_topics": ["火锅店为什么要现炒锅底", "鲜切黄牛肉怎么选"],
            "ip_learning_selected_topic": "",
            "ip_learning_requires_topic_confirmation": False,
            "final_script": "旧的口播文案",
            "source_text": "旧的口播文案",
            "source_label": "IP学习",
        },
    )

    result = await run_ip_broadcast_step(
        pixelle_video=FakePixelleVideo(),
        session=session,
        step_key="source",
    )

    assert result is True
    assert session.state["ip_learning_requires_topic_confirmation"] is True
    assert session.state["final_script"] == ""
    assert session.state["source_text"] == ""
    assert session.state["source_label"] == ""
    assert session.state["copywriting_confirmed"] is False
    assert session.next_action()["key"] == "source"


def test_ip_learning_source_mode_change_clears_cache_script_and_outputs():
    session = IpBroadcastSessionStore().create_session()
    _seed_ip_learning_outputs(session)

    session.update_config({"source_mode": "paste"})

    _assert_ip_learning_outputs_cleared(session)


def test_ip_learning_manual_video_links_change_clears_cache_script_and_outputs():
    session = IpBroadcastSessionStore().create_session()
    _seed_ip_learning_outputs(session)

    session.update_config({"ip_manual_video_links": "https://www.douyin.com/video/new"})

    _assert_ip_learning_outputs_cleared(session)


def test_ip_learning_source_text_fallback_change_clears_cache_script_and_outputs():
    session = IpBroadcastSessionStore().create_session()
    _seed_ip_learning_outputs(session)

    session.update_config({"source_text": "https://www.douyin.com/user/new"})

    _assert_ip_learning_outputs_cleared(
        session,
        source_text="https://www.douyin.com/user/new",
    )
    assert session.next_action()["key"] == "source"


def test_ip_learning_unrelated_config_keeps_cached_topics():
    session = IpBroadcastSessionStore().create_session()
    session.update_config(
        {
            "source_mode": "ip_learning",
            "ip_profile_url": "https://www.douyin.com/user/demo",
            "ip_learning_video_urls": ["https://www.douyin.com/video/old"],
            "ip_learning_scripts": [{"source": "old", "script": "old script"}],
            "ip_learning_errors": [{"source": "bad", "error": "failed"}],
            "ip_learning_topics": ["保留选题"],
            "ip_learning_selected_topic": "保留选题",
            "ip_learning_summary": "已提取 1 条，失败 1 条",
            "ip_learning_requires_topic_confirmation": True,
        }
    )

    session.update_config({"tts_speed": 1.15})

    assert session.state["ip_learning_video_urls"] == ["https://www.douyin.com/video/old"]
    assert session.state["ip_learning_scripts"] == [{"source": "old", "script": "old script"}]
    assert session.state["ip_learning_errors"] == [{"source": "bad", "error": "failed"}]
    assert session.state["ip_learning_topics"] == ["保留选题"]
    assert session.state["ip_learning_selected_topic"] == "保留选题"
    assert session.state["ip_learning_summary"] == "已提取 1 条，失败 1 条"
    assert session.state["ip_learning_requires_topic_confirmation"] is True


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
        "max_mel_tokens": 1500,
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


def test_artifact_download_falls_back_to_final_video_state(tmp_path):
    client = _client()
    session_id = client.post("/api/ip-broadcast/sessions").json()["session_id"]
    video_path = Path.cwd() / "output" / f"{session_id}_fallback_final.mp4"
    video_path.parent.mkdir(exist_ok=True)
    video_path.write_bytes(b"video")
    try:
        _session_store.update_config(session_id, {"final_video_path": str(video_path)})

        response = client.get(f"/api/ip-broadcast/sessions/{session_id}/artifacts/final_video")

        assert response.status_code == 200
        assert response.content == b"video"
    finally:
        video_path.unlink(missing_ok=True)


def test_artifact_download_allows_project_temp_preview_files(tmp_path):
    client = _client()
    session_id = client.post("/api/ip-broadcast/sessions").json()["session_id"]
    audio_path = Path.cwd() / "temp" / f"{session_id}_preview.mp3"
    audio_path.parent.mkdir(exist_ok=True)
    audio_path.write_bytes(b"audio")
    try:
        _session_store.update_config(session_id, {"audio_path": str(audio_path)})

        response = client.get(f"/api/ip-broadcast/sessions/{session_id}/artifacts/audio")

        assert response.status_code == 200
        assert response.content == b"audio"
    finally:
        audio_path.unlink(missing_ok=True)
