import shutil
import subprocess
import uuid
from pathlib import Path

import streamlit as st
from loguru import logger

from pixelle_video.services.subtitle_service import (
    embed_subtitles,
    generate_srt,
    merge_audio_into_video,
    remove_silence,
)
from pixelle_video.utils.os_util import (
    get_output_path,
    get_resource_path,
    get_temp_path,
    list_resource_files,
)
from web.ip_broadcast.state import STATUS_ICONS, get_step_status, set_step_status
from web.ip_broadcast.status_ui import render_step_notice, set_step_notice, show_global_loading
from web.utils.streamlit_helpers import safe_rerun


def _build_bgm_mix_command(
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


def render_m5_postproduction(pixelle_video, run_mode: str):
    status = get_step_status(5)
    icon = STATUS_ICONS.get(status, "○")
    with st.container(border=True):
        st.markdown(f"**{icon} 5. 一键成片**")

    dh_video = st.session_state.get("ipb_m4_dh_video_path", "")
    audio = st.session_state.get("ipb_m3_audio_path", "")

    if not dh_video:
        st.info("💡 完成「4. 数字人视频」后可合成")
    if not audio:
        st.info("💡 完成「3. 声音生成」后可合成")

    st.checkbox("添加字幕", key="ipb_m5_subtitle_enabled")

    with st.expander("高级成片设置", expanded=False):
        st.caption("IP口播成片保持数字人视频为主体，这里只处理字幕、BGM、音量和静音段。")
        st.checkbox("自动删除静音段", key="ipb_m5_remove_silence")
        bgm_files = list_resource_files("bgm")
        bgm_options = ["无BGM"] + bgm_files
        selected_bgm = st.selectbox("背景音乐", options=bgm_options, key="_ipb_m5_bgm_select")
        if selected_bgm and selected_bgm != "无BGM":
            st.session_state.ipb_m5_bgm_path = get_resource_path("bgm", selected_bgm)
        else:
            st.session_state.ipb_m5_bgm_path = ""

        if st.session_state.get("ipb_m5_bgm_path"):
            st.slider("BGM音量", 0.0, 1.0, step=0.05, key="ipb_m5_bgm_volume")

        st.slider("人声音量", 0.0, 1.0, step=0.05, key="ipb_m5_voice_volume")

    can_generate = bool(dh_video and audio)

    if run_mode == "manual":
        generate_clicked = st.button(
            "🎬 合成视频",
            disabled=not can_generate,
            type="primary",
            key="ipb_m5_generate_btn",
        )
        if generate_clicked:
            _run_postproduction(pixelle_video)
    else:
        if can_generate and status == "ready":
            _run_postproduction(pixelle_video)

    final_path = st.session_state.get("ipb_m5_final_video_path", "")
    if final_path and Path(final_path).exists():
        st.video(final_path)
        with open(final_path, "rb") as f:
            st.download_button(
                "⬇️ 下载最终视频",
                data=f.read(),
                file_name=Path(final_path).name,
                mime="video/mp4",
            )
    render_step_notice(5)


def _run_postproduction(pixelle_video):
    set_step_status(5, "running")
    show_global_loading("正在合成最终视频，请稍候...")
    progress = st.progress(0, text="准备中...")
    try:
        uid = uuid.uuid4().hex[:8]
        dh_video = st.session_state.get("ipb_m4_dh_video_path", "")
        audio_src = st.session_state.get("ipb_m3_audio_path", "")
        subtitle_enabled = st.session_state.get("ipb_m5_subtitle_enabled", True)
        remove_silence_enabled = st.session_state.get("ipb_m5_remove_silence", False)
        bgm_path = st.session_state.get("ipb_m5_bgm_path", "")
        bgm_volume = st.session_state.get("ipb_m5_bgm_volume", 0.3)
        voice_volume = st.session_state.get("ipb_m5_voice_volume", 1.0)
        copy_text = st.session_state.get("ipb_m2_output", "")

        # Step 1: Optionally remove silence
        progress.progress(10, text="处理音频...")
        audio = audio_src
        if remove_silence_enabled:
            cleaned = get_temp_path(f"ipb_clean_{uid}.mp3")
            audio = remove_silence(audio_src, cleaned)

        # Step 2: Merge audio into digital human video
        progress.progress(30, text="合并音视频...")
        merged = get_temp_path(f"ipb_merged_{uid}.mp4")
        merged = merge_audio_into_video(dh_video, audio, merged)

        # Step 3: Optionally add BGM
        if bgm_path and Path(bgm_path).exists():
            progress.progress(50, text="混入背景音乐...")
            with_bgm = get_temp_path(f"ipb_bgm_{uid}.mp4")
            cmd = _build_bgm_mix_command(
                merged_video=merged,
                bgm_path=bgm_path,
                output_path=with_bgm,
                bgm_volume=bgm_volume,
                voice_volume=voice_volume,
            )
            subprocess.run(cmd, check=True, capture_output=True)
            merged = with_bgm

        # Step 4: Optionally embed subtitles
        progress.progress(70, text="生成字幕...")
        final = get_output_path(f"ipb_{uid}_final.mp4")
        if subtitle_enabled and copy_text:
            srt = get_temp_path(f"ipb_{uid}.srt")
            generate_srt(copy_text, audio, srt)
            progress.progress(85, text="嵌入字幕...")
            embed_subtitles(merged, srt, final)
        else:
            shutil.copy2(merged, final)

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


async def run_m5(pixelle_video) -> bool:
    uid = uuid.uuid4().hex[:8]
    try:
        dh_video = st.session_state.get("ipb_m4_dh_video_path", "")
        audio_src = st.session_state.get("ipb_m3_audio_path", "")
        if not dh_video or not audio_src:
            return False

        subtitle_enabled = st.session_state.get("ipb_m5_subtitle_enabled", True)
        remove_silence_enabled = st.session_state.get("ipb_m5_remove_silence", False)
        bgm_path = st.session_state.get("ipb_m5_bgm_path", "")
        bgm_volume = st.session_state.get("ipb_m5_bgm_volume", 0.3)
        voice_volume = st.session_state.get("ipb_m5_voice_volume", 1.0)
        copy_text = st.session_state.get("ipb_m2_output", "")

        audio = audio_src
        if remove_silence_enabled:
            cleaned = get_temp_path(f"ipb_clean_{uid}.mp3")
            audio = remove_silence(audio_src, cleaned)

        merged = get_temp_path(f"ipb_merged_{uid}.mp4")
        merged = merge_audio_into_video(dh_video, audio, merged)

        if bgm_path and Path(bgm_path).exists():
            with_bgm = get_temp_path(f"ipb_bgm_{uid}.mp4")
            cmd = _build_bgm_mix_command(
                merged_video=merged,
                bgm_path=bgm_path,
                output_path=with_bgm,
                bgm_volume=bgm_volume,
                voice_volume=voice_volume,
            )
            subprocess.run(cmd, check=True, capture_output=True)
            merged = with_bgm

        final = get_output_path(f"ipb_{uid}_final.mp4")
        if subtitle_enabled and copy_text:
            srt = get_temp_path(f"ipb_{uid}.srt")
            generate_srt(copy_text, audio, srt)
            embed_subtitles(merged, srt, final)
        else:
            shutil.copy2(merged, final)

        st.session_state.ipb_m5_final_video_path = final
        set_step_status(5, "done")
        return True
    except Exception as e:
        logger.exception(e)
        set_step_status(5, "error")
        return False
