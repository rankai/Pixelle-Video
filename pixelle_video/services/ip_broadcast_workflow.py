"""Streamlit-free IP broadcast workflow state and step execution."""

from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from pixelle_video.prompts.ip_broadcast import build_rewrite_prompt
from pixelle_video.services.digital_human_service import _load_workflow_config
from pixelle_video.services.ip_broadcast_templates import (
    build_ass_force_style,
    get_ip_broadcast_template,
)
from pixelle_video.services.subtitle_service import (
    embed_subtitles,
    generate_srt,
    merge_audio_into_video,
    remove_silence,
)
from pixelle_video.utils.os_util import get_output_path, get_temp_path

STEP_SOURCE = "source"
STEP_COPYWRITING = "copywriting"
STEP_VOICE = "voice"
STEP_DIGITAL_HUMAN = "digital_human"
STEP_POSTPRODUCTION = "postproduction"
STEP_PUBLISH = "publish"

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
        "source_mode": "paste",
        "source_text": "",
        "source_label": "",
        "style_prompt": "口语化、亲切自然、有感染力",
        "word_count": 200,
        "final_script": "",
        "tts_inference_mode": "local",
        "tts_voice": "zh-CN-YunjianNeural",
        "tts_speed": 1.2,
        "tts_pitch": 0,
        "tts_volume": 0,
        "tts_workflow": "",
        "tts_ref_audio_path": "",
        "audio_path": "",
        "portrait_id": "",
        "portrait_path": "",
        "portrait_media_type": "",
        "digital_human_workflow": "workflows/runninghub/digital_combination.json",
        "digital_human_prompt": "自然口播，正面镜头，表情稳定，唇形同步",
        "digital_human_duration": 0.0,
        "digital_human_width": 720,
        "digital_human_height": 1280,
        "digital_human_video_path": "",
        "template_id": "boss_clean",
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
        self.state.update(values)
        self.refresh_readiness()

    def set_notice(self, step: int, kind: str, message: str) -> None:
        self.notices[step] = {"kind": kind, "message": message}

    def refresh_readiness(self) -> None:
        has_script = bool(self.state.get("final_script"))
        has_audio = _path_exists(self.state.get("audio_path", ""))
        has_digital_human = _path_exists(self.state.get("digital_human_video_path", ""))
        has_final_video = _path_exists(self.state.get("final_video_path", ""))

        if self.state.get("source_text") or has_script:
            self.step_status[1] = "done"
        if has_script:
            self.step_status[2] = "done"
        elif self.state.get("source_text") and self.step_status.get(2) == "pending":
            self.step_status[2] = "ready"
        if has_script and not has_audio and self.step_status.get(3) != "done":
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
        if not self.state.get("source_text") and not self.state.get("final_script"):
            return {
                "key": STEP_SOURCE,
                "step": 1,
                "label": "生成口播文案",
                "description": "先选择素材来源并生成可用文案",
                "disabled": False,
            }
        if not self.state.get("final_script"):
            return {
                "key": STEP_COPYWRITING,
                "step": 2,
                "label": "AI 改写/优化文案",
                "description": "已有来源文案，下一步确认最终口播稿",
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
        portrait_path = self.state.get("portrait_path", "")
        return bool(portrait_path and Path(portrait_path).exists())


class IpBroadcastSessionStore:
    def __init__(self):
        self._sessions: dict[str, IpBroadcastSession] = {}

    def create_session(self) -> IpBroadcastSession:
        session = IpBroadcastSession(session_id=uuid.uuid4().hex)
        self._sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> IpBroadcastSession | None:
        return self._sessions.get(session_id)

    def update_config(self, session_id: str, values: dict[str, Any]) -> IpBroadcastSession:
        session = self._sessions[session_id]
        session.update_config(values)
        return session


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
            await _run_source(session)
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
        session.step_status[step] = "done"
        session.set_notice(step, "success", "步骤执行完成")
        session.refresh_readiness()
        return True
    except Exception as e:
        session.step_status[step] = "error"
        session.set_notice(step, "error", str(e))
        logger.exception(e)
        return False


async def _run_source(session: IpBroadcastSession) -> None:
    source_text = str(session.state.get("source_text", "")).strip()
    if not source_text:
        raise ValueError("请先提供素材文本")
    session.state["final_script"] = source_text
    session.state["source_label"] = session.state.get("source_mode") or "素材来源"
    session.step_status[1] = "done"
    session.step_status[2] = "done"


async def _run_copywriting(pixelle_video, session: IpBroadcastSession) -> None:
    source = str(
        session.state.get("final_script") or session.state.get("source_text") or ""
    ).strip()
    if not source:
        raise ValueError("请先生成或填写口播文案")
    style = session.state.get("style_prompt", "口语化、亲切自然、有感染力")
    word_count = int(session.state.get("word_count") or 200)
    output = await pixelle_video.llm(prompt=build_rewrite_prompt(source, style, word_count))
    session.state["final_script"] = output


async def _run_voice(pixelle_video, session: IpBroadcastSession) -> None:
    text = str(session.state.get("final_script", "")).strip()
    if not text:
        raise ValueError("口播文案为空，无法生成语音")
    output_path = get_temp_path(f"ipb_audio_{uuid.uuid4().hex[:8]}.mp3")
    kwargs = {
        "text": text,
        "inference_mode": session.state.get("tts_inference_mode", "local"),
        "voice": session.state.get("tts_voice"),
        "speed": session.state.get("tts_speed"),
        "pitch": session.state.get("tts_pitch"),
        "volume": session.state.get("tts_volume"),
        "output_path": output_path,
    }
    if session.state.get("tts_workflow"):
        kwargs["workflow"] = session.state["tts_workflow"]
    if session.state.get("tts_ref_audio_path"):
        kwargs["ref_audio"] = session.state["tts_ref_audio_path"]
    audio_path = await pixelle_video.tts(**kwargs)
    session.state["audio_path"] = audio_path
    session.artifacts["audio"] = audio_path


async def _run_digital_human(pixelle_video, session: IpBroadcastSession) -> None:
    audio_path = session.state.get("audio_path", "")
    portrait_path = session.state.get("portrait_path", "")
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

    uid = uuid.uuid4().hex[:8]
    working_audio = audio_path
    if session.state.get("remove_silence"):
        working_audio = remove_silence(audio_path, get_temp_path(f"ipb_clean_{uid}.mp3"))

    merged = merge_audio_into_video(
        dh_video,
        working_audio,
        get_temp_path(f"ipb_merged_{uid}.mp4"),
    )
    final = get_output_path(f"ipb_{uid}_final.mp4")
    if session.state.get("subtitle_enabled", True) and session.state.get("final_script"):
        srt = get_temp_path(f"ipb_{uid}.srt")
        generate_srt(session.state["final_script"], working_audio, srt)
        template = get_ip_broadcast_template(session.state.get("template_id"))
        embed_subtitles(merged, srt, final, force_style=build_ass_force_style(template))
    else:
        shutil.copy2(merged, final)

    session.state["final_video_path"] = final
    session.artifacts["final_video"] = final
    await _run_publish(session)


async def _run_publish(session: IpBroadcastSession) -> None:
    script = str(session.state.get("final_script", "")).strip()
    if not session.state.get("title"):
        session.state["title"] = _shorten_title(script)
    if not session.state.get("description"):
        session.state["description"] = script[:180]
    if not session.state.get("hashtags"):
        session.state["hashtags"] = ["老板口播", "IP口播"]
    if session.state.get("final_video_path"):
        session.artifacts["final_video"] = session.state["final_video_path"]
    if session.state.get("cover_path"):
        session.artifacts["cover"] = session.state["cover_path"]


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
