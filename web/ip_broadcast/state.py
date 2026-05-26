"""Session state helpers for IP broadcast page. All keys prefixed ipb_"""

from dataclasses import dataclass
from pathlib import Path
from typing import MutableMapping

import streamlit as st


@dataclass(frozen=True)
class NextAction:
    key: str
    step: int
    label: str
    description: str
    disabled: bool = False


def _session(session: MutableMapping | None = None) -> MutableMapping:
    return session if session is not None else st.session_state


def init_ip_broadcast_state(session: MutableMapping | None = None):
    session = _session(session)
    defaults = {
        # Global control
        "ipb_run_mode": "manual",
        "ipb_step_status": {i: "pending" for i in range(1, 8)},
        "ipb_active_step": 1,
        # Module 1 — Tab: 提取脚本
        "ipb_source_mode": "视频链接",
        "ipb_source_text": "",
        "ipb_source_label": "",
        "ipb_m1_raw_script": "",
        # Module 1 — Tab: IP大脑
        "ipb_brain_video_type": "口播文案",
        "ipb_brain_copy_type": "人设型",
        "ipb_brain_industry_persona": "",
        "ipb_brain_selling_points": "",
        "ipb_brain_other_reqs": "",
        "ipb_brain_result": "",
        # Module 1 — Tab: 热点选题
        "ipb_hot_viral_input": "",
        "ipb_hot_topics": [],
        "ipb_hot_selected_topic": "",
        "ipb_hot_topic_script": "",
        # Module 1 — IP学习
        "ipb_ip_profile_url": "",
        "ipb_ip_manual_video_links": "",
        "ipb_ip_video_urls": [],
        "ipb_ip_learning_scripts": [],
        "ipb_ip_learning_errors": [],
        "ipb_ip_learning_topics": [],
        "ipb_ip_selected_topic": "",
        "ipb_ip_topic_script": "",
        # Module 2
        "ipb_m2_style_prompt": "口语化、亲切自然、有感染力",
        "ipb_m2_word_count": 200,
        "ipb_final_script": "",
        "ipb_final_script_editor": "",
        "_ipb_editor_synced_value": "",
        "ipb_m2_output": "",
        # Module 3
        "ipb_m3_inference_mode": "local",
        "ipb_m3_voice": "zh-CN-YunjianNeural",
        "ipb_m3_speed": 1.2,
        "ipb_m3_tts_workflow": "",
        "ipb_m3_preview_text": "大家好，这是一段测试语音。",
        "ipb_m3_ref_audio_path": "",
        "ipb_m3_audio_path": "",
        # Module 4
        "ipb_m4_portrait_id": "",
        "ipb_m4_dh_video_path": "",
        "ipb_m4_workflow": "workflows/runninghub/digital_combination.json",
        "ipb_m4_prompt": "自然口播，正面镜头，表情稳定，唇形同步",
        "ipb_m4_duration": 0.0,
        # Module 5
        "ipb_m5_subtitle_enabled": True,
        "ipb_m5_bgm_path": "",
        "ipb_m5_bgm_volume": 0.3,
        "ipb_m5_voice_volume": 1.0,
        "ipb_m5_remove_silence": False,
        "ipb_m5_final_video_path": "",
        # Module 6
        "ipb_m6_title": "",
        "ipb_m6_description": "",
        "ipb_m6_hashtags": [],
        "ipb_m6_cover_mode": "first_frame",
        "ipb_m6_cover_path": "",
    }
    for key, val in defaults.items():
        if key not in session:
            session[key] = val

    if session.get("ipb_m2_output") and not session.get("ipb_final_script"):
        session["ipb_final_script"] = session["ipb_m2_output"]


STATUS_ICONS = {
    "pending": "○",
    "ready": "●",
    "running": "🔄",
    "done": "✅",
    "error": "❌",
}


def get_step_status(step: int, session: MutableMapping | None = None) -> str:
    session = _session(session)
    return session.get("ipb_step_status", {}).get(step, "pending")


def set_step_status(step: int, status: str, session: MutableMapping | None = None):
    session = _session(session)
    if "ipb_step_status" not in session:
        session["ipb_step_status"] = {i: "pending" for i in range(1, 8)}
    session["ipb_step_status"][step] = status


def set_source_text(text: str, label: str, session: MutableMapping | None = None):
    session = _session(session)
    init_ip_broadcast_state(session)
    session["ipb_source_text"] = text.strip()
    session["ipb_source_label"] = label
    session["ipb_active_step"] = 2
    if session["ipb_source_text"]:
        set_step_status(1, "done", session)
        set_final_script(session["ipb_source_text"], session)


def set_final_script(text: str, session: MutableMapping | None = None):
    session = _session(session)
    init_ip_broadcast_state(session)
    final = text.strip()
    session["ipb_final_script"] = final
    session["ipb_m2_output"] = final
    if final:
        session["ipb_active_step"] = 3
        set_step_status(2, "done", session)
        if not session.get("ipb_m3_audio_path"):
            set_step_status(3, "ready", session)


def _path_exists(value: str) -> bool:
    return bool(value and Path(value).exists())


def refresh_step_readiness(session: MutableMapping | None = None):
    session = _session(session)
    init_ip_broadcast_state(session)
    if session.get("ipb_source_text"):
        set_step_status(1, "done", session)
    if session.get("ipb_final_script") or session.get("ipb_m2_output"):
        set_step_status(2, "done", session)
    elif session.get("ipb_source_text") and get_step_status(2, session) == "pending":
        set_step_status(2, "ready", session)
    if session.get("ipb_final_script") and not _path_exists(session.get("ipb_m3_audio_path", "")):
        set_step_status(3, "ready", session)
    if _path_exists(session.get("ipb_m3_audio_path", "")):
        set_step_status(3, "done", session)
    if _path_exists(session.get("ipb_m4_dh_video_path", "")):
        set_step_status(4, "done", session)
    elif _path_exists(session.get("ipb_m3_audio_path", "")) and session.get("ipb_m4_portrait_id"):
        set_step_status(4, "ready", session)
    if _path_exists(session.get("ipb_m5_final_video_path", "")):
        set_step_status(5, "done", session)
    elif _path_exists(session.get("ipb_m4_dh_video_path", "")):
        set_step_status(5, "ready", session)
    if session.get("ipb_m6_title") and session.get("ipb_m6_description"):
        set_step_status(6, "done", session)
    elif session.get("ipb_final_script") and get_step_status(6, session) == "pending":
        set_step_status(6, "ready", session)


def get_next_action(session: MutableMapping | None = None) -> NextAction:
    session = _session(session)
    init_ip_broadcast_state(session)
    refresh_step_readiness(session)

    if not session.get("ipb_source_text") and not session.get("ipb_final_script"):
        return NextAction("prepare_source", 1, "生成口播文案", "先选择素材来源并生成可用文案")
    if not session.get("ipb_final_script"):
        return NextAction("rewrite", 2, "AI 改写/优化文案", "已有来源文案，下一步确认最终口播稿")
    if not _path_exists(session.get("ipb_m3_audio_path", "")):
        return NextAction("voice", 3, "生成语音", "使用最终口播文案合成配音")
    if not session.get("ipb_m4_portrait_id"):
        return NextAction("select_portrait", 4, "选择数字人形象", "先选择或上传一个数字人形象", True)
    if not _path_exists(session.get("ipb_m4_dh_video_path", "")):
        return NextAction("digital_human", 4, "生成数字人视频", "使用形象和语音生成口播视频")
    if not _path_exists(session.get("ipb_m5_final_video_path", "")):
        return NextAction("postproduce", 5, "合成最终视频", "添加字幕、音量和成片设置")
    if not session.get("ipb_m6_title") or not session.get("ipb_m6_description"):
        return NextAction("social_meta", 6, "生成标题封面", "生成发布标题、描述和标签")
    return NextAction("publish", 7, "查看并下载", "最终视频和发布素材已准备好")
