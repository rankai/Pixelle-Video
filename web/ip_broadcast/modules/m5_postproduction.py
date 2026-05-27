import base64
import html
import mimetypes
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
from pixelle_video.services.video_asset_service import VideoAssetService
from pixelle_video.utils.os_util import (
    get_output_path,
    get_resource_path,
    get_temp_path,
    list_resource_files,
)
from web.ip_broadcast.state import (
    STATUS_ICONS,
    create_overlay_group,
    get_step_status,
    remove_overlay_group,
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
                st.markdown(
                    _build_card_text_html(
                        title=template.display_name,
                        subtitle=template.short_description,
                        tooltip=template.full_description,
                    ),
                    unsafe_allow_html=True,
                )
                if selected:
                    st.button(
                        "已选择",
                        key=f"ipb_m5_template_selected_{template.template_id}",
                        use_container_width=True,
                        disabled=True,
                        type="primary",
                    )
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
        st.markdown(_build_template_missing_preview_html(height=180), unsafe_allow_html=True)
        return
    st.markdown(_build_template_preview_html(str(path), height=180), unsafe_allow_html=True)


def _build_card_text_html(title: str, subtitle: str, tooltip: str = "") -> str:
    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    safe_tooltip = html.escape(tooltip or subtitle, quote=True)
    return f"""
    <div style="padding:8px 2px 2px;">
        <div style="min-height:20px; display:flex; align-items:flex-start;
                    font-size:14px; line-height:20px; font-weight:700; color:#111827;">
            {safe_title}
        </div>
        <div title="{safe_tooltip}"
             style="min-height:34px; font-size:12px; line-height:17px; color:#6b7280;
                    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
                    overflow:hidden;">
            {safe_subtitle}
        </div>
    </div>
    """


def _build_template_preview_html(preview_path: str, height: int = 180) -> str:
    path = Path(preview_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"""
    <div style="height:{height}px; border:1px solid #e5e7eb; border-radius:6px;
                overflow:hidden; background:#f8fafc; display:flex; align-items:center;
                justify-content:center;">
        <img src="data:{mime_type};base64,{data}" alt="画面模板效果图"
             style="width:100%; height:{height}px; object-fit:contain; display:block;" />
    </div>
    """


def _build_template_missing_preview_html(height: int = 180) -> str:
    return f"""
    <div style="height:{height}px; border:1px dashed #cbd5e1; border-radius:6px;
                background:#f8fafc; display:flex; align-items:center; justify-content:center;
                color:#94a3b8; font-size:13px;">
        暂无效果图
    </div>
    """


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

    _render_video_asset_management()

    if st.button("按当前文案更新段落", key="ipb_overlay_refresh_btn", use_container_width=True):
        sync_story_segments_from_script(script)
        st.success("画面规划段落已更新")
        safe_rerun()

    if not segments:
        st.caption("在第 2 步文案中用回车分段后，这里会显示可规划的段落。")
        return

    if not enabled:
        return

    st.markdown("**勾选连续段落创建覆盖组**")
    selected_segment_ids = _render_overlay_segment_picker(segments, groups)
    if st.button("创建覆盖组", key="ipb_overlay_create_group_btn", use_container_width=True):
        try:
            create_overlay_group(selected_segment_ids)
            _clear_overlay_segment_picker(segments)
            st.success("覆盖组已创建")
            safe_rerun()
        except Exception as e:
            st.error(str(e))

    visible_groups = _visible_overlay_groups(groups)
    with st.expander("编辑覆盖组", expanded=bool(visible_groups)):
        if not visible_groups:
            st.caption("勾选一个或多个连续段落后创建覆盖组，再在这里配置覆盖视频。")
            return

        for group in visible_groups:
            group_segments = [
                segment for segment in segments
                if segment["segment_id"] in group.get("segment_ids", [])
            ]
            label = "、".join(f"第{segment['index']}段" for segment in group_segments)
            with st.container(border=True):
                title_col, action_col = st.columns([3, 1])
                with title_col:
                    st.markdown(f"**覆盖组 {group['group_id']}：{label}**")
                with action_col:
                    if st.button(
                        "取消覆盖组",
                        key=f"ipb_overlay_remove_{group['group_id']}",
                        use_container_width=True,
                    ):
                        remove_overlay_group(group["group_id"])
                        safe_rerun()
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
                    _render_group_video_asset_selector(group)
                elif overlay_type == "ai_video":
                    group["prompt"] = st.text_area(
                        "AI 视频提示词",
                        value=group.get("prompt") or "商务口播相关真实场景，镜头稳定",
                        height=80,
                        key=f"ipb_overlay_prompt_{group['group_id']}",
                    )


def _get_video_asset_svc() -> VideoAssetService:
    return VideoAssetService()


def _render_video_asset_management() -> None:
    svc = _get_video_asset_svc()
    with st.expander("视频素材管理", expanded=False):
        assets = svc.list_assets()
        if assets:
            cols_per_row = 3
            rows = [assets[i : i + cols_per_row] for i in range(0, len(assets), cols_per_row)]
            for row in rows:
                cols = st.columns(cols_per_row)
                for col, asset in zip(cols, row):
                    with col:
                        with st.container(border=True):
                            _render_video_asset_cover(asset)
                            st.markdown(
                                _build_card_text_html(
                                    title=asset.name,
                                    subtitle=_format_video_asset_meta(asset),
                                    tooltip=f"{asset.name} · {asset.created_at}",
                                ),
                                unsafe_allow_html=True,
                            )
                            if st.button(
                                "删除",
                                key=f"ipb_video_asset_delete_{asset.asset_id}",
                                use_container_width=True,
                            ):
                                _delete_video_asset(svc, asset.asset_id)
        else:
            st.caption("暂无视频素材。")

        st.markdown("**上传新视频素材**")
        name = st.text_input(
            "素材名称",
            key="ipb_video_asset_new_name",
            placeholder="例如：客户案例、门店环境、产品演示",
        )
        uploaded = st.file_uploader(
            "上传视频素材",
            type=["mp4", "mov", "webm"],
            key="ipb_video_asset_uploader",
        )
        if st.button("保存视频素材", key="ipb_video_asset_save_btn", use_container_width=True):
            _save_video_asset(svc, name, uploaded)


def _render_group_video_asset_selector(group: dict[str, Any]) -> None:
    svc = _get_video_asset_svc()
    assets = svc.list_assets()
    if not assets:
        st.warning("暂无视频素材，请先在上方「视频素材管理」里上传。")
        return

    asset_paths = {asset.asset_id: asset.asset_path() for asset in assets}
    options = [""] + [asset.asset_id for asset in assets]
    labels = {"": "请选择视频素材"}
    labels.update({asset.asset_id: asset.name for asset in assets})
    current_id = group.get("video_asset_id", "")
    if current_id not in options:
        current_id = ""
    selected_id = st.selectbox(
        "选择视频素材",
        options=options,
        index=options.index(current_id),
        format_func=lambda asset_id: labels.get(asset_id, asset_id),
        key=f"ipb_overlay_asset_{group['group_id']}",
    )
    if selected_id:
        _apply_video_asset_to_group(group, selected_id, asset_paths[selected_id])
        asset = next(item for item in assets if item.asset_id == selected_id)
        _render_video_asset_cover(asset, height=90)
    else:
        group["video_asset_id"] = ""
        group["uploaded_video_path"] = ""


def _apply_video_asset_to_group(group: dict[str, Any], asset_id: str, asset_path: str) -> None:
    group["video_asset_id"] = asset_id
    group["uploaded_video_path"] = asset_path


def _save_video_asset(svc: VideoAssetService, name: str, uploaded) -> None:
    clean_name = name.strip()
    if not clean_name:
        st.warning("请填写素材名称。")
        return
    if uploaded is None:
        st.warning("请上传视频素材。")
        return
    try:
        ext = uploaded.name.rsplit(".", 1)[-1].lower()
        svc.save_asset(clean_name, uploaded.getvalue(), ext)
        st.success(f"视频素材「{clean_name}」已保存。")
        safe_rerun()
    except Exception as e:
        st.error(str(e))
        logger.exception(e)


def _delete_video_asset(svc: VideoAssetService, asset_id: str) -> None:
    if _video_asset_in_use(asset_id):
        st.warning("该素材正在覆盖组中使用，请先取消对应覆盖组或更换素材。")
        return
    svc.delete_asset(asset_id)
    safe_rerun()


def _video_asset_in_use(asset_id: str) -> bool:
    return any(
        group.get("video_asset_id") == asset_id
        for group in st.session_state.get("ipb_visual_groups", [])
    )


def _render_video_asset_cover(asset, height: int = 120) -> None:
    if asset.thumbnail_exists():
        st.markdown(
            _build_video_asset_cover_html(asset.thumbnail_path(), height=height),
            unsafe_allow_html=True,
        )
        return
    st.markdown(_build_video_asset_missing_cover_html(height=height), unsafe_allow_html=True)


def _build_video_asset_cover_html(cover_path: str, height: int = 120) -> str:
    path = Path(cover_path)
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"""
    <div style="height:{height}px; border:1px solid #e5e7eb; border-radius:6px;
                overflow:hidden; background:#111827;">
        <img src="data:{mime_type};base64,{data}" alt="视频素材封面"
             style="width:100%; height:{height}px; object-fit:cover; display:block;" />
    </div>
    """


def _build_video_asset_missing_cover_html(height: int = 120) -> str:
    return f"""
    <div style="height:{height}px; border:1px dashed #cbd5e1; border-radius:6px;
                background:#f8fafc; display:flex; align-items:center; justify-content:center;
                color:#94a3b8; font-size:13px;">
        暂无封面
    </div>
    """


def _format_video_asset_meta(asset) -> str:
    parts = []
    if asset.duration:
        parts.append(f"{asset.duration:.1f}s")
    if asset.size:
        parts.append(_format_file_size(asset.size))
    return " · ".join(parts) or asset.created_at


def _format_file_size(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    return f"{size / (1024 * 1024):.1f}MB"


def _render_overlay_segment_picker(
    segments: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> list[str]:
    group_by_segment = {
        segment_id: group
        for group in groups
        for segment_id in group.get("segment_ids", [])
    }
    selected_segment_ids = []
    with st.container(border=True):
        for segment in segments:
            segment_id = segment["segment_id"]
            current_group = group_by_segment.get(segment_id, {})
            group_label = ""
            if current_group.get("is_overlay_group") or _normalize_overlay_type(current_group) != "none":
                group_label = f" · 已在 {current_group.get('group_id', '覆盖组')}"
            picked = st.checkbox(
                f"第{segment['index']}段{group_label}",
                key=_overlay_pick_key(segment_id),
            )
            st.caption(segment.get("text", "")[:96])
            if picked:
                selected_segment_ids.append(segment_id)
    st.caption("提示：一次只能创建连续段落的覆盖组。未加入覆盖组的段落默认保留数字人画面。")
    return selected_segment_ids


def _clear_overlay_segment_picker(segments: list[dict[str, Any]]) -> None:
    st.session_state["ipb_overlay_picker_nonce"] = int(
        st.session_state.get("ipb_overlay_picker_nonce", 0)
    ) + 1


def _overlay_pick_key(segment_id: str) -> str:
    nonce = int(st.session_state.get("ipb_overlay_picker_nonce", 0))
    return f"ipb_overlay_pick_{nonce}_{segment_id}"


def _visible_overlay_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        group for group in groups
        if group.get("is_overlay_group")
        or _normalize_overlay_type(group) != "none"
        or len(group.get("segment_ids", [])) > 1
    ]


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
        set_step_notice(5, "error", str(e))
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
