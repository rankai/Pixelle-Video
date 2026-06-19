import importlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers.ip_broadcast import _step_progress_message
from api.tasks import TaskType
from api.tasks.manager import TaskManager
from api.tasks.models import TaskStatus
from api.tasks.persistence import TaskPersistence
from pixelle_video.services import ip_broadcast_workflow as workflow
from pixelle_video.services.ip_broadcast_composer import (
    build_segment_timeline,
    build_video_overlay_command,
)
from pixelle_video.services.ip_broadcast_errors import classify_ip_broadcast_error
from pixelle_video.services.ip_broadcast_video_plan import (
    apply_video_plan_to_visual_groups,
    generate_video_plan,
)
from pixelle_video.services.ip_broadcast_workflow import (
    IpBroadcastSession,
    IpBroadcastSessionStore,
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
    assert notice["message"] == "云端算力服务授权无效或无权限，请到配置中心检查。"
    assert notice["technical_message"] == "HTTP 401: unauthorized"
    assert notice["category"] == "auth"


def test_business_error_messages_hide_technical_provider_names():
    for error in [
        RuntimeError("HTTP 403 forbidden"),
        RuntimeError("timeout while waiting RunningHub task"),
    ]:
        business_error = classify_ip_broadcast_error(error)

        assert "RunningHub" not in business_error.user_message
        assert "ComfyUI" not in business_error.user_message
        assert "RunningHub" not in business_error.next_action
        assert "ComfyUI" not in business_error.next_action


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
async def test_postproduction_uses_selected_template_for_subtitles_and_cover(
    monkeypatch,
    tmp_path,
):
    audio = tmp_path / "voice.mp3"
    base_video = tmp_path / "digital.mp4"
    audio.write_bytes(b"audio")
    base_video.write_bytes(b"video")
    seen: dict[str, str] = {}

    def fake_merge_audio_into_video(video_path, audio_path, output_path):
        seen["merged_video"] = video_path
        seen["merged_audio"] = audio_path
        Path(output_path).write_bytes(b"merged")
        return output_path

    def fake_generate_srt(script, audio_path, output_path):
        seen["srt_script"] = script
        seen["srt_audio"] = audio_path
        Path(output_path).write_text("1\n00:00:00,000 --> 00:00:01,000\n字幕", encoding="utf-8")

    def fake_embed_subtitles(input_path, srt_path, output_path, force_style=None):
        seen["force_style"] = force_style or ""
        Path(output_path).write_bytes(b"final")

    def fake_extract_first_frame(video_path, output_path):
        seen["cover_source"] = video_path
        Path(output_path).write_bytes(b"frame")
        return output_path

    async def fake_render_cover(template_id, title, subtitle="", background="", output_path=None, extra=None):
        seen["cover_template_id"] = template_id
        seen["cover_title"] = title
        seen["cover_subtitle"] = subtitle
        seen["cover_background"] = background
        assert output_path
        Path(output_path).write_bytes(b"cover")
        return output_path

    monkeypatch.setattr(workflow, "merge_audio_into_video", fake_merge_audio_into_video)
    monkeypatch.setattr(workflow, "generate_srt", fake_generate_srt)
    monkeypatch.setattr(workflow, "embed_subtitles", fake_embed_subtitles)
    monkeypatch.setattr(workflow, "extract_first_frame", fake_extract_first_frame)
    monkeypatch.setattr(workflow, "render_ip_broadcast_cover", fake_render_cover)

    session = IpBroadcastSession(session_id="s1")
    session.update_config(
        {
            "final_script": "第一段老板口播。\n第二段门店介绍。",
            "copywriting_confirmed": True,
            "audio_path": str(audio),
            "digital_human_video_path": str(base_video),
            "template_id": "boss_premium",
            "title": "老板口播标题",
            "description": "老板口播描述",
        }
    )

    assert await run_ip_broadcast_step(None, session, "postproduction") is True

    assert "Fontsize=17" in seen["force_style"]
    assert "MarginV=227" in seen["force_style"]
    assert "PrimaryColour=&H00DFF0F4" in seen["force_style"]
    assert seen["cover_template_id"] == "boss_premium"
    assert seen["cover_title"] == "老板口播标题"
    assert seen["cover_subtitle"] == "老板口播描述"
    assert session.state["cover_path"]
    assert session.artifacts["cover"] == session.state["cover_path"]
    assert session.state["publish_package"]["cover_path"] == session.state["cover_path"]


@pytest.mark.asyncio
async def test_postproduction_applies_session_subtitle_style_overrides(
    monkeypatch,
    tmp_path,
):
    audio = tmp_path / "voice.mp3"
    base_video = tmp_path / "digital.mp4"
    audio.write_bytes(b"audio")
    base_video.write_bytes(b"video")
    seen: dict[str, str] = {}

    def fake_merge_audio_into_video(_video_path, _audio_path, output_path):
        Path(output_path).write_bytes(b"merged")
        return output_path

    def fake_generate_srt(_script, _audio_path, output_path):
        Path(output_path).write_text("1\n00:00:00,000 --> 00:00:01,000\n字幕", encoding="utf-8")

    def fake_embed_subtitles(_input_path, _srt_path, output_path, force_style=None):
        seen["force_style"] = force_style or ""
        Path(output_path).write_bytes(b"final")

    async def fake_render_cover(template_id, title, subtitle="", background="", output_path=None, extra=None):
        assert output_path
        Path(output_path).write_bytes(b"cover")
        return output_path

    def fake_extract_first_frame(video_path, output_path):
        Path(output_path).write_bytes(b"frame")
        return output_path

    monkeypatch.setattr(workflow, "merge_audio_into_video", fake_merge_audio_into_video)
    monkeypatch.setattr(workflow, "generate_srt", fake_generate_srt)
    monkeypatch.setattr(workflow, "embed_subtitles", fake_embed_subtitles)
    monkeypatch.setattr(workflow, "render_ip_broadcast_cover", fake_render_cover)
    monkeypatch.setattr(workflow, "extract_first_frame", fake_extract_first_frame)

    session = IpBroadcastSession(session_id="s1")
    session.update_config(
        {
            "final_script": "第一段老板口播。",
            "copywriting_confirmed": True,
            "audio_path": str(audio),
            "digital_human_video_path": str(base_video),
            "template_id": "boss_clean",
            "subtitle_style": {
                "font_size": 22,
                "margin_v": 90,
            },
        }
    )

    assert await run_ip_broadcast_step(None, session, "postproduction") is True

    assert "Fontsize=22" in seen["force_style"]
    assert "MarginV=90" in seen["force_style"]
    assert "Outline=2" in seen["force_style"]


@pytest.mark.asyncio
async def test_postproduction_mixes_selected_bgm(monkeypatch, tmp_path):
    audio = tmp_path / "voice.mp3"
    base_video = tmp_path / "digital.mp4"
    bgm = tmp_path / "bgm.mp3"
    audio.write_bytes(b"audio")
    base_video.write_bytes(b"video")
    bgm.write_bytes(b"music")
    seen: dict[str, object] = {}

    def fake_merge_audio_into_video(_video_path, _audio_path, output_path):
        Path(output_path).write_bytes(b"merged")
        return output_path

    def fake_generate_srt(_script, _audio_path, output_path):
        Path(output_path).write_text("1\n00:00:00,000 --> 00:00:01,000\n字幕", encoding="utf-8")

    def fake_embed_subtitles(_input_path, _srt_path, output_path, force_style=None):
        Path(output_path).write_bytes(b"final")

    def fake_run(cmd, check=False, capture_output=False):
        seen["cmd"] = cmd
        seen["check"] = check
        seen["capture_output"] = capture_output
        Path(cmd[-1]).write_bytes(b"with bgm")

    def fake_extract_first_frame(video_path, output_path):
        seen["cover_source"] = video_path
        Path(output_path).write_bytes(b"frame")
        return output_path

    async def fake_render_cover(template_id, title, subtitle="", background="", output_path=None, extra=None):
        assert output_path
        Path(output_path).write_bytes(b"cover")
        return output_path

    monkeypatch.setattr(workflow, "merge_audio_into_video", fake_merge_audio_into_video)
    monkeypatch.setattr(workflow, "generate_srt", fake_generate_srt)
    monkeypatch.setattr(workflow, "embed_subtitles", fake_embed_subtitles)
    monkeypatch.setattr(workflow.subprocess, "run", fake_run)
    monkeypatch.setattr(workflow, "extract_first_frame", fake_extract_first_frame)
    monkeypatch.setattr(workflow, "render_ip_broadcast_cover", fake_render_cover)

    session = IpBroadcastSession(session_id="s1")
    session.update_config(
        {
            "final_script": "老板口播文案。",
            "copywriting_confirmed": True,
            "audio_path": str(audio),
            "digital_human_video_path": str(base_video),
            "bgm_path": str(bgm),
            "bgm_volume": 0.25,
            "voice_volume": 0.9,
        }
    )

    assert await run_ip_broadcast_step(None, session, "postproduction") is True

    cmd = seen["cmd"]
    assert str(bgm) in cmd
    assert "volume=0.25[bgm]" in cmd[cmd.index("-filter_complex") + 1]
    assert "volume=0.9[voice]" in cmd[cmd.index("-filter_complex") + 1]
    assert session.state["final_video_path"].endswith("_final_bgm.mp4")
    assert seen["cover_source"] == session.state["final_video_path"]


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


def test_task_manager_persists_tasks_to_local_sqlite(tmp_path):
    db_path = tmp_path / "desktop_tasks.sqlite"
    manager = TaskManager(TaskPersistence(db_path))

    task = manager.create_task(
        TaskType.IP_BROADCAST_STEP,
        display_name="生成语音",
        flow_name="IP口播",
        step_key="voice",
        session_id="s1",
        artifact_keys=["audio"],
        retry_payload={"kind": "ip_step"},
    )
    manager.update_progress(task.task_id, 1, 3, "正在生成配音。")

    reloaded = TaskManager(TaskPersistence(db_path))
    tasks = reloaded.list_tasks()

    assert len(tasks) == 1
    assert tasks[0].task_id == task.task_id
    assert tasks[0].display_name == "生成语音"
    assert tasks[0].progress.message == "正在生成配音。"


def test_task_manager_marks_running_tasks_interrupted_after_restart(tmp_path):
    db_path = tmp_path / "desktop_tasks.sqlite"
    manager = TaskManager(TaskPersistence(db_path))
    task = manager.create_task(TaskType.IP_BROADCAST_STEP, display_name="生成数字人视频")
    task.status = TaskStatus.RUNNING
    manager._persist_task(task)

    reloaded = TaskManager(TaskPersistence(db_path))
    tasks = reloaded.list_tasks()

    assert tasks[0].status == TaskStatus.FAILED
    assert tasks[0].error == "服务重启，任务已中断，请重新执行。"


def test_ip_broadcast_session_store_persists_completed_artifacts(tmp_path):
    final = tmp_path / "final.mp4"
    final.write_bytes(b"video")
    store_path = tmp_path / "ip_sessions"
    store = IpBroadcastSessionStore(store_path=store_path)
    session = store.create_session()

    store.update_config(session.session_id, {"final_script": "老板口播文案"})
    store.update_config(
        session.session_id,
        {
            "copywriting_confirmed": True,
            "final_video_path": str(final),
        },
    )
    session.artifacts["final_video"] = str(final)
    store.save_session(session)

    restored_store = IpBroadcastSessionStore(store_path=store_path)
    restored = restored_store.get_session(session.session_id)

    assert restored is not None
    assert restored.state["final_video_path"] == str(final)
    assert restored.artifacts["final_video"] == str(final)
    assert restored.next_action()["key"] == "publish"


def test_session_invalidates_downstream_artifacts_when_script_changes(tmp_path):
    audio = tmp_path / "voice.mp3"
    dh = tmp_path / "dh.mp4"
    final = tmp_path / "final.mp4"
    cover = tmp_path / "cover.png"
    for path in (audio, dh, final, cover):
        path.write_bytes(b"ok")
    session = IpBroadcastSession(session_id="s1")
    session.update_config(
        {
            "final_script": "旧文案",
            "copywriting_confirmed": True,
            "audio_path": str(audio),
            "digital_human_video_path": str(dh),
            "final_video_path": str(final),
            "cover_path": str(cover),
            "publish_package": {"video_path": str(final)},
        }
    )
    session.artifacts.update(
        {
            "audio": str(audio),
            "digital_human_video": str(dh),
            "final_video": str(final),
            "cover": str(cover),
        }
    )

    session.update_config({"final_script": "新文案"})

    assert session.state["copywriting_confirmed"] is False
    assert session.state["audio_path"] == ""
    assert session.state["digital_human_video_path"] == ""
    assert session.state["final_video_path"] == ""
    assert session.state["cover_path"] == ""
    assert session.state["publish_package"] == {}
    assert "audio" not in session.artifacts
    assert "digital_human_video" not in session.artifacts
    assert "final_video" not in session.artifacts
    assert "cover" not in session.artifacts


def test_ip_step_progress_message_is_business_readable():
    assert _step_progress_message("digital_human") == (
        "正在使用云端算力生成数字人视频，通常需要 1-5 分钟。"
    )
    for step_key in ["source", "copywriting", "voice", "digital_human", "postproduction", "publish"]:
        assert "RunningHub" not in _step_progress_message(step_key)
        assert "ComfyUI" not in _step_progress_message(step_key)


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
        output_duration=52.0,
        width=720,
        height=1280,
    )

    filter_complex = cmd[cmd.index("-filter_complex") + 1]
    assert cmd[:6] == ["ffmpeg", "-y", "-i", "/tmp/base.mp4", "-stream_loop", "-1"]
    assert "scale=720:1280" in filter_complex
    assert "enable='between(t,2,5.5)'" in filter_complex
    assert "overlay=0:0" in filter_complex
    assert "0:a?" in cmd
    assert cmd[cmd.index("-t") + 1] == "52"
