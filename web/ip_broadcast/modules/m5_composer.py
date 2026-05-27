import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger

from pixelle_video.services.digital_human_service import _save_video_output
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
from pixelle_video.services.video import VideoService
from pixelle_video.utils.os_util import get_output_path, get_temp_path
from web.ip_broadcast.modules.m5_overlay_planning import (
    estimate_overlay_timeline,
    normalize_overlay_type,
)
from web.ip_broadcast.modules.m5_publish_assets import (
    ensure_publish_assets,
    ensure_publish_assets_async,
)
from web.ip_broadcast.state import set_step_status
from web.ip_broadcast.status_ui import (
    hide_global_loading,
    set_step_notice,
    show_global_loading,
)
from web.utils.async_helpers import run_async
from web.utils.streamlit_helpers import safe_rerun


def build_bgm_mix_command(
    merged_video: str,
    bgm_path: str,
    output_path: str,
    bgm_volume: float,
    voice_volume: float,
) -> list[str]:
    """Build FFmpeg command that keeps output duration bounded by the source video."""
    return [
        "ffmpeg",
        "-y",
        "-i",
        merged_video,
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
        "-shortest",
        output_path,
    ]


def run_postproduction(pixelle_video) -> None:
    set_step_status(5, "running")
    loading = show_global_loading("正在合成最终视频，请稍候...")
    progress = st.progress(0, text="准备中...")
    try:
        uid = uuid.uuid4().hex[:8]
        progress.progress(10, text="处理音频...")
        audio = _prepare_audio(uid)

        progress.progress(30, text="合并音视频...")
        merged = _merge_voice_with_video(audio, uid)

        if overlay_enabled():
            progress.progress(42, text="叠加覆盖画面...")
            merged = run_async(apply_overlay_plan_async(pixelle_video, merged, audio, uid))

        merged = _mix_bgm_if_needed(merged, uid, progress)

        progress.progress(70, text="生成字幕...")
        final = _write_final_video(merged, audio, uid, progress)

        progress.progress(92, text="生成发布素材...")
        ensure_publish_assets(pixelle_video, final)
        progress.progress(100, text="完成！")
        st.session_state.ipb_m5_final_video_path = final
        set_step_status(5, "done")
        set_step_notice(5, "success", "视频合成完成")
        safe_rerun()
    except Exception as e:
        set_step_notice(5, "error", str(e))
        st.error(str(e))
        logger.exception(e)
        set_step_status(5, "error")
        progress.empty()
    finally:
        hide_global_loading(loading)


async def run_m5(pixelle_video) -> bool:
    uid = uuid.uuid4().hex[:8]
    try:
        dh_video = st.session_state.get("ipb_m4_dh_video_path", "")
        audio_src = st.session_state.get("ipb_m3_audio_path", "")
        if not dh_video or not audio_src:
            return False

        audio = _prepare_audio(uid)
        merged = _merge_voice_with_video(audio, uid)

        if overlay_enabled():
            merged = await apply_overlay_plan_async(pixelle_video, merged, audio, uid)

        merged = _mix_bgm_if_needed(merged, uid)
        final = _write_final_video(merged, audio, uid)

        await ensure_publish_assets_async(pixelle_video, final)
        st.session_state.ipb_m5_final_video_path = final
        set_step_status(5, "done")
        return True
    except Exception as e:
        logger.exception(e)
        set_step_status(5, "error")
        set_step_notice(5, "error", str(e))
        return False


def _prepare_audio(uid: str) -> str:
    audio = st.session_state.get("ipb_m3_audio_path", "")
    if st.session_state.get("ipb_m5_remove_silence", False):
        cleaned = get_temp_path(f"ipb_clean_{uid}.mp3")
        audio = remove_silence(audio, cleaned)
    return audio


def _merge_voice_with_video(audio: str, uid: str) -> str:
    dh_video = st.session_state.get("ipb_m4_dh_video_path", "")
    merged = get_temp_path(f"ipb_merged_{uid}.mp4")
    return merge_audio_into_video(dh_video, audio, merged)


def _mix_bgm_if_needed(merged: str, uid: str, progress=None) -> str:
    bgm_path = st.session_state.get("ipb_m5_bgm_path", "")
    if not bgm_path or not Path(bgm_path).exists():
        return merged
    if progress:
        progress.progress(50, text="混入背景音乐...")
    with_bgm = get_temp_path(f"ipb_bgm_{uid}.mp4")
    cmd = build_bgm_mix_command(
        merged_video=merged,
        bgm_path=bgm_path,
        output_path=with_bgm,
        bgm_volume=st.session_state.get("ipb_m5_bgm_volume", 0.3),
        voice_volume=st.session_state.get("ipb_m5_voice_volume", 1.0),
    )
    subprocess.run(cmd, check=True, capture_output=True)
    return with_bgm


def _write_final_video(merged: str, audio: str, uid: str, progress=None) -> str:
    final = get_output_path(f"ipb_{uid}_final.mp4")
    copy_text = st.session_state.get("ipb_m2_output", "")
    if st.session_state.get("ipb_m5_subtitle_enabled", True) and copy_text:
        srt = get_temp_path(f"ipb_{uid}.srt")
        generate_srt(copy_text, audio, srt)
        if progress:
            progress.progress(85, text="嵌入字幕...")
        template = get_ip_broadcast_template(st.session_state.get("ipb_m5_template_id"))
        embed_subtitles(merged, srt, final, force_style=build_ass_force_style(template))
    else:
        shutil.copy2(merged, final)
    return final


def overlay_enabled() -> bool:
    return bool(
        st.session_state.get("ipb_overlay_enabled")
        and st.session_state.get("ipb_story_segments")
        and st.session_state.get("ipb_visual_groups")
    )


async def apply_overlay_plan_async(
    pixelle_video,
    base_video: str,
    audio_path: str,
    uid: str,
) -> str:
    segments = st.session_state.get("ipb_story_segments", [])
    groups = st.session_state.get("ipb_visual_groups", [])
    timeline = estimate_overlay_timeline(segments, groups, probe_duration(audio_path))
    if not timeline:
        return base_video

    video_service = VideoService()
    group_by_id = {group["group_id"]: group for group in groups}
    current_video = base_video
    for index, item in enumerate(timeline, start=1):
        group = group_by_id[item["group_id"]]
        overlay_video = await prepare_overlay_clip(
            pixelle_video=pixelle_video,
            group=group,
            target_duration=item["duration"],
            uid=uid,
        )
        output_path = get_temp_path(f"ipb_overlay_{uid}_{index}.mp4")
        current_video = video_service.overlay_video_segment(
            base_video=current_video,
            overlay_video=overlay_video,
            output_path=output_path,
            start_time=item["start_time"],
            end_time=item["end_time"],
            mode=item["overlay_mode"],
        )
        group["status"] = "done"
        group["error"] = ""
    return current_video


async def prepare_overlay_clip(
    pixelle_video,
    group: dict[str, Any],
    target_duration: float,
    uid: str,
) -> str:
    overlay_type = normalize_overlay_type(group)
    if overlay_type == "uploaded_video":
        uploaded_video = group.get("uploaded_video_path", "")
        if not uploaded_video or not Path(uploaded_video).exists():
            raise RuntimeError(f"覆盖组 {group.get('group_id')} 未上传视频素材")
        return uploaded_video

    if overlay_type == "ai_video":
        if group.get("generated_video_path") and Path(group["generated_video_path"]).exists():
            return group["generated_video_path"]
        media_result = await pixelle_video.media(
            prompt=group.get("prompt") or "商务口播相关真实场景，镜头稳定",
            workflow=first_video_workflow(pixelle_video),
            media_type="video",
            duration=target_duration,
        )
        raw_video_path = get_temp_path(f"ipb_overlay_ai_{uid}_{group.get('group_id')}.mp4")
        media_url = getattr(media_result, "url", None) or str(media_result)
        await _save_video_output(media_url, raw_video_path)
        group["generated_video_path"] = raw_video_path
        return raw_video_path

    raise RuntimeError(f"覆盖组 {group.get('group_id')} 不需要覆盖画面")


def first_video_workflow(pixelle_video) -> str | None:
    workflows = pixelle_video.media.list_workflows()
    for workflow in workflows:
        key = workflow.get("key", "")
        if "video_" in key.lower():
            return key
    return None


def probe_duration(media_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            media_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())
