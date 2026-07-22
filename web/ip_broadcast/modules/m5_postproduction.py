from pathlib import Path

import streamlit as st

from pixelle_video.utils.os_util import get_resource_path, list_resource_files
from web.ip_broadcast.modules.m5_composer import (
    apply_overlay_plan_async as _apply_overlay_plan_async,
)
from web.ip_broadcast.modules.m5_composer import (
    build_bgm_mix_command as _build_bgm_mix_command,
)
from web.ip_broadcast.modules.m5_composer import (
    first_video_workflow as _first_video_workflow,
)
from web.ip_broadcast.modules.m5_composer import (
    overlay_enabled as _overlay_enabled,
)
from web.ip_broadcast.modules.m5_composer import (
    prepare_overlay_clip as _prepare_overlay_clip,
)
from web.ip_broadcast.modules.m5_composer import (
    probe_duration as _probe_duration,
)
from web.ip_broadcast.modules.m5_composer import (
    run_m5,
)
from web.ip_broadcast.modules.m5_composer import (
    run_postproduction as _run_postproduction,
)
from web.ip_broadcast.modules.m5_overlay_planning import (
    clear_overlay_segment_picker as _clear_overlay_segment_picker,
)
from web.ip_broadcast.modules.m5_overlay_planning import (
    estimate_overlay_timeline,
)
from web.ip_broadcast.modules.m5_overlay_planning import (
    normalize_overlay_type as _normalize_overlay_type,
)
from web.ip_broadcast.modules.m5_overlay_planning import (
    overlay_pick_key as _overlay_pick_key,
)
from web.ip_broadcast.modules.m5_overlay_planning import (
    render_overlay_planning as _render_overlay_planning,
)
from web.ip_broadcast.modules.m5_overlay_planning import (
    render_overlay_segment_picker as _render_overlay_segment_picker,
)
from web.ip_broadcast.modules.m5_overlay_planning import (
    visible_overlay_groups as _visible_overlay_groups,
)
from web.ip_broadcast.modules.m5_publish_assets import (
    ensure_publish_assets as _ensure_publish_assets,
)
from web.ip_broadcast.modules.m5_publish_assets import (
    ensure_publish_assets_async as _ensure_publish_assets_async,
)
from web.ip_broadcast.modules.m5_publish_assets import (
    render_publish_asset_settings as _render_publish_asset_settings,
)
from web.ip_broadcast.modules.m5_publish_assets import (
    render_publish_asset_summary as _render_publish_asset_summary,
)
from web.ip_broadcast.modules.m5_templates import (
    build_card_text_html as _build_card_text_html,
)
from web.ip_broadcast.modules.m5_templates import (
    build_template_missing_preview_html as _build_template_missing_preview_html,
)
from web.ip_broadcast.modules.m5_templates import (
    build_template_preview_html as _build_template_preview_html,
)
from web.ip_broadcast.modules.m5_templates import (
    render_template_preview as _render_template_preview,
)
from web.ip_broadcast.modules.m5_templates import (
    render_template_selector as _render_template_selector,
)
from web.ip_broadcast.modules.m5_video_assets import (
    apply_video_asset_to_group as _apply_video_asset_to_group,
)
from web.ip_broadcast.modules.m5_video_assets import (
    build_video_asset_cover_html as _build_video_asset_cover_html,
)
from web.ip_broadcast.modules.m5_video_assets import (
    build_video_asset_missing_cover_html as _build_video_asset_missing_cover_html,
)
from web.ip_broadcast.modules.m5_video_assets import (
    delete_video_asset as _delete_video_asset,
)
from web.ip_broadcast.modules.m5_video_assets import (
    format_file_size as _format_file_size,
)
from web.ip_broadcast.modules.m5_video_assets import (
    format_video_asset_meta as _format_video_asset_meta,
)
from web.ip_broadcast.modules.m5_video_assets import (
    get_video_asset_svc as _get_video_asset_svc,
)
from web.ip_broadcast.modules.m5_video_assets import (
    render_group_video_asset_selector as _render_group_video_asset_selector,
)
from web.ip_broadcast.modules.m5_video_assets import (
    render_video_asset_cover as _render_video_asset_cover,
)
from web.ip_broadcast.modules.m5_video_assets import (
    render_video_asset_management as _render_video_asset_management,
)
from web.ip_broadcast.modules.m5_video_assets import (
    save_video_asset as _save_video_asset,
)
from web.ip_broadcast.modules.m5_video_assets import (
    video_asset_in_use as _video_asset_in_use,
)
from web.ip_broadcast.state import STATUS_ICONS, get_step_status
from web.ip_broadcast.status_ui import render_step_notice

__all__ = [
    "_apply_overlay_plan_async",
    "_apply_video_asset_to_group",
    "_build_bgm_mix_command",
    "_build_card_text_html",
    "_build_template_missing_preview_html",
    "_build_template_preview_html",
    "_build_video_asset_cover_html",
    "_build_video_asset_missing_cover_html",
    "_clear_overlay_segment_picker",
    "_delete_video_asset",
    "_ensure_publish_assets",
    "_ensure_publish_assets_async",
    "_first_video_workflow",
    "_format_file_size",
    "_format_video_asset_meta",
    "_get_video_asset_svc",
    "_normalize_overlay_type",
    "_overlay_enabled",
    "_overlay_pick_key",
    "_prepare_overlay_clip",
    "_probe_duration",
    "_render_group_video_asset_selector",
    "_render_overlay_planning",
    "_render_overlay_segment_picker",
    "_render_publish_asset_settings",
    "_render_publish_asset_summary",
    "_render_template_preview",
    "_render_template_selector",
    "_render_video_asset_cover",
    "_render_video_asset_management",
    "_run_postproduction",
    "_save_video_asset",
    "_video_asset_in_use",
    "_visible_overlay_groups",
    "estimate_overlay_timeline",
    "render_m5_postproduction",
    "run_m5",
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
    _render_video_asset_management()
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
