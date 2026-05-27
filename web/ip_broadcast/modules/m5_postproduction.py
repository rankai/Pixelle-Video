import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger

from pixelle_video.models.ip_broadcast import SocialMetaResult
from pixelle_video.prompts.ip_broadcast import build_social_meta_prompt
from pixelle_video.services.digital_human_service import _save_video_output
from pixelle_video.services.ip_broadcast_templates import (
    build_ass_force_style,
    get_ip_broadcast_template,
    list_ip_broadcast_templates,
    render_ip_broadcast_cover,
)
from pixelle_video.services.subtitle_service import (
    embed_subtitles,
    extract_first_frame,
    generate_srt,
    merge_audio_into_video,
    remove_silence,
)
from pixelle_video.services.video import VideoService
from pixelle_video.utils.os_util import (
    get_output_path,
    get_resource_path,
    get_temp_path,
    list_resource_files,
)
from web.ip_broadcast.state import (
    STATUS_ICONS,
    get_step_status,
    merge_story_segments,
    set_step_status,
    sync_story_segments_from_script,
)
from web.ip_broadcast.status_ui import (
    hide_global_loading,
    render_step_notice,
    set_step_notice,
    show_global_loading,
)
from web.utils.async_helpers import run_async
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
    _render_template_selector()
    _render_overlay_planning()

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

    with st.expander("发布素材与封面", expanded=False):
        _render_publish_asset_settings()

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
    _render_publish_asset_summary()
    render_step_notice(5)


def _render_template_selector():
    templates = list_ip_broadcast_templates()
    current_id = st.session_state.get("ipb_m5_template_id", templates[0].template_id)
    template_ids = [item.template_id for item in templates]
    if current_id not in template_ids:
        current_id = templates[0].template_id

    st.markdown("**画面模板**")
    cols = st.columns(len(templates))
    for col, template in zip(cols, templates):
        with col:
            selected = template.template_id == current_id
            with st.container(border=True):
                _render_template_preview(template.preview_image_path)
                st.markdown(f"**{template.display_name}**")
                st.caption("展示封面标题位置、字幕位置和模板风格")
                if selected:
                    st.success("已选择")
                elif st.button(
                    "选择",
                    key=f"ipb_m5_template_select_{template.template_id}",
                    use_container_width=True,
                ):
                    st.session_state.ipb_m5_template_id = template.template_id
                    safe_rerun()
    st.session_state.ipb_m5_template_id = st.session_state.get("ipb_m5_template_id", current_id)


def _render_template_preview(preview_path: str):
    path = Path(preview_path)
    if not path.exists():
        st.caption("暂无效果图")
        return
    st.image(str(path), use_container_width=True)


def _render_overlay_planning():
    st.markdown("**画面规划（可选）**")
    script = st.session_state.get("ipb_final_script", "")
    if script and not st.session_state.get("ipb_story_segments"):
        sync_story_segments_from_script(script)

    segments = st.session_state.get("ipb_story_segments", [])
    groups = st.session_state.get("ipb_visual_groups", [])
    st.caption(
        f"已识别 {len(segments)} 个文案段落。默认全程数字人；开启后只在第 5 步覆盖画面，不会重复生成语音或数字人。"
    )

    enabled = st.toggle(
        "添加覆盖画面",
        key="ipb_overlay_enabled",
        help="用于在指定文案段落对应的时间范围内叠加上传视频或 AI 视频。",
    )
    st.session_state.ipb_storyboard_enabled = enabled

    if st.button("按当前文案更新段落", key="ipb_overlay_refresh_btn", use_container_width=True):
        sync_story_segments_from_script(script)
        st.success("画面规划段落已更新")
        safe_rerun()

    if not segments:
        st.caption("在第 2 步文案中用回车分段后，这里会显示可规划的段落。")
        return

    if not enabled:
        return

    merge_col1, merge_col2, merge_col3 = st.columns([1, 1, 1.3])
    with merge_col1:
        start_idx = st.number_input(
            "覆盖起始段",
            min_value=1,
            max_value=len(segments),
            value=1,
            step=1,
            key="ipb_overlay_merge_start",
        )
    with merge_col2:
        end_idx = st.number_input(
            "覆盖结束段",
            min_value=1,
            max_value=len(segments),
            value=min(2, len(segments)),
            step=1,
            key="ipb_overlay_merge_end",
        )
    with merge_col3:
        st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        if st.button("合并连续段落为覆盖组", key="ipb_overlay_merge_btn", use_container_width=True):
            try:
                selected = [
                    item["segment_id"]
                    for item in segments
                    if int(start_idx) <= item["index"] <= int(end_idx)
                ]
                merge_story_segments(selected)
                st.success("已合并为同一个覆盖组")
                safe_rerun()
            except Exception as e:
                st.error(str(e))

    with st.expander("编辑覆盖组", expanded=True):
        for group in groups:
            group_segments = [
                segment for segment in segments
                if segment["segment_id"] in group.get("segment_ids", [])
            ]
            label = "、".join(f"第{segment['index']}段" for segment in group_segments)
            with st.container(border=True):
                st.markdown(f"**覆盖组 {group['group_id']}：{label}**")
                for segment in group_segments:
                    st.caption(f"{segment['index']}. {segment['text'][:80]}")
                overlay_type = _normalize_overlay_type(group)
                overlay_type = st.radio(
                    "覆盖类型",
                    options=["none", "uploaded_video", "ai_video"],
                    format_func=lambda value: {
                        "none": "不覆盖，保留数字人",
                        "uploaded_video": "上传视频覆盖",
                        "ai_video": "AI 视频覆盖",
                    }[value],
                    horizontal=True,
                    index=["none", "uploaded_video", "ai_video"].index(overlay_type),
                    key=f"ipb_overlay_type_{group['group_id']}",
                )
                group["overlay_type"] = overlay_type
                group["visual_type"] = {
                    "none": "digital_human",
                    "uploaded_video": "uploaded_video",
                    "ai_video": "ai_video",
                }[overlay_type]
                if overlay_type == "none":
                    continue

                group["overlay_mode"] = st.radio(
                    "覆盖方式",
                    options=["fullscreen", "pip"],
                    format_func=lambda value: "全屏覆盖" if value == "fullscreen" else "画中画",
                    horizontal=True,
                    index=["fullscreen", "pip"].index(group.get("overlay_mode", "fullscreen")),
                    key=f"ipb_overlay_mode_{group['group_id']}",
                )
                if overlay_type == "uploaded_video":
                    uploaded = st.file_uploader(
                        "上传覆盖视频",
                        type=["mp4", "mov", "webm"],
                        key=f"ipb_overlay_upload_{group['group_id']}",
                    )
                    if uploaded is not None:
                        ext = Path(uploaded.name).suffix or ".mp4"
                        path = get_temp_path(f"ipb_overlay_{uuid.uuid4().hex[:8]}{ext}")
                        with open(path, "wb") as f:
                            f.write(uploaded.getbuffer())
                        group["uploaded_video_path"] = path
                    if group.get("uploaded_video_path"):
                        st.caption(f"已选择：{Path(group['uploaded_video_path']).name}")
                elif overlay_type == "ai_video":
                    group["prompt"] = st.text_area(
                        "AI 视频提示词",
                        value=group.get("prompt") or "商务口播相关真实场景，镜头稳定",
                        height=80,
                        key=f"ipb_overlay_prompt_{group['group_id']}",
                    )


def _render_publish_asset_settings():
    st.text_input("视频标题", key="ipb_m6_title", placeholder="留空则一键成片时自动生成")
    st.text_area(
        "视频描述",
        key="ipb_m6_description",
        height=90,
        placeholder="留空则一键成片时自动生成",
    )
    tags = st.session_state.get("ipb_m6_hashtags", [])
    tags_text = ", ".join(tags) if tags else ""
    updated_tags = st.text_input(
        "话题标签（逗号分隔）",
        value=tags_text,
        key="_ipb_m5_hashtags_input",
    )
    st.session_state.ipb_m6_hashtags = [
        tag.strip() for tag in updated_tags.split(",") if tag.strip()
    ]

    cover_mode = st.radio(
        "封面来源",
        options=["first_frame", "upload"],
        format_func=lambda value: "模板封面（首帧背景）" if value == "first_frame" else "上传封面图片",
        horizontal=True,
        key="ipb_m6_cover_mode",
    )
    if cover_mode == "upload":
        uploaded = st.file_uploader(
            "上传封面图片",
            type=["jpg", "jpeg", "png", "webp"],
            key="ipb_m5_cover_upload",
        )
        if uploaded is not None:
            uid = uuid.uuid4().hex[:8]
            ext = Path(uploaded.name).suffix or ".jpg"
            cover_path = get_temp_path(f"ipb_cover_upload_{uid}{ext}")
            with open(cover_path, "wb") as f:
                f.write(uploaded.getbuffer())
            st.session_state.ipb_m6_cover_path = cover_path
            st.image(uploaded, caption="封面预览", use_container_width=True)


def _render_publish_asset_summary():
    title = st.session_state.get("ipb_m6_title", "")
    description = st.session_state.get("ipb_m6_description", "")
    hashtags = st.session_state.get("ipb_m6_hashtags", [])
    cover_path = st.session_state.get("ipb_m6_cover_path", "")
    if not any([title, description, hashtags, cover_path]):
        return
    with st.container(border=True):
        st.markdown("**发布素材**")
        if cover_path and Path(cover_path).exists():
            st.image(cover_path, caption="封面预览", use_container_width=True)
        if title:
            st.markdown(f"**标题：** {title}")
        if description:
            st.caption(description)
        if hashtags:
            st.caption(" ".join(f"#{tag}" for tag in hashtags))


def _normalize_overlay_type(group: dict[str, Any]) -> str:
    overlay_type = group.get("overlay_type")
    if overlay_type in {"none", "uploaded_video", "ai_video"}:
        return overlay_type
    visual_type = group.get("visual_type")
    if visual_type in {"uploaded_video", "ai_video"}:
        return visual_type
    return "none"


def estimate_overlay_timeline(
    segments: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    audio_duration: float,
) -> list[dict[str, Any]]:
    if not segments or audio_duration <= 0:
        return []

    char_counts = [max(len(segment.get("text", "")), 1) for segment in segments]
    total_chars = sum(char_counts) or 1
    segment_ranges: dict[str, tuple[float, float]] = {}
    current = 0.0
    for segment, chars in zip(segments, char_counts):
        start = current
        current += audio_duration * (chars / total_chars)
        segment_ranges[segment["segment_id"]] = (start, current)

    timeline = []
    for group in groups:
        overlay_type = _normalize_overlay_type(group)
        if overlay_type == "none":
            continue
        ranges = [
            segment_ranges[segment_id]
            for segment_id in group.get("segment_ids", [])
            if segment_id in segment_ranges
        ]
        if not ranges:
            continue
        start_time = min(item[0] for item in ranges)
        end_time = max(item[1] for item in ranges)
        item = {
            "group_id": group["group_id"],
            "start_time": round(start_time, 2),
            "end_time": round(end_time, 2),
            "duration": round(end_time - start_time, 2),
            "overlay_type": overlay_type,
            "overlay_mode": group.get("overlay_mode", "fullscreen"),
        }
        group["start_time"] = item["start_time"]
        group["end_time"] = item["end_time"]
        timeline.append(item)
    return timeline


def _probe_duration(media_path: str) -> float:
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


def _run_postproduction(pixelle_video):
    set_step_status(5, "running")
    loading = show_global_loading("正在合成最终视频，请稍候...")
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

        # Step 3: Optionally apply overlay planning
        if _overlay_enabled():
            progress.progress(42, text="叠加覆盖画面...")
            merged = run_async(_apply_overlay_plan_async(pixelle_video, merged, audio, uid))

        # Step 4: Optionally add BGM
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

        # Step 5: Optionally embed subtitles
        progress.progress(70, text="生成字幕...")
        final = get_output_path(f"ipb_{uid}_final.mp4")
        if subtitle_enabled and copy_text:
            srt = get_temp_path(f"ipb_{uid}.srt")
            generate_srt(copy_text, audio, srt)
            progress.progress(85, text="嵌入字幕...")
            template = get_ip_broadcast_template(st.session_state.get("ipb_m5_template_id"))
            embed_subtitles(merged, srt, final, force_style=build_ass_force_style(template))
        else:
            shutil.copy2(merged, final)

        progress.progress(92, text="生成发布素材...")
        _ensure_publish_assets(pixelle_video, final)
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

        if _overlay_enabled():
            merged = await _apply_overlay_plan_async(pixelle_video, merged, audio, uid)

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
            template = get_ip_broadcast_template(st.session_state.get("ipb_m5_template_id"))
            embed_subtitles(merged, srt, final, force_style=build_ass_force_style(template))
        else:
            shutil.copy2(merged, final)

        await _ensure_publish_assets_async(pixelle_video, final)
        st.session_state.ipb_m5_final_video_path = final
        set_step_status(5, "done")
        return True
    except Exception as e:
        logger.exception(e)
        set_step_status(5, "error")
        return False


def _overlay_enabled() -> bool:
    return bool(
        st.session_state.get("ipb_overlay_enabled")
        and st.session_state.get("ipb_story_segments")
        and st.session_state.get("ipb_visual_groups")
    )


async def _apply_overlay_plan_async(
    pixelle_video,
    base_video: str,
    audio_path: str,
    uid: str,
) -> str:
    segments = st.session_state.get("ipb_story_segments", [])
    groups = st.session_state.get("ipb_visual_groups", [])
    timeline = estimate_overlay_timeline(segments, groups, _probe_duration(audio_path))
    if not timeline:
        return base_video

    video_service = VideoService()
    group_by_id = {group["group_id"]: group for group in groups}
    current_video = base_video
    for index, item in enumerate(timeline, start=1):
        group = group_by_id[item["group_id"]]
        overlay_video = await _prepare_overlay_clip(
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


async def _prepare_overlay_clip(
    pixelle_video,
    group: dict[str, Any],
    target_duration: float,
    uid: str,
) -> str:
    overlay_type = _normalize_overlay_type(group)
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
            workflow=_first_video_workflow(pixelle_video),
            media_type="video",
            duration=target_duration,
        )
        raw_video_path = get_temp_path(f"ipb_overlay_ai_{uid}_{group.get('group_id')}.mp4")
        media_url = getattr(media_result, "url", None) or str(media_result)
        await _save_video_output(media_url, raw_video_path)
        group["generated_video_path"] = raw_video_path
        return raw_video_path

    raise RuntimeError(f"覆盖组 {group.get('group_id')} 不需要覆盖画面")


def _first_video_workflow(pixelle_video) -> str | None:
    workflows = pixelle_video.media.list_workflows()
    for workflow in workflows:
        key = workflow.get("key", "")
        if "video_" in key.lower():
            return key
    return None


def _ensure_publish_assets(pixelle_video, final_video_path: str) -> None:
    run_async(_ensure_publish_assets_async(pixelle_video, final_video_path))


async def _ensure_publish_assets_async(pixelle_video, final_video_path: str) -> None:
    copy_text = st.session_state.get("ipb_m2_output", "")
    if copy_text and (
        not st.session_state.get("ipb_m6_title")
        or not st.session_state.get("ipb_m6_description")
    ):
        result: SocialMetaResult = await pixelle_video.llm(
            prompt=build_social_meta_prompt(copy_text),
            response_type=SocialMetaResult,
        )
        st.session_state.ipb_m6_title = result.title
        st.session_state.ipb_m6_description = result.description
        st.session_state.ipb_m6_hashtags = result.hashtags

    if st.session_state.get("ipb_m6_cover_path"):
        return
    if st.session_state.get("ipb_m6_cover_mode", "first_frame") != "first_frame":
        return
    if not final_video_path or not Path(final_video_path).exists():
        return

    uid = uuid.uuid4().hex[:8]
    first_frame_path = get_temp_path(f"ipb_cover_bg_{uid}.png")
    extract_first_frame(final_video_path, first_frame_path)
    title = st.session_state.get("ipb_m6_title") or "老板IP口播"
    subtitle = st.session_state.get("ipb_m6_description") or "高价值短视频内容"
    cover_path = get_temp_path(f"ipb_cover_{uid}.png")
    st.session_state.ipb_m6_cover_path = await render_ip_broadcast_cover(
        template_id=st.session_state.get("ipb_m5_template_id"),
        title=title,
        subtitle=subtitle,
        background=first_frame_path,
        output_path=cover_path,
    )
