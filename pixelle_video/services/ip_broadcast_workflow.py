"""Streamlit-free IP broadcast workflow state and step execution."""

from __future__ import annotations

import inspect
import json
import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from pixelle_video.config import config_manager
from pixelle_video.models.ip_broadcast import HotTopicsResult
from pixelle_video.prompts.ip_broadcast import (
    build_hot_topics_from_viral_prompt,
    build_ip_brain_generation_prompt,
    build_rewrite_prompt,
    build_script_extraction_prompt,
    build_script_from_topic_prompt,
)
from pixelle_video.services.digital_human_service import _load_workflow_config
from pixelle_video.services.ip_broadcast_composer import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    compose_ip_broadcast_video,
    normalize_video_to_canvas,
)
from pixelle_video.services.ip_broadcast_errors import classify_ip_broadcast_error
from pixelle_video.services.ip_broadcast_templates import (
    build_ass_force_style,
    get_ip_broadcast_template_for_render,
    render_ip_broadcast_cover,
    resolve_ip_broadcast_fonts_dir,
    wrap_template_subtitle_text,
)
from pixelle_video.services.ip_broadcast_video_plan import generate_video_plan
from pixelle_video.services.ip_learning import (
    extract_many_video_scripts,
    fetch_latest_video_urls_from_profile,
    parse_manual_video_inputs,
)
from pixelle_video.services.script_extractor import VideoScriptExtractor
from pixelle_video.services.subtitle_service import (
    embed_subtitles,
    extract_first_frame,
    generate_ass,
    generate_srt,
    merge_audio_into_video,
    remove_silence,
)
from pixelle_video.utils.os_util import get_data_path, get_output_path, get_temp_path

STEP_SOURCE = "source"
STEP_COPYWRITING = "copywriting"
STEP_VOICE = "voice"
STEP_DIGITAL_HUMAN = "digital_human"
STEP_POSTPRODUCTION = "postproduction"
STEP_PUBLISH = "publish"

INDEX_TTS_MAX_MEL_TOKENS_LIMIT = 1500

VOICE_DEPENDENCY_KEYS = {
    "final_script",
    "tts_text",
    "tts_mode",
    "voice_source",
    "tts_voice",
    "tts_ref_audio_id",
    "tts_speed",
    "tts_ref_audio_path",
    "tts_ref_text",
    "tts_max_mel_tokens",
    "tts_max_tokens_per_sentence",
    "tts_max_new_tokens",
}
DIGITAL_HUMAN_DEPENDENCY_KEYS = {
    "portrait_id",
    "portrait_path",
    "portrait_media_type",
    "digital_human_scene_id",
    "digital_human_workflow",
    "digital_human_prompt",
    "digital_human_duration",
    "digital_human_width",
    "digital_human_height",
}
FINAL_VIDEO_DEPENDENCY_KEYS = {
    "brand_kit_id",
    "brand_bgm_asset_id",
    "bgm_asset_id",
    "template_id",
    "story_segments",
    "visual_groups",
    "video_plan",
    "video_plan_applied",
    "overlay_enabled",
    "subtitle_enabled",
    "bgm_path",
    "bgm_volume",
    "voice_volume",
    "remove_silence",
    "subtitle_style",
    "output_canvas_width",
    "output_canvas_height",
}
COVER_ONLY_DEPENDENCY_KEYS = {
    "title",
    "description",
    "cover_title",
}
IP_LEARNING_INPUT_KEYS = {
    "source_mode",
    "ip_profile_url",
    "ip_manual_video_links",
    "source_text",
}
IP_LEARNING_CACHE_LIST_KEYS = {
    "ip_learning_video_urls",
    "ip_learning_scripts",
    "ip_learning_errors",
    "ip_learning_topics",
}
IP_LEARNING_CACHE_TEXT_KEYS = {
    "ip_learning_selected_topic",
    "ip_learning_summary",
}

STEP_KEYS = {
    STEP_SOURCE: 1,
    STEP_COPYWRITING: 2,
    STEP_VOICE: 3,
    STEP_DIGITAL_HUMAN: 4,
    STEP_POSTPRODUCTION: 5,
    STEP_PUBLISH: 6,
}


def _default_state() -> dict[str, Any]:
    return {
        "source_mode": "video_extract",
        "video_input": "",
        "business_preset_id": "",
        "business_goal_name": "",
        "business_script_structure": [],
        "business_visual_strategy": "",
        "business_publish_platforms": [],
        "business_intent_note": "",
        "brand_kit_id": "",
        "brand_bgm_asset_id": "",
        "bgm_asset_id": "",
        "source_text": "",
        "source_label": "",
        "video_type": "口播文案",
        "copy_type": "人设型",
        "industry_persona": "",
        "selling_points": "",
        "target_customer": "",
        "conversion_phrase": "",
        "other_reqs": "",
        "ip_profile_url": "",
        "ip_manual_video_links": "",
        "ip_learning_video_urls": [],
        "ip_learning_scripts": [],
        "ip_learning_errors": [],
        "ip_learning_topics": [],
        "ip_learning_summary": "",
        "ip_learning_selected_topic": "",
        "ip_learning_requires_topic_confirmation": False,
        "style_prompt": "口语化、亲切自然、有感染力",
        "word_count": 200,
        "final_script": "",
        "copywriting_confirmed": False,
        "tts_inference_mode": "local",
        "tts_voice": "zh-CN-YunjianNeural",
        "tts_speed": 1.2,
        "tts_pitch": 0,
        "tts_volume": 0,
        "tts_workflow": "runninghub/tts_index_custom.json",
        "tts_workflow_language": "zh-CN",
        "tts_workflow_voice": "[Chinese] zh-CN Yunjian",
        "tts_workflow_speed": 1.0,
        "tts_workflow_pitch": 0,
        "tts_index_mode": "Auto",
        "tts_index_do_sample_mode": "on",
        "tts_temperature": 0.8,
        "tts_top_p": 0.9,
        "tts_top_k": 30,
        "tts_num_beams": 3,
        "tts_repetition_penalty": 10.0,
        "tts_length_penalty": 0.0,
        "tts_max_mel_tokens": INDEX_TTS_MAX_MEL_TOKENS_LIMIT,
        "tts_max_tokens_per_sentence": 120,
        "tts_seed": 0,
        "tts_spark_gender": "male",
        "tts_spark_speed": "moderate",
        "tts_spark_pitch": "moderate",
        "tts_max_new_tokens": 3000,
        "tts_do_sample": True,
        "tts_ref_audio_id": "",
        "tts_ref_audio_path": "",
        "audio_path": "",
        "portrait_id": "",
        "portrait_path": "",
        "portrait_media_type": "",
        "digital_human_scene_id": "",
        "digital_human_workflow": "workflows/runninghub/digital_combination.json",
        "digital_human_prompt": "自然口播，正面镜头，表情稳定，唇形同步",
        "digital_human_duration": 0.0,
        "digital_human_width": 720,
        "digital_human_height": 1280,
        "digital_human_video_path": "",
        "output_canvas_width": CANVAS_WIDTH,
        "output_canvas_height": CANVAS_HEIGHT,
        "template_id": "boss_clean",
        "story_segments": [],
        "visual_groups": [],
        "video_plan": {},
        "video_plan_status": "empty",
        "video_plan_applied": False,
        "overlay_enabled": False,
        "subtitle_enabled": True,
        "bgm_path": "",
        "bgm_volume": 0.3,
        "voice_volume": 1.0,
        "remove_silence": False,
        "final_video_path": "",
        "title": "",
        "description": "",
        "hashtags": [],
        "cover_path": "",
        "publish_package": {},
        "platform_suggestions": {},
        "script_summary": "",
    }


@dataclass
class IpBroadcastSession:
    session_id: str
    state: dict[str, Any] = field(default_factory=_default_state)
    step_status: dict[int, str] = field(
        default_factory=lambda: {step: "pending" for step in range(1, 7)}
    )
    notices: dict[int, dict[str, str]] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)

    def update_config(self, values: dict[str, Any]) -> None:
        changed_keys = {
            key
            for key, value in values.items()
            if self.state.get(key) != value
        }
        self.state.update(values)
        self._invalidate_dependents(changed_keys, set(values))
        self.refresh_readiness()

    def _invalidate_dependents(self, changed_keys: set[str], protected_keys: set[str]) -> None:
        if changed_keys & IP_LEARNING_INPUT_KEYS:
            self._clear_ip_learning_outputs(protected_keys)
        if "final_script" in changed_keys:
            self.state["copywriting_confirmed"] = False
        if changed_keys & VOICE_DEPENDENCY_KEYS:
            self._clear_voice_outputs(protected_keys)
        elif changed_keys & DIGITAL_HUMAN_DEPENDENCY_KEYS:
            self._clear_digital_human_outputs(protected_keys)
        elif changed_keys & FINAL_VIDEO_DEPENDENCY_KEYS:
            self._clear_final_outputs(protected_keys)
        elif changed_keys & COVER_ONLY_DEPENDENCY_KEYS:
            self._clear_cover_outputs(protected_keys)

    def _clear_ip_learning_outputs(self, protected_keys: set[str]) -> None:
        for key in IP_LEARNING_CACHE_LIST_KEYS:
            if key not in protected_keys:
                self.state[key] = []
        for key in IP_LEARNING_CACHE_TEXT_KEYS:
            if key not in protected_keys:
                self.state[key] = ""
        if "ip_learning_requires_topic_confirmation" not in protected_keys:
            self.state["ip_learning_requires_topic_confirmation"] = False
        if "final_script" not in protected_keys:
            self.state["final_script"] = ""
        if "source_text" not in protected_keys:
            self.state["source_text"] = ""
        if "source_label" not in protected_keys:
            self.state["source_label"] = ""
        self.state["copywriting_confirmed"] = False
        self._clear_voice_outputs(protected_keys)

    def _clear_voice_outputs(self, protected_keys: set[str]) -> None:
        if "audio_path" not in protected_keys:
            self.state["audio_path"] = ""
            self.artifacts.pop("audio", None)
        self._clear_digital_human_outputs(protected_keys)

    def _clear_digital_human_outputs(self, protected_keys: set[str]) -> None:
        if "digital_human_video_path" not in protected_keys:
            self.state["digital_human_video_path"] = ""
            self.artifacts.pop("digital_human_video", None)
        self._clear_final_outputs(protected_keys)

    def _clear_final_outputs(self, protected_keys: set[str]) -> None:
        if "final_video_path" not in protected_keys:
            self.state["final_video_path"] = ""
            self.artifacts.pop("final_video", None)
        if "cover_path" not in protected_keys:
            self.state["cover_path"] = ""
            self.artifacts.pop("cover", None)
        if "publish_package" not in protected_keys:
            self.state["publish_package"] = {}
        if "platform_suggestions" not in protected_keys:
            self.state["platform_suggestions"] = {}

    def _clear_cover_outputs(self, protected_keys: set[str]) -> None:
        if "cover_path" not in protected_keys:
            self.state["cover_path"] = ""
            self.artifacts.pop("cover", None)
        if "publish_package" not in protected_keys:
            self.state["publish_package"] = {}
        if "platform_suggestions" not in protected_keys:
            self.state["platform_suggestions"] = {}

    def set_notice(self, step: int, kind: str, message: str) -> None:
        self.notices[step] = {"kind": kind, "message": message}

    def set_error_notice(self, step: int, error: Exception) -> None:
        business_error = classify_ip_broadcast_error(error)
        self.notices[step] = {
            "kind": "error",
            "message": business_error.user_message,
            "technical_message": business_error.technical_message,
            "category": business_error.category,
            "retryable": str(business_error.retryable).lower(),
            "next_action": business_error.next_action,
        }

    def refresh_readiness(self) -> None:
        has_script = bool(self.state.get("final_script"))
        has_source_text = bool(self.state.get("source_text"))
        if self.state.get("source_mode") == "ip_learning" and not has_script:
            has_source_text = False
        has_confirmed_script = has_script and bool(self.state.get("copywriting_confirmed"))
        has_audio = _path_exists(self.state.get("audio_path", ""))
        has_digital_human = _path_exists(self.state.get("digital_human_video_path", ""))
        has_final_video = _path_exists(self.state.get("final_video_path", ""))

        if self.state.get("ip_learning_requires_topic_confirmation"):
            self.step_status[1] = "ready"
            self.step_status[2] = "pending"
            return

        if has_source_text or has_script:
            self.step_status[1] = "done"
        if has_confirmed_script:
            self.step_status[2] = "done"
        elif has_script or (has_source_text and self.step_status.get(2) == "pending"):
            self.step_status[2] = "ready"
        if has_confirmed_script and not has_audio and self.step_status.get(3) != "done":
            self.step_status[3] = "ready"
        if has_audio or has_final_video:
            self.step_status[3] = "done"
        if has_digital_human or has_final_video:
            self.step_status[4] = "done"
        elif has_audio and self._has_portrait():
            self.step_status[4] = "ready"
        if has_final_video:
            self.step_status[5] = "done"
            self.step_status[6] = "ready"
        elif has_digital_human:
            self.step_status[5] = "ready"

    def completed_steps(self) -> int:
        self.refresh_readiness()
        return sum(1 for status in self.step_status.values() if status == "done")

    def next_action(self) -> dict[str, Any]:
        self.refresh_readiness()
        has_script = bool(self.state.get("final_script"))
        has_source_text = bool(self.state.get("source_text"))
        if self.state.get("source_mode") == "ip_learning" and not has_script:
            has_source_text = False
        if _path_exists(self.state.get("final_video_path", "")):
            return {
                "key": STEP_PUBLISH,
                "step": 6,
                "label": "查看并下载",
                "description": "最终视频和发布素材已准备好",
                "disabled": False,
            }
        if self.state.get("ip_learning_requires_topic_confirmation"):
            return {
                "key": STEP_SOURCE,
                "step": 1,
                "label": "确认学习选题",
                "description": "已生成候选选题，请先确认一个选题再生成口播文案",
                "disabled": False,
            }
        if not has_source_text and not has_script:
            return {
                "key": STEP_SOURCE,
                "step": 1,
                "label": "生成口播文案",
                "description": "先选择素材来源并生成可用文案",
                "disabled": False,
            }
        if not has_script:
            return {
                "key": STEP_COPYWRITING,
                "step": 2,
                "label": "AI 改写/优化文案",
                "description": "已有来源文案，下一步确认最终口播稿",
                "disabled": False,
            }
        if not self.state.get("copywriting_confirmed"):
            return {
                "key": STEP_COPYWRITING,
                "step": 2,
                "label": "AI 改写/优化文案",
                "description": "先确认最终口播稿，再进入配音",
                "disabled": False,
            }
        if not _path_exists(self.state.get("audio_path", "")):
            return {
                "key": STEP_VOICE,
                "step": 3,
                "label": "生成语音",
                "description": "使用最终口播文案合成配音",
                "disabled": False,
            }
        if not self._has_portrait():
            return {
                "key": STEP_DIGITAL_HUMAN,
                "step": 4,
                "label": "选择数字人形象",
                "description": "先选择或上传一个数字人形象",
                "disabled": True,
            }
        if not _path_exists(self.state.get("digital_human_video_path", "")):
            return {
                "key": STEP_DIGITAL_HUMAN,
                "step": 4,
                "label": "生成数字人视频",
                "description": "使用形象和语音生成口播视频",
                "disabled": False,
            }
        if not _path_exists(self.state.get("final_video_path", "")):
            return {
                "key": STEP_POSTPRODUCTION,
                "step": 5,
                "label": "合成最终视频",
                "description": "添加字幕、音量和成片设置",
                "disabled": False,
            }
        return {
            "key": STEP_PUBLISH,
            "step": 6,
            "label": "查看并下载",
            "description": "最终视频和发布素材已准备好",
            "disabled": False,
        }

    def missing_requirements(self) -> list[str]:
        action = self.next_action()
        if self.state.get("ip_learning_requires_topic_confirmation"):
            return ["缺确认选题"]
        if action["key"] == STEP_SOURCE:
            return ["缺文案"]
        if action["key"] == STEP_VOICE:
            return ["缺语音"]
        if action["key"] == STEP_DIGITAL_HUMAN and action.get("disabled"):
            return ["缺形象"]
        if action["key"] == STEP_DIGITAL_HUMAN:
            return ["缺数字人视频"]
        if action["key"] == STEP_POSTPRODUCTION:
            return ["缺最终视频"]
        return []

    def to_response(self) -> dict[str, Any]:
        self.refresh_readiness()
        return {
            "session_id": self.session_id,
            "current_step": self.next_action()["step"],
            "completed_steps": self.completed_steps(),
            "next_action": self.next_action(),
            "missing_requirements": self.missing_requirements(),
            "step_status": self.step_status,
            "notices": self.notices,
            "artifacts": self.artifacts,
            "state": self.state,
        }

    def _has_portrait(self) -> bool:
        portrait_path = _resolve_v2_portrait_path(
            str(self.state.get("portrait_id") or ""),
            str(self.state.get("digital_human_scene_id") or ""),
            str(self.state.get("portrait_path") or ""),
        )
        return bool(portrait_path and Path(portrait_path).exists())


class IpBroadcastSessionStore:
    def __init__(self, store_path: str | Path | None = None):
        self._sessions: dict[str, IpBroadcastSession] = {}
        self._store_path = Path(store_path) if store_path else Path(get_data_path("ip_broadcast_sessions"))
        self._store_path.mkdir(parents=True, exist_ok=True)
        self._load_sessions()

    def create_session(self) -> IpBroadcastSession:
        session = IpBroadcastSession(session_id=uuid.uuid4().hex)
        self._sessions[session.session_id] = session
        self.save_session(session)
        return session

    def get_session(self, session_id: str) -> IpBroadcastSession | None:
        return self._sessions.get(session_id)

    def update_config(self, session_id: str, values: dict[str, Any]) -> IpBroadcastSession:
        session = self._sessions[session_id]
        session.update_config(values)
        self.save_session(session)
        return session

    def save_session(self, session: IpBroadcastSession) -> None:
        self._sessions[session.session_id] = session
        path = self._session_path(session.session_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(_session_to_payload(session), ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _load_sessions(self) -> None:
        for path in self._store_path.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                session = _session_from_payload(payload)
            except Exception as e:
                logger.warning(f"Failed to load IP broadcast session {path}: {e}")
                continue
            self._sessions[session.session_id] = session

    def _session_path(self, session_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)
        return self._store_path / f"{safe_id}.json"


def _session_to_payload(session: IpBroadcastSession) -> dict[str, Any]:
    return {
        "session_id": session.session_id,
        "state": session.state,
        "step_status": session.step_status,
        "notices": session.notices,
        "artifacts": session.artifacts,
    }


def _session_from_payload(payload: dict[str, Any]) -> IpBroadcastSession:
    state = _default_state()
    state.update(dict(payload.get("state") or {}))
    return IpBroadcastSession(
        session_id=str(payload["session_id"]),
        state=state,
        step_status={
            int(key): str(value)
            for key, value in dict(payload.get("step_status") or {}).items()
        } or {step: "pending" for step in range(1, 7)},
        notices={
            int(key): dict(value)
            for key, value in dict(payload.get("notices") or {}).items()
            if isinstance(value, dict)
        },
        artifacts={
            str(key): str(value)
            for key, value in dict(payload.get("artifacts") or {}).items()
            if value
        },
    )


async def run_ip_broadcast_step(
    pixelle_video,
    session: IpBroadcastSession,
    step_key: str,
) -> bool:
    step = STEP_KEYS.get(step_key)
    if not step:
        raise ValueError(f"Unknown IP broadcast step: {step_key}")
    session.step_status[step] = "running"
    try:
        if step_key == STEP_SOURCE:
            await _run_source(pixelle_video, session)
        elif step_key == STEP_COPYWRITING:
            await _run_copywriting(pixelle_video, session)
        elif step_key == STEP_VOICE:
            await _run_voice(pixelle_video, session)
        elif step_key == STEP_DIGITAL_HUMAN:
            await _run_digital_human(pixelle_video, session)
        elif step_key == STEP_POSTPRODUCTION:
            await _run_postproduction(pixelle_video, session)
        elif step_key == STEP_PUBLISH:
            await _run_publish(session)
        if step_key == STEP_SOURCE and session.state.get("ip_learning_requires_topic_confirmation"):
            session.step_status[step] = "ready"
            session.step_status[2] = "pending"
            session.set_notice(step, "info", "已生成候选选题，请先确认一个选题再生成口播文案。")
            session.refresh_readiness()
            return True
        session.step_status[step] = "done"
        session.set_notice(step, "success", "步骤执行完成")
        session.refresh_readiness()
        return True
    except Exception as e:
        session.step_status[step] = "error"
        session.set_error_notice(step, e)
        logger.exception(e)
        return False


async def _run_source(pixelle_video, session: IpBroadcastSession) -> None:
    source_mode = str(session.state.get("source_mode") or "paste")
    if source_mode == "video_extract":
        await _run_video_extract_source(session)
    elif source_mode == "industry_persona":
        await _run_industry_persona_source(pixelle_video, session)
    elif source_mode == "ip_learning":
        await _run_ip_learning_source(pixelle_video, session)
        if session.state.get("ip_learning_requires_topic_confirmation"):
            session.step_status[1] = "ready"
            session.step_status[2] = "pending"
            return
    else:
        await _run_paste_source(pixelle_video, session)
    session.step_status[1] = "done"
    session.step_status[2] = "ready"


async def _run_paste_source(pixelle_video, session: IpBroadcastSession) -> None:
    source_text = str(session.state.get("source_text", "")).strip()
    if not source_text:
        raise ValueError("请先提供素材文本")
    if pixelle_video:
        source_text = (
            await pixelle_video.llm(prompt=build_script_extraction_prompt(source_text))
        ).strip()
    session.state["source_text"] = source_text
    _set_source_script(session, source_text, "粘贴脚本")


async def _run_video_extract_source(session: IpBroadcastSession) -> None:
    video_input = str(
        session.state.get("video_input") or session.state.get("source_text") or ""
    ).strip()
    if not video_input:
        raise ValueError("请先输入视频链接或抖音分享文本")
    extractor = _build_script_extractor()
    script = (await extractor.extract(video_input)).strip()
    if not script:
        raise ValueError("没有提取到口播文案，请检查链接或手动粘贴文案")
    session.state["video_input"] = video_input
    session.state["source_text"] = script
    _set_source_script(session, script, "视频提取")


async def _run_industry_persona_source(pixelle_video, session: IpBroadcastSession) -> None:
    if pixelle_video is None:
        raise ValueError("行业+人设生成需要可用的 LLM 服务")
    industry_persona = str(session.state.get("industry_persona") or "").strip()
    selling_points = str(session.state.get("selling_points") or "").strip()
    target_customer = str(session.state.get("target_customer") or "").strip()
    conversion_phrase = str(session.state.get("conversion_phrase") or "").strip()
    other_reqs = str(session.state.get("other_reqs") or "").strip()
    if not any([industry_persona, selling_points, target_customer, conversion_phrase, other_reqs]):
        raise ValueError("请至少填写行业人设、核心卖点或目标客户")
    merged_reqs = "\n".join(
        item
        for item in [
            f"目标客户：{target_customer}" if target_customer else "",
            f"转化口令：{conversion_phrase}" if conversion_phrase else "",
            other_reqs,
        ]
        if item
    )
    script = (
        await pixelle_video.llm(
            prompt=build_ip_brain_generation_prompt(
                video_type=str(session.state.get("video_type") or "口播文案"),
                copy_type=str(session.state.get("copy_type") or "人设型"),
                industry_persona=industry_persona,
                selling_points=selling_points,
                other_reqs=merged_reqs,
                business_goal=str(session.state.get("business_goal_name") or ""),
                script_structure=_read_string_list(
                    session.state.get("business_script_structure")
                ),
                target_word_count=int(session.state.get("word_count") or 200),
                style_prompt=str(session.state.get("style_prompt") or ""),
                intent_note=str(session.state.get("business_intent_note") or ""),
            )
        )
    ).strip()
    session.state["source_text"] = script
    _set_source_script(session, script, "行业+人设")


async def _run_ip_learning_source(pixelle_video, session: IpBroadcastSession) -> None:
    if pixelle_video is None:
        raise ValueError("IP 学习需要可用的 LLM 服务")
    existing_scripts = session.state.get("ip_learning_scripts")
    existing_topics = session.state.get("ip_learning_topics")
    selected_topic = str(session.state.get("ip_learning_selected_topic") or "").strip()
    if selected_topic and isinstance(existing_scripts, list) and existing_scripts:
        viral_hint = "\n\n".join(
            str(item.get("script", "")) for item in existing_scripts if isinstance(item, dict)
        )[:1200]
        script = str(
            await pixelle_video.llm(prompt=build_script_from_topic_prompt(selected_topic, viral_hint))
        ).strip()
        session.state["ip_learning_requires_topic_confirmation"] = False
        session.state["source_text"] = script
        _set_source_script(session, script, "IP学习")
        return
    if isinstance(existing_scripts, list) and existing_scripts and isinstance(existing_topics, list) and existing_topics:
        session.state["ip_learning_requires_topic_confirmation"] = True
        session.state["final_script"] = ""
        session.state["source_text"] = ""
        session.state["source_label"] = ""
        session.state["copywriting_confirmed"] = False
        session._clear_voice_outputs(set())
        return

    video_inputs = parse_manual_video_inputs(str(session.state.get("ip_manual_video_links") or ""))
    if video_inputs:
        urls = video_inputs[:5]
    else:
        profile_url = str(
            session.state.get("ip_profile_url") or session.state.get("source_text") or ""
        ).strip()
        if not profile_url:
            raise ValueError("请先输入 IP 主页链接，或手动粘贴最近 5 条视频链接")
        urls = await fetch_latest_video_urls_from_profile(profile_url, limit=5)
    if not urls:
        raise ValueError("未抓取到视频链接，请手动粘贴最近 5 条视频链接继续学习")

    extractor = _build_script_extractor()
    results = await extract_many_video_scripts(extractor, urls, limit=5)
    scripts = [{"source": item.source, "script": item.script} for item in results if item.ok and item.script]
    errors = [{"source": item.source, "error": item.error} for item in results if not item.ok]
    if not scripts:
        raise ValueError("未能从这些视频中提取到可用口播文案，请检查链接或手动粘贴脚本")

    topics_result: HotTopicsResult = await pixelle_video.llm(
        prompt=build_hot_topics_from_viral_prompt("\n\n".join(item["script"] for item in scripts)),
        response_type=HotTopicsResult,
    )
    topics = topics_result.topics
    if not topics:
        raise ValueError("IP 学习未生成可用选题")

    session.state["ip_learning_video_urls"] = urls
    session.state["ip_learning_scripts"] = scripts
    session.state["ip_learning_errors"] = errors
    session.state["ip_learning_topics"] = topics
    session.state["ip_learning_summary"] = f"已提取 {len(scripts)} 条，失败 {len(errors)} 条"
    session.state["ip_learning_selected_topic"] = ""
    session.state["ip_learning_requires_topic_confirmation"] = True


def _set_source_script(session: IpBroadcastSession, script: str, label: str) -> None:
    session.state["final_script"] = script
    session.state["copywriting_confirmed"] = False
    session.state["source_label"] = label


def _build_script_extractor() -> VideoScriptExtractor:
    llm_cfg = config_manager.get_llm_config()
    return VideoScriptExtractor(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
    )


def _update_video_plan(session: IpBroadcastSession) -> None:
    plan = generate_video_plan(
        business_goal=str(session.state.get("business_goal_name") or ""),
        script=str(session.state.get("final_script") or ""),
        visual_strategy=str(session.state.get("business_visual_strategy") or ""),
        intent_note=str(session.state.get("business_intent_note") or ""),
    )
    session.state["video_plan"] = plan
    session.state["video_plan_status"] = plan.get("status", "empty")
    session.state["video_plan_applied"] = False


async def _run_copywriting(pixelle_video, session: IpBroadcastSession) -> None:
    source = str(
        session.state.get("final_script") or session.state.get("source_text") or ""
    ).strip()
    if not source:
        raise ValueError("请先生成或填写口播文案")
    style = session.state.get("style_prompt", "口语化、亲切自然、有感染力")
    word_count = int(session.state.get("word_count") or 200)
    output = await pixelle_video.llm(
        prompt=build_rewrite_prompt(
            source,
            style,
            word_count,
            business_goal=str(session.state.get("business_goal_name") or ""),
            script_structure=_read_string_list(session.state.get("business_script_structure")),
            intent_note=str(session.state.get("business_intent_note") or ""),
        )
    )
    session.state["final_script"] = _normalize_script_paragraphs(
        str(output),
        _read_string_list(session.state.get("business_script_structure")),
        source,
    )
    session.state["copywriting_confirmed"] = True
    _update_video_plan(session)


def _normalize_script_paragraphs(
    text: str,
    structure: list[str] | None = None,
    source_text: str = "",
) -> str:
    compact = "\n".join(line.strip() for line in str(text).splitlines() if line.strip())
    if "\n" in compact:
        return compact

    target_count = _target_paragraph_count(source_text, structure, compact)
    if target_count <= 1:
        return compact

    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?；;，,])", compact) if item.strip()]
    if len(sentences) < target_count:
        return _split_text_by_length(compact, target_count)

    target_count = min(target_count, len(sentences))
    groups: list[list[str]] = [[] for _ in range(target_count)]
    for index, sentence in enumerate(sentences):
        group_index = min(index * target_count // len(sentences), target_count - 1)
        groups[group_index].append(sentence)

    return "\n".join("".join(group).strip() for group in groups if group)


def _target_paragraph_count(
    source_text: str,
    structure: list[str] | None,
    output_text: str,
) -> int:
    source_lines = [line.strip() for line in str(source_text).splitlines() if line.strip()]
    if len(source_lines) >= 2:
        return min(max(len(source_lines), 2), 5)
    if structure:
        return min(max(len(structure), 2), 5)
    if len(output_text) > 90:
        return 3
    return 1


def _split_text_by_length(text: str, target_count: int) -> str:
    if target_count <= 1:
        return text
    chunk_size = max(1, len(text) // target_count)
    chunks: list[str] = []
    start = 0
    for index in range(target_count):
        if index == target_count - 1:
            chunks.append(text[start:].strip())
            break
        end = min(len(text), start + chunk_size)
        while end < len(text) and text[end] not in "，,。！？!?；;":
            end += 1
        if end < len(text):
            end += 1
        chunks.append(text[start:end].strip())
        start = end
    return "\n".join(chunk for chunk in chunks if chunk)


async def _run_voice(pixelle_video, session: IpBroadcastSession) -> None:
    text = str(session.state.get("final_script", "")).strip()
    if not text:
        raise ValueError("口播文案为空，无法生成语音")
    output_path = get_temp_path(f"ipb_audio_{uuid.uuid4().hex[:8]}.mp3")
    kwargs = {
        "text": text,
        "inference_mode": session.state.get("tts_inference_mode", "local"),
        "output_path": output_path,
    }
    _append_tts_params(kwargs, session.state)
    audio_path = await pixelle_video.tts(**kwargs)
    session.state["audio_path"] = audio_path
    session.artifacts["audio"] = audio_path


def _append_tts_params(kwargs: dict[str, Any], state: dict[str, Any]) -> None:
    if kwargs["inference_mode"] == "local":
        kwargs["voice"] = state.get("tts_voice")
        kwargs["speed"] = state.get("tts_speed")
        kwargs["pitch"] = state.get("tts_pitch")
        kwargs["volume"] = state.get("tts_volume")
        return

    workflow = str(state.get("tts_workflow") or "")
    if workflow:
        kwargs["workflow"] = workflow

    workflow_kind = _tts_workflow_kind(workflow)
    if workflow_kind == "edge":
        kwargs["voice"] = state.get("tts_workflow_voice", "[Chinese] zh-CN Yunjian")
        kwargs["speed"] = float(state.get("tts_workflow_speed", 1.0))
        kwargs["pitch"] = int(state.get("tts_workflow_pitch", 0))
    elif workflow_kind == "spark":
        kwargs["gender"] = state.get("tts_spark_gender", "male")
        kwargs["speed"] = state.get("tts_spark_speed", "moderate")
        kwargs["pitch"] = state.get("tts_spark_pitch", "moderate")
        kwargs["temperature"] = float(state.get("tts_temperature", 0.8))
        kwargs["top_k"] = int(state.get("tts_top_k", 30))
        kwargs["top_p"] = float(state.get("tts_top_p", 0.9))
        kwargs["max_new_tokens"] = int(state.get("tts_max_new_tokens", 3000))
        kwargs["do_sample"] = bool(state.get("tts_do_sample", True))
        _append_tts_seed(kwargs, state)
    elif workflow_kind == "index":
        ref_audio = _resolve_v2_audio_path(
            str(state.get("tts_ref_audio_id") or ""),
            str(state.get("tts_ref_audio_path") or ""),
        )
        if ref_audio:
            kwargs["ref_audio"] = ref_audio
        kwargs["mode"] = state.get("tts_index_mode", "Auto")
        kwargs["do_sample_mode"] = state.get("tts_index_do_sample_mode", "on")
        kwargs["temperature"] = float(state.get("tts_temperature", 0.8))
        kwargs["top_p"] = float(state.get("tts_top_p", 0.9))
        kwargs["top_k"] = int(state.get("tts_top_k", 30))
        kwargs["num_beams"] = int(state.get("tts_num_beams", 3))
        kwargs["repetition_penalty"] = float(state.get("tts_repetition_penalty", 10.0))
        kwargs["length_penalty"] = float(state.get("tts_length_penalty", 0.0))
        kwargs["max_mel_tokens"] = min(
            int(state.get("tts_max_mel_tokens", INDEX_TTS_MAX_MEL_TOKENS_LIMIT)),
            INDEX_TTS_MAX_MEL_TOKENS_LIMIT,
        )
        kwargs["max_tokens_per_sentence"] = int(state.get("tts_max_tokens_per_sentence", 120))
        _append_tts_seed(kwargs, state)
    else:
        ref_audio = _resolve_v2_audio_path(
            str(state.get("tts_ref_audio_id") or ""),
            str(state.get("tts_ref_audio_path") or ""),
        )
        if ref_audio:
            kwargs["ref_audio"] = ref_audio


def _append_tts_seed(kwargs: dict[str, Any], state: dict[str, Any]) -> None:
    seed = int(state.get("tts_seed") or 0)
    if seed > 0:
        kwargs["seed"] = seed


def _tts_workflow_kind(workflow: str) -> str:
    workflow_name = (workflow or "").lower()
    if "spark" in workflow_name:
        return "spark"
    if "index" in workflow_name:
        return "index"
    if "edge" in workflow_name:
        return "edge"
    return "generic"


async def _run_digital_human(pixelle_video, session: IpBroadcastSession) -> None:
    audio_path = session.state.get("audio_path", "")
    portrait_path = _resolve_v2_portrait_path(
        str(session.state.get("portrait_id") or ""),
        str(session.state.get("digital_human_scene_id") or ""),
        str(session.state.get("portrait_path") or ""),
    )
    workflow = session.state.get("digital_human_workflow")
    if not _path_exists(audio_path):
        raise ValueError("语音文件不存在，请先生成语音")
    if not _path_exists(portrait_path):
        raise ValueError("形象文件不存在，请先选择或上传形象")
    _validate_portrait_media_type(workflow, session.state.get("portrait_media_type", ""))
    output_path = get_temp_path(f"ipb_dh_{uuid.uuid4().hex[:8]}.mp4")
    video_path = await pixelle_video.digital_human.generate(
        portrait_path=portrait_path,
        audio_path=audio_path,
        output_path=output_path,
        workflow=workflow,
        duration=float(session.state.get("digital_human_duration") or 0.0),
        prompt=session.state.get("digital_human_prompt") or "",
        width=int(session.state.get("digital_human_width") or 720),
        height=int(session.state.get("digital_human_height") or 1280),
    )
    session.state["digital_human_video_path"] = video_path
    session.artifacts["digital_human_video"] = video_path


async def _run_postproduction(pixelle_video, session: IpBroadcastSession) -> None:
    audio_path = session.state.get("audio_path", "")
    dh_video = session.state.get("digital_human_video_path", "")
    if not _path_exists(audio_path):
        raise ValueError("语音文件不存在，无法合成最终视频")
    if not _path_exists(dh_video):
        raise ValueError("数字人视频不存在，无法合成最终视频")

    _record_media_usage_and_snapshots(session)

    uid = uuid.uuid4().hex[:8]
    working_audio = audio_path
    if session.state.get("remove_silence"):
        working_audio = remove_silence(audio_path, get_temp_path(f"ipb_clean_{uid}.mp3"))

    final = get_output_path(f"ipb_{uid}_final.mp4")
    # All currently shipped templates are authored on this canvas.  Keep the
    # state fields as descriptive metadata, but do not let an old client
    # reintroduce the 720x1280 render coordinate system.
    canvas_width = CANVAS_WIDTH
    canvas_height = CANVAS_HEIGHT
    normalized_dh = get_temp_path(f"ipb_{uid}_canvas.mp4")
    geometry_normalized = False
    try:
        normalize_video_to_canvas(
            dh_video,
            normalized_dh,
            width=canvas_width,
            height=canvas_height,
        )
        geometry_normalized = True
    except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
        # Keep unit/integration fakes and already-probed provider outputs
        # usable, while real media always takes the canonical path above.
        logger.warning("视频画布标准化失败，将使用原始视频继续：{}", exc)
        normalized_dh = dh_video

    cover_source = ""
    if session.state.get("overlay_enabled") and session.state.get("visual_groups"):
        clean_cover_source = get_temp_path(f"ipb_{uid}_visual.mp4")
        compose_ip_broadcast_video(
            base_video=normalized_dh,
            audio_path=working_audio,
            output_path=final,
            script=session.state.get("final_script", ""),
            story_segments=session.state.get("story_segments") or [],
            visual_groups=session.state.get("visual_groups") or [],
            template_id=session.state.get("template_id"),
            subtitle_style=session.state.get("subtitle_style"),
            subtitle_enabled=bool(session.state.get("subtitle_enabled", True)),
            width=canvas_width,
            height=canvas_height,
            clean_output_path=clean_cover_source,
        )
        cover_source = clean_cover_source
    else:
        merged = merge_audio_into_video(
            normalized_dh,
            working_audio,
            get_temp_path(f"ipb_merged_{uid}.mp4"),
        )
        cover_source = merged
        if session.state.get("subtitle_enabled", True) and session.state.get("final_script"):
            template = get_ip_broadcast_template_for_render(session.state.get("template_id"))
            force_style = build_ass_force_style(
                template,
                session.state.get("subtitle_style"),
                video_width=canvas_width,
                video_height=canvas_height if geometry_normalized else int(
                    session.state.get("digital_human_height") or 1280
                ),
            )
            render_script = wrap_template_subtitle_text(
                session.state["final_script"],
                template,
                video_width=canvas_width,
                video_height=canvas_height if geometry_normalized else int(session.state.get("digital_human_height") or 1280),
            )
            try:
                ass = get_temp_path(f"ipb_{uid}.ass")
                generate_ass(
                    render_script,
                    working_audio,
                    ass,
                    play_res_x=canvas_width,
                    play_res_y=canvas_height,
                    force_style=force_style,
                )
                _embed_subtitles_compat(
                    merged,
                    ass,
                    final,
                    force_style=force_style,
                )
            except (OSError, TypeError, ValueError, subprocess.CalledProcessError) as exc:
                # Preserve the existing SRT seam for test doubles and old
                # provider artifacts that do not expose probeable media.
                logger.warning("ASS 字幕生成失败，回退 SRT：{}", exc)
                srt = get_temp_path(f"ipb_{uid}.srt")
                generate_srt(render_script, working_audio, srt)
                _embed_subtitles_compat(merged, srt, final, force_style=force_style)
        else:
            shutil.copy2(merged, final)

    final = _mix_bgm_if_needed(final, session, uid)
    if not geometry_normalized or not cover_source or not Path(cover_source).exists():
        # Invalid/fake media has no reliable clean frame.  Real media always
        # reaches the branch above and therefore never reuses burned captions.
        cover_source = final
    session.state["final_video_path"] = final
    session.artifacts["final_video"] = final
    _populate_publish_metadata(session)
    await _ensure_template_cover(session, cover_source, uid)
    await _run_publish(session)


def _embed_subtitles_compat(
    input_path: str,
    subtitle_path: str,
    output_path: str,
    *,
    force_style: str,
) -> str:
    """Keep old provider/test doubles working while passing bundled fonts."""
    kwargs: dict[str, Any] = {"force_style": force_style}
    if "fontsdir" in inspect.signature(embed_subtitles).parameters:
        kwargs["fontsdir"] = resolve_ip_broadcast_fonts_dir()
    return embed_subtitles(input_path, subtitle_path, output_path, **kwargs)


def _record_media_usage_and_snapshots(session: IpBroadcastSession) -> None:
    """Account for V2 media references at the render boundary.

    Legacy overlay groups continue to use their absolute compatibility path;
    only stable V2 asset IDs are recorded in the new usage/snapshot ledger.
    """
    try:
        from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

        repository = AssetLibraryRepository()
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("V2 media ledger unavailable; continuing with legacy render: {}", exc)
        return
    references: list[dict[str, Any]] = []
    # Domain resources are pinned together with media so a rerender uses the
    # same voice, digital-human, brand and template revisions selected in the
    # production flow.
    domain_refs = (
        ("voice", str(session.state.get("tts_ref_audio_id") or ""), STEP_VOICE, "reference", "voice-reference"),
        ("digital_human", str(session.state.get("portrait_id") or ""), STEP_DIGITAL_HUMAN, "portrait", "digital-human"),
        ("brand", str(session.state.get("brand_kit_id") or ""), STEP_POSTPRODUCTION, "brand_kit", "brand"),
        ("audio", str(session.state.get("brand_bgm_asset_id") or ""), STEP_POSTPRODUCTION, "brand_bgm", "brand-bgm"),
        ("audio", str(session.state.get("bgm_asset_id") or ""), STEP_POSTPRODUCTION, "bgm", "bgm"),
        ("template", str(session.state.get("template_id") or ""), STEP_POSTPRODUCTION, "template", "template"),
    )
    for resource_kind, resource_id, step, purpose, slot_id in domain_refs:
        if resource_id:
            references.append({"resource_kind": resource_kind, "resource_id": resource_id, "step": step, "purpose": purpose, "slot_id": slot_id})
    scene_id = str(session.state.get("digital_human_scene_id") or "").strip()
    if scene_id:
        references.append({"resource_kind": "digital_human_scene", "resource_id": scene_id, "step": STEP_DIGITAL_HUMAN, "purpose": "scene", "slot_id": "digital-human-scene"})
    groups = session.state.get("visual_groups") or []
    if not isinstance(groups, list):
        groups = []
    template_contract = repository.get_template_revision(str(session.state.get("template_id") or ""))
    for index, group in enumerate(groups, start=1):
        if not isinstance(group, dict):
            continue
        visual_type = str(group.get("visual_type") or "")
        if visual_type == "uploaded_video":
            resource_kind = "video"
            asset_id = str(group.get("video_asset_id") or "").strip()
            purpose = "overlay_video"
        elif visual_type == "uploaded_image":
            resource_kind = "image"
            asset_id = str(group.get("image_asset_id") or "").strip()
            purpose = "overlay_image"
        else:
            continue
        if not asset_id or not repository.get_asset(asset_id):
            continue
        slot_id = str(group.get("group_id") or f"overlay-{index}")
        references.append({"resource_kind": resource_kind, "resource_id": asset_id, "step": STEP_POSTPRODUCTION, "purpose": purpose, "slot_id": slot_id})
    repository.reconcile_session_usage(session.session_id, references)

    snapshot_ids: list[str] = []
    for reference in references:
        resource_kind = reference["resource_kind"]
        resource_id = reference["resource_id"]
        step = reference["step"]
        if resource_kind in {"image", "video", "audio"}:
            snapshot = repository.create_snapshot(
                resource_id,
                session.session_id,
                step,
                template_revision=int(template_contract.get("revision") or 1) if template_contract else 1,
                renderer_version=(template_contract or {}).get("renderer_version") or "ip-broadcast-composer-v2",
            )
        else:
            template_revision = int(template_contract.get("revision") or 1) if resource_kind == "template" and template_contract else None
            renderer_version = (template_contract or {}).get("renderer_version") if resource_kind == "template" else None
            snapshot = repository.create_external_snapshot(
                resource_kind,
                resource_id,
                session.session_id,
                step,
                template_revision=template_revision,
                renderer_version=renderer_version,
                metadata=repository.domain_snapshot_metadata(resource_kind, resource_id),
            )
        if snapshot:
            snapshot_ids.append(snapshot["snapshot_id"])
    session.state["resource_snapshot_ids"] = snapshot_ids


def _mix_bgm_if_needed(video_path: str, session: IpBroadcastSession, uid: str) -> str:
    bgm_path = _resolve_v2_audio_path(
        str(session.state.get("bgm_asset_id") or session.state.get("brand_bgm_asset_id") or ""),
        str(session.state.get("bgm_path") or ""),
    )
    if not bgm_path or not Path(bgm_path).exists():
        return video_path
    output_path = get_output_path(f"ipb_{uid}_final_bgm.mp4")
    subprocess.run(
        _build_bgm_mix_command(
            video_path=video_path,
            bgm_path=bgm_path,
            output_path=output_path,
            bgm_volume=float(session.state.get("bgm_volume") or 0.3),
            voice_volume=float(session.state.get("voice_volume") or 1.0),
        ),
        check=True,
        capture_output=True,
    )
    return output_path


def _build_bgm_mix_command(
    video_path: str,
    bgm_path: str,
    output_path: str,
    bgm_volume: float,
    voice_volume: float,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        video_path,
        "-stream_loop",
        "-1",
        "-i",
        bgm_path,
        "-filter_complex",
        (
            f"[0:a]volume={voice_volume}[voice];"
            f"[1:a]volume={bgm_volume}[bgm];"
            "[voice][bgm]amix=inputs=2:duration=first[aout]"
        ),
        "-map",
        "0:v",
        "-map",
        "[aout]",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        output_path,
    ]


async def _ensure_template_cover(
    session: IpBroadcastSession,
    cover_source: str,
    uid: str,
) -> None:
    if session.state.get("cover_path") and Path(str(session.state["cover_path"])).exists():
        session.artifacts["cover"] = str(session.state["cover_path"])
        return
    if not cover_source or not Path(cover_source).exists():
        return
    first_frame = get_temp_path(f"ipb_cover_bg_{uid}.png")
    extract_first_frame(cover_source, first_frame)
    cover_path = get_temp_path(f"ipb_cover_{uid}.png")
    session.state["cover_path"] = await render_ip_broadcast_cover(
        template_id=str(session.state.get("template_id") or ""),
        title=_build_cover_title(session),
        subtitle=str(session.state.get("description") or "")[:80],
        background=first_frame,
        output_path=cover_path,
    )
    session.artifacts["cover"] = session.state["cover_path"]


async def _run_publish(session: IpBroadcastSession) -> None:
    _populate_publish_metadata(session)
    if session.state.get("final_video_path"):
        session.artifacts["final_video"] = session.state["final_video_path"]
    if session.state.get("cover_path"):
        session.artifacts["cover"] = session.state["cover_path"]
    _write_publish_package(session)


def _populate_publish_metadata(session: IpBroadcastSession) -> None:
    """Fill metadata before cover rendering so title/description stay in sync."""
    script = str(session.state.get("final_script", "")).strip()
    if not session.state.get("title"):
        session.state["title"] = _shorten_title(script)
    if not session.state.get("description"):
        session.state["description"] = script[:180]
    if not session.state.get("hashtags"):
        session.state["hashtags"] = _build_default_hashtags(
            str(session.state.get("business_goal_name") or "")
        )


def _write_publish_package(session: IpBroadcastSession) -> None:
    script = str(session.state.get("final_script", "")).strip()
    preferred_platforms = _read_string_list(session.state.get("business_publish_platforms"))
    hashtags = session.state.get("hashtags") or _build_default_hashtags(
        str(session.state.get("business_goal_name") or "")
    )
    package = {
        "video_path": session.state.get("final_video_path", ""),
        "cover_path": session.state.get("cover_path", ""),
        "title": session.state.get("title", ""),
        "description": session.state.get("description", ""),
        "cover_title": _build_cover_title(session),
        "comment_cta": _build_comment_cta(str(session.state.get("business_goal_name") or "")),
        "hashtags": hashtags,
        "preferred_platforms": preferred_platforms,
        "script": script,
        "script_summary": script[:80],
        "platform_suggestions": _build_platform_suggestions(
            session.state.get("title", ""),
            session.state.get("description", ""),
            hashtags,
            preferred_platforms=preferred_platforms,
        ),
    }
    session.state["publish_package"] = package
    session.state["platform_suggestions"] = package["platform_suggestions"]
    session.state["script_summary"] = package["script_summary"]

    uid = session.session_id[:8]
    script_path = get_output_path(f"ipb_{uid}_script.txt")
    package_path = get_output_path(f"ipb_{uid}_publish_package.json")
    Path(script_path).write_text(script, encoding="utf-8")
    Path(package_path).write_text(
        json.dumps(package, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    session.artifacts["script"] = script_path
    session.artifacts["publish_package_json"] = package_path


def _build_platform_suggestions(
    title: str,
    description: str,
    hashtags: list[str],
    preferred_platforms: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    tag_text = " ".join(f"#{tag}" for tag in hashtags)
    suggestions = {
        "douyin": {
            "title": title[:55],
            "description": f"{description}\n{tag_text}".strip(),
            "hashtags": hashtags,
        },
        "xiaohongshu": {
            "title": title[:20],
            "description": f"{description}\n\n{tag_text}".strip(),
            "hashtags": hashtags,
        },
        "shipinhao": {
            "title": title[:30],
            "description": description,
            "hashtags": hashtags,
        },
        "kuaishou": {
            "title": title[:40],
            "description": f"{description} {tag_text}".strip(),
            "hashtags": hashtags,
        },
    }
    ordered_keys = [
        key for key in (preferred_platforms or []) if key in suggestions
    ] + [key for key in suggestions if key not in (preferred_platforms or [])]
    return {key: suggestions[key] for key in ordered_keys}


def _build_default_hashtags(business_goal: str) -> list[str]:
    hashtags = ["老板口播", "IP口播"]
    goal_tags = {
        "团购转化": ["团购套餐", "到店优惠"],
        "门店探店": ["本地生活", "探店推荐"],
        "新品推荐": ["新品推荐", "门店新品"],
        "老板人设": ["老板口播", "经营经验"],
        "客户案例": ["客户案例", "真实反馈"],
    }
    for tag in goal_tags.get(business_goal, []):
        if tag not in hashtags:
            hashtags.append(tag)
    return hashtags


def _build_cover_title(session: IpBroadcastSession) -> str:
    explicit = str(session.state.get("cover_title") or "").strip()
    if explicit:
        return explicit
    return str(session.state.get("title") or "").strip() or _shorten_title(
        str(session.state.get("final_script") or "")
    )


def _build_comment_cta(business_goal: str) -> str:
    if business_goal == "团购转化":
        return "想了解套餐详情，评论区打“套餐”。"
    if business_goal == "门店探店":
        return "想知道门店地址，评论区打“位置”。"
    if business_goal == "新品推荐":
        return "想了解新品详情，评论区打“新品”。"
    if business_goal == "客户案例":
        return "想看更多真实案例，评论区打“案例”。"
    return "想了解更多，评论区留言。"


def _read_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _validate_portrait_media_type(workflow: str | None, media_type: str) -> None:
    if not workflow:
        return
    config = _load_workflow_config(workflow)
    required = config.get("ip_broadcast", {}).get("portrait_media_type")
    if not required or required == "any":
        return
    if media_type and media_type != required:
        label = "视频形象" if required == "video" else "图片形象"
        raise ValueError(f"当前数字人工作流只支持{label}")


def _shorten_title(script: str) -> str:
    compact = " ".join(script.split())
    return compact[:40] or "老板IP口播"


def _path_exists(value: str) -> bool:
    return bool(value and Path(value).exists())


def _resolve_v2_audio_path(resource_id: str, fallback: str) -> str:
    """Resolve a V2 voice reference to a local path at provider boundary."""
    if resource_id:
        try:
            from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

            repository = AssetLibraryRepository()
            asset = repository.get_asset(resource_id) or repository.get_asset_by_legacy_id("audio", resource_id)
            if asset is None:
                # The production picker stores the stable VoiceProfile ID. The
                # profile owns the audio revision, so resolve through the
                # domain projection before falling back to legacy IDs.
                profile = repository.get_domain_item("voice", resource_id)
                profile_asset_id = str((profile or {}).get("asset_id") or "")
                if profile_asset_id:
                    asset = repository.get_asset(profile_asset_id)
            path = repository.get_revision_path(asset["asset_id"]) if asset else None
            if path:
                return str(path)
        except (OSError, RuntimeError, ValueError) as exc:
            logger.warning("Unable to resolve V2 voice reference {}: {}", resource_id, exc)
    return fallback


def _resolve_v2_portrait_path(profile_id: str, scene_id: str, fallback: str) -> str:
    """Resolve a V2 digital-human profile/scene to its pinned local source."""
    try:
        from pixelle_video.services.assets_v2.repository import AssetLibraryRepository

        repository = AssetLibraryRepository()
        if scene_id:
            scene_path = repository.get_scene_source_path(scene_id)
            if scene_path:
                return str(scene_path)
        if profile_id:
            profile_path = repository.get_profile_source_path(profile_id)
            if profile_path:
                return str(profile_path)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("Unable to resolve V2 digital-human {} / {}: {}", profile_id, scene_id, exc)
    return fallback
