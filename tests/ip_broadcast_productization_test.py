import importlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.ip_broadcast import _step_progress_message
from api.tasks import TaskType
from api.tasks.manager import TaskManager
from pixelle_video.services.ip_broadcast_composer import (
    build_segment_timeline,
    build_video_overlay_command,
)
from pixelle_video.services.ip_broadcast_video_plan import (
    apply_video_plan_to_visual_groups,
    generate_video_plan,
)
from pixelle_video.services.ip_broadcast_workflow import (
    IpBroadcastSession,
    run_ip_broadcast_step,
)


def _assets_client(monkeypatch, tmp_path) -> TestClient:
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    assets_module = importlib.import_module("api.routers.assets")
    app = FastAPI()
    app.include_router(assets_module.router, prefix="/api")
    return TestClient(app)


@pytest.mark.asyncio
async def test_publish_step_creates_productized_publish_package(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    final_video = tmp_path / "final.mp4"
    final_video.write_bytes(b"video")
    session = IpBroadcastSession(session_id="s1")
    session.update_config(
        {
            "final_script": "第一段口播文案。\n第二段口播文案。",
            "copywriting_confirmed": True,
            "final_video_path": str(final_video),
            "title": "老板口播标题",
            "description": "老板口播描述",
            "hashtags": ["老板口播", "探店"],
        }
    )

    assert await run_ip_broadcast_step(None, session, "publish") is True

    package = session.state["publish_package"]
    assert package["title"] == "老板口播标题"
    assert package["platform_suggestions"]["douyin"]["hashtags"] == ["老板口播", "探店"]
    assert "script" in session.artifacts
    assert "publish_package_json" in session.artifacts
    assert Path(session.artifacts["script"]).read_text(encoding="utf-8").startswith("第一段")
    assert json.loads(Path(session.artifacts["publish_package_json"]).read_text(encoding="utf-8"))[
        "description"
    ] == "老板口播描述"


@pytest.mark.asyncio
async def test_publish_step_uses_business_goal_platforms_and_tags(monkeypatch, tmp_path):
    monkeypatch.setenv("PIXELLE_VIDEO_ROOT", str(tmp_path))
    final_video = tmp_path / "final.mp4"
    final_video.write_bytes(b"video")
    session = IpBroadcastSession(session_id="s1")
    session.update_config(
        {
            "final_script": "双人牛油火锅套餐 99 元，适合下班聚餐。",
            "copywriting_confirmed": True,
            "final_video_path": str(final_video),
            "title": "火锅双人套餐限时优惠",
            "description": "附近上班族下班就能吃的火锅套餐。",
            "business_goal_name": "团购转化",
            "business_publish_platforms": ["douyin", "kuaishou"],
        }
    )

    assert await run_ip_broadcast_step(None, session, "publish") is True

    package = session.state["publish_package"]
    assert package["hashtags"] == ["老板口播", "IP口播", "团购套餐", "到店优惠"]
    assert list(package["platform_suggestions"].keys())[:2] == ["douyin", "kuaishou"]
    assert package["preferred_platforms"] == ["douyin", "kuaishou"]
    assert package["cover_title"] == "火锅双人套餐限时优惠"
    assert package["comment_cta"] == "想了解套餐详情，评论区打“套餐”。"


@pytest.mark.asyncio
async def test_step_error_notice_uses_business_message_and_technical_detail():
    class FailingTTS:
        async def tts(self, **_kwargs):
            raise RuntimeError("HTTP 401: unauthorized")

    session = IpBroadcastSession(session_id="s1")
    session.update_config({"final_script": "测试文案"})

    assert await run_ip_broadcast_step(FailingTTS(), session, "voice") is False

    notice = session.notices[3]
    assert notice["kind"] == "error"
    assert notice["message"] == "RunningHub Key 无效或无权限，请到配置中心检查。"
    assert notice["technical_message"] == "HTTP 401: unauthorized"
    assert notice["category"] == "auth"


def test_ip_broadcast_presets_api_returns_business_defaults(monkeypatch, tmp_path):
    client = _assets_client(monkeypatch, tmp_path)

    response = client.get("/api/assets/presets/ip-broadcast")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["preset_id"] for item in items[:2]] == ["boss_persona", "store_visit"]
    assert items[1]["recommended_word_count"] > 0
    assert items[1]["default_template_id"]


def test_group_buying_video_plan_recommends_business_readable_visuals():
    script = "今天双人牛油火锅套餐只要99元。\n套餐里有鲜切牛肉和现炸酥肉。\n下班聚餐到店就能吃。"

    plan = generate_video_plan(
        business_goal="团购转化",
        script=script,
        visual_strategy="套餐内容段用门店或产品视频覆盖。",
    )

    assert plan["status"] == "ready"
    assert plan["summary"] == "老板出镜 1 段 · 插入门店视频 2 段"
    assert plan["segments"][0]["visual_type"] == "digital_human"
    assert plan["segments"][1]["visual_type"] == "uploaded_video"
    assert plan["segments"][1]["asset_keywords"] == ["菜品", "套餐", "产品"]
    assert "菜品/套餐视频" in plan["segments"][1]["label"]


def test_video_plan_application_creates_existing_visual_groups():
    plan = {
        "segments": [
            {"segment_id": "1", "visual_type": "digital_human"},
            {
                "segment_id": "2",
                "visual_type": "uploaded_video",
                "prompt": "菜品和套餐特写",
                "asset_keywords": ["菜品", "套餐"],
            },
            {
                "segment_id": "3",
                "visual_type": "uploaded_video",
                "prompt": "门店环境和聚餐画面",
                "asset_keywords": ["门店", "环境"],
            },
        ]
    }

    groups = apply_video_plan_to_visual_groups(plan)

    assert groups == [
        {
            "group_id": "plan_group_2",
            "segment_ids": ["2"],
            "visual_type": "uploaded_video",
            "prompt": "菜品和套餐特写",
            "uploaded_video_path": "",
            "video_asset_id": "",
            "status": "recommended",
            "asset_keywords": ["菜品", "套餐"],
        },
        {
            "group_id": "plan_group_3",
            "segment_ids": ["3"],
            "visual_type": "uploaded_video",
            "prompt": "门店环境和聚餐画面",
            "uploaded_video_path": "",
            "video_asset_id": "",
            "status": "recommended",
            "asset_keywords": ["门店", "环境"],
        },
    ]


@pytest.mark.asyncio
async def test_copywriting_generates_video_plan_from_business_goal():
    class FakePixelleVideo:
        async def llm(self, prompt, response_type=None):
            assert response_type is None
            return "今天双人牛油火锅套餐只要99元。\n套餐里有鲜切牛肉和现炸酥肉。\n下班聚餐到店就能吃。"

    session = IpBroadcastSession(session_id="s1")
    session.update_config(
        {
            "final_script": "火锅套餐文案",
            "business_goal_name": "团购转化",
            "business_visual_strategy": "套餐内容段用门店或产品视频覆盖。",
        }
    )

    assert await run_ip_broadcast_step(FakePixelleVideo(), session, "copywriting") is True

    assert session.state["video_plan_status"] == "ready"
    assert session.state["video_plan"]["summary"] == "老板出镜 1 段 · 插入门店视频 2 段"
    assert session.state["video_plan_applied"] is False


def test_brand_kit_create_list_update_and_delete(monkeypatch, tmp_path):
    client = _assets_client(monkeypatch, tmp_path)

    created = client.post(
        "/api/assets/brand-kits",
        json={
            "brand_name": "测试门店",
            "primary_color": "#0f766e",
            "store_address": "上海市",
            "coupon_phrase": "到店报暗号",
        },
    )

    assert created.status_code == 200
    brand_id = created.json()["brand_id"]
    assert client.get("/api/assets/brand-kits").json()["items"][0]["brand_id"] == brand_id

    updated = client.patch(
        f"/api/assets/brand-kits/{brand_id}",
        json={"phone": "13800000000"},
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "13800000000"

    deleted = client.delete(f"/api/assets/brand-kits/{brand_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True


def test_task_manager_keeps_product_task_metadata():
    manager = TaskManager()

    task = manager.create_task(
        TaskType.IP_BROADCAST_STEP,
        request_params={"session_id": "s1", "step_key": "voice"},
        display_name="生成语音",
        flow_name="IP口播",
        step_key="voice",
        session_id="s1",
        artifact_keys=["audio"],
        retry_payload={"kind": "ip_step"},
    )

    assert task.display_name == "生成语音"
    assert task.flow_name == "IP口播"
    assert task.step_key == "voice"
    assert task.session_id == "s1"
    assert task.artifact_keys == ["audio"]
    assert task.retry_payload == {"kind": "ip_step"}


def test_ip_step_progress_message_is_business_readable():
    assert _step_progress_message("digital_human") == (
        "正在生成数字人视频，远程任务通常需要 1-5 分钟，可在 RunningHub 后台查看进度。"
    )


def test_composer_builds_segment_timeline_by_character_ratio():
    timeline = build_segment_timeline(
        [
            {"segment_id": "segment_1", "text": "一一"},
            {"segment_id": "segment_2", "text": "二二二二"},
        ],
        audio_duration=60.0,
    )

    assert timeline == [
        {"segment_id": "segment_1", "start_time": 0.0, "end_time": 20.0, "duration": 20.0},
        {"segment_id": "segment_2", "start_time": 20.0, "end_time": 60.0, "duration": 40.0},
    ]


def test_composer_overlay_command_replaces_video_in_time_range():
    cmd = build_video_overlay_command(
        base_video="/tmp/base.mp4",
        overlay_video="/tmp/clip.mp4",
        output_path="/tmp/out.mp4",
        start_time=2.0,
        end_time=5.5,
        width=720,
        height=1280,
    )

    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert cmd[:6] == ["ffmpeg", "-y", "-i", "/tmp/base.mp4", "-stream_loop", "-1"]
    assert "scale=720:1280" in filter_complex
    assert "enable='between(t,2,5.5)'" in filter_complex
    assert "overlay=0:0" in filter_complex
    assert "0:a?" in cmd
