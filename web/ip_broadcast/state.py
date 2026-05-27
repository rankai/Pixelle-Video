"""Session state helpers for IP broadcast page. All keys prefixed ipb_"""

import re
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
        "ipb_step_status": {i: "pending" for i in range(1, 7)},
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
        "ipb_ip_show_manual_fallback": False,
        # Module 2
        "ipb_m2_style_prompt": "口语化、亲切自然、有感染力",
        "ipb_m2_word_count": 200,
        "ipb_final_script": "",
        "ipb_final_script_editor": "",
        "_ipb_editor_synced_value": "",
        "ipb_m2_output": "",
        # Module 3
        "ipb_m3_inference_mode": "local",
        "ipb_m3_language": "zh-CN",
        "ipb_m3_voice": "zh-CN-YunjianNeural",
        "ipb_m3_speed": 1.2,
        "ipb_m3_pitch": 0,
        "ipb_m3_volume": 0,
        "ipb_m3_tts_workflow": "",
        "ipb_m3_workflow_language": "zh-CN",
        "ipb_m3_workflow_voice": "[Chinese] zh-CN Yunjian",
        "ipb_m3_workflow_speed": 1.0,
        "ipb_m3_workflow_pitch": 0,
        "ipb_m3_spark_gender": "male",
        "ipb_m3_spark_speed": "moderate",
        "ipb_m3_spark_pitch": "moderate",
        "ipb_m3_index_mode": "Auto",
        "ipb_m3_index_do_sample_mode": "on",
        "ipb_m3_temperature": 0.8,
        "ipb_m3_top_p": 0.9,
        "ipb_m3_top_k": 30,
        "ipb_m3_num_beams": 3,
        "ipb_m3_repetition_penalty": 10.0,
        "ipb_m3_length_penalty": 0.0,
        "ipb_m3_max_mel_tokens": 1815,
        "ipb_m3_max_tokens_per_sentence": 120,
        "ipb_m3_max_new_tokens": 3000,
        "ipb_m3_do_sample": True,
        "ipb_m3_seed": 0,
        "ipb_m3_preview_text": "大家好，这是一段测试语音。",
        "ipb_m3_ref_audio_id": "",
        "ipb_m3_new_ref_audio_name": "",
        "ipb_m3_ref_audio_uploader_nonce": 0,
        "ipb_m3_ref_audio_path": "",
        "ipb_m3_audio_path": "",
        # Module 4
        "ipb_m4_portrait_id": "",
        "ipb_m4_dh_video_path": "",
        "ipb_m4_workflow": "workflows/runninghub/digital_combination.json",
        "ipb_m4_prompt": "自然口播，正面镜头，表情稳定，唇形同步",
        "ipb_m4_duration": 0.0,
        # Module 5
        "ipb_m5_template_id": "boss_clean",
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
        # Overlay planning
        "ipb_overlay_enabled": False,
        "ipb_overlay_selected_segments": [],
        "ipb_overlay_picker_nonce": 0,
        "ipb_storyboard_enabled": False,
        "ipb_story_segments": [],
        "ipb_visual_groups": [],
    }
    for key, val in defaults.items():
        if key not in session:
            session[key] = val
    session["ipb_step_status"] = {
        i: session.get("ipb_step_status", {}).get(i, "pending")
        for i in range(1, 7)
    }

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
        session["ipb_step_status"] = {i: "pending" for i in range(1, 7)}
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
    sync_story_segments_from_script(final, session)
    if final:
        session["ipb_active_step"] = 3
        set_step_status(2, "done", session)
        if not session.get("ipb_m3_audio_path"):
            set_step_status(3, "ready", session)


def mark_voice_generated(audio_path: str, session: MutableMapping | None = None):
    session = _session(session)
    init_ip_broadcast_state(session)
    session["ipb_m3_audio_path"] = audio_path
    session["ipb_active_step"] = 4
    if audio_path:
        set_step_status(3, "done", session)


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
    if (
        session.get("ipb_final_script")
        and not _path_exists(session.get("ipb_m3_audio_path", ""))
        and get_step_status(3, session) != "done"
    ):
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
    if _path_exists(session.get("ipb_m5_final_video_path", "")):
        set_step_status(6, "ready", session)


def get_completed_step_count(session: MutableMapping | None = None) -> int:
    session = _session(session)
    init_ip_broadcast_state(session)
    refresh_step_readiness(session)
    return sum(1 for status in session.get("ipb_step_status", {}).values() if status == "done")


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
    return NextAction("publish", 6, "查看并下载", "最终视频和发布素材已准备好")


def split_script_to_segments(text: str) -> list[str]:
    """Split a script into user-visible paragraphs by Enter/newlines."""
    return [part.strip() for part in re.split(r"\n+", text.strip()) if part.strip()]


def _new_segment(index: int, text: str, group_id: str) -> dict:
    return {
        "segment_id": f"segment_{index}",
        "index": index,
        "text": text,
        "visual_group_id": group_id,
        "audio_path": "",
        "duration": 0.0,
    }


def _new_group(index: int, segment_ids: list[str]) -> dict:
    return {
        "group_id": f"group_{index}",
        "segment_ids": segment_ids,
        "visual_type": "digital_human",
        "overlay_type": "none",
        "overlay_mode": "fullscreen",
        "prompt": "",
        "video_asset_id": "",
        "uploaded_video_path": "",
        "generated_video_path": "",
        "start_time": 0.0,
        "end_time": 0.0,
        "status": "pending",
        "error": "",
        "is_overlay_group": False,
    }


def sync_story_segments_from_script(text: str, session: MutableMapping | None = None):
    session = _session(session)
    init_ip_broadcast_state(session)
    parts = split_script_to_segments(text)
    old_segments = {item.get("text"): item for item in session.get("ipb_story_segments", [])}
    old_groups = {item.get("group_id"): item for item in session.get("ipb_visual_groups", [])}

    segments = []
    groups = []
    for idx, part in enumerate(parts, start=1):
        old = old_segments.get(part, {})
        old_group_id = old.get("visual_group_id")
        if old_group_id and old_group_id in old_groups:
            group_id = old_group_id
        else:
            group_id = f"group_{idx}"
        segment = _new_segment(idx, part, group_id)
        segment["audio_path"] = old.get("audio_path", "")
        segment["duration"] = old.get("duration", 0.0)
        segments.append(segment)

    grouped_segment_ids: dict[str, list[str]] = {}
    for segment in segments:
        grouped_segment_ids.setdefault(segment["visual_group_id"], []).append(segment["segment_id"])

    for idx, (group_id, segment_ids) in enumerate(grouped_segment_ids.items(), start=1):
        old_group = old_groups.get(group_id, {})
        group = _new_group(idx, segment_ids)
        group["group_id"] = group_id
        for key in (
            "visual_type",
            "overlay_type",
            "overlay_mode",
            "prompt",
            "video_asset_id",
            "uploaded_video_path",
            "generated_video_path",
            "start_time",
            "end_time",
            "status",
            "error",
            "is_overlay_group",
        ):
            if key in old_group:
                group[key] = old_group[key]
        groups.append(group)

    session["ipb_story_segments"] = segments
    session["ipb_visual_groups"] = groups


def merge_story_segments(segment_ids: list[str], session: MutableMapping | None = None):
    create_overlay_group(segment_ids, session)


def create_overlay_group(segment_ids: list[str], session: MutableMapping | None = None):
    session = _session(session)
    init_ip_broadcast_state(session)
    requested = [sid for sid in segment_ids if sid]
    if not requested:
        return

    segment_by_id = {item["segment_id"]: item for item in session.get("ipb_story_segments", [])}
    indexes = sorted(segment_by_id[sid]["index"] for sid in requested if sid in segment_by_id)
    if not indexes or indexes != list(range(indexes[0], indexes[-1] + 1)):
        raise ValueError("只支持连续段落合并为同一个画面组")

    first_segment = segment_by_id.get(requested[0], {})
    old_group_by_id = {item["group_id"]: item for item in session.get("ipb_visual_groups", [])}
    seed_group = old_group_by_id.get(first_segment.get("visual_group_id"), {})
    new_group_id = (
        first_segment.get("visual_group_id", f"group_{indexes[0]}")
        if len(indexes) == 1
        else f"group_{indexes[0]}_{indexes[-1]}"
    )
    for segment in session.get("ipb_story_segments", []):
        if segment["index"] in indexes:
            segment["visual_group_id"] = new_group_id

    _rebuild_visual_groups(session, overlay_group_id=new_group_id, seed_group=seed_group)


def remove_overlay_group(group_id: str, session: MutableMapping | None = None):
    session = _session(session)
    init_ip_broadcast_state(session)
    if not group_id:
        return

    for segment in session.get("ipb_story_segments", []):
        if segment.get("visual_group_id") == group_id:
            segment["visual_group_id"] = f"group_{segment['index']}"

    _rebuild_visual_groups(session)


def _rebuild_visual_groups(
    session: MutableMapping,
    overlay_group_id: str = "",
    seed_group: dict | None = None,
):
    old_group_by_id = {item["group_id"]: item for item in session.get("ipb_visual_groups", [])}
    groups = []
    seen = set()
    for segment in session.get("ipb_story_segments", []):
        group_id = segment["visual_group_id"]
        if group_id in seen:
            continue
        seen.add(group_id)
        group_segments = [
            item["segment_id"]
            for item in session.get("ipb_story_segments", [])
            if item["visual_group_id"] == group_id
        ]
        group = _new_group(len(groups) + 1, group_segments)
        group["group_id"] = group_id
        source = seed_group or {} if group_id == overlay_group_id else old_group_by_id.get(group_id, {})
        for key in (
            "visual_type",
            "overlay_type",
            "overlay_mode",
            "prompt",
            "video_asset_id",
            "uploaded_video_path",
            "generated_video_path",
            "start_time",
            "end_time",
            "status",
            "error",
            "is_overlay_group",
        ):
            if key in source:
                group[key] = source[key]
        if group_id == overlay_group_id:
            group["is_overlay_group"] = True
        groups.append(group)
    session["ipb_visual_groups"] = groups
