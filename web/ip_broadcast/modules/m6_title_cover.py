import uuid
from pathlib import Path

import streamlit as st
from loguru import logger

from pixelle_video.models.ip_broadcast import SocialMetaResult
from pixelle_video.prompts.ip_broadcast import build_social_meta_prompt
from pixelle_video.services.subtitle_service import extract_first_frame
from pixelle_video.utils.os_util import get_temp_path
from web.ip_broadcast.state import STATUS_ICONS, get_step_status, set_step_status
from web.ip_broadcast.status_ui import (
    hide_global_loading,
    render_step_notice,
    set_step_notice,
    show_global_loading,
)
from web.utils.async_helpers import run_async
from web.utils.streamlit_helpers import safe_rerun


def render_m6_title_cover(pixelle_video, run_mode: str):
    status = get_step_status(6)
    icon = STATUS_ICONS.get(status, "○")
    with st.container(border=True):
        st.markdown(f"**{icon} 6. 标题封面**")

    copy_text = st.session_state.get("ipb_m2_output", "")
    if not copy_text:
        st.info("💡 完成「2. 改写文案」后可一键AI生成标题，也可直接手动填写")

    if st.button("✨ AI生成标题描述", key="ipb_m6_ai_gen", disabled=not bool(copy_text)):
        _generate_meta(pixelle_video, copy_text)

    _render_meta_summary()
    render_step_notice(6)

    with st.expander("手动编辑与封面设置", expanded=False):
        st.text_input("视频标题", key="ipb_m6_title", placeholder="输入视频标题（15-20字）")
        st.text_area(
            "视频描述",
            key="ipb_m6_description",
            height=100,
            placeholder="输入视频描述（50-100字）",
        )

        current_tags = st.session_state.get("ipb_m6_hashtags", [])
        tags_str = ", ".join(current_tags) if current_tags else ""
        new_tags_str = st.text_input(
            "话题标签（用逗号分隔，不含#号）",
            value=tags_str,
            key="_ipb_m6_hashtags_input",
            placeholder="例如：创业, 干货分享, 老板IP",
        )
        st.session_state.ipb_m6_hashtags = [
            t.strip() for t in new_tags_str.split(",") if t.strip()
        ]

        _render_cover_settings()

    if run_mode == "auto":
        if copy_text and get_step_status(6) == "ready":
            run_async(run_m6(pixelle_video))


def _generate_meta(pixelle_video, copy_text: str):
    loading = show_global_loading("AI 正在生成标题和描述，请稍候...")
    with st.spinner("AI正在生成标题和描述..."):
        try:
            result: SocialMetaResult = run_async(
                pixelle_video.llm(
                    prompt=build_social_meta_prompt(copy_text),
                    response_type=SocialMetaResult,
                )
            )
            st.session_state.ipb_m6_title = result.title
            st.session_state.ipb_m6_description = result.description
            st.session_state.ipb_m6_hashtags = result.hashtags
            _extract_cover_if_possible()
            set_step_status(6, "done")
            set_step_notice(6, "success", "标题描述生成完成")
            safe_rerun()
        except Exception as e:
            set_step_notice(6, "error", str(e))
            st.error(str(e))
            logger.exception(e)
            set_step_status(6, "error")
        finally:
            hide_global_loading(loading)


async def run_m6(pixelle_video) -> bool:
    copy_text = st.session_state.get("ipb_m2_output", "")
    if not copy_text:
        return False
    try:
        result: SocialMetaResult = await pixelle_video.llm(
            prompt=build_social_meta_prompt(copy_text),
            response_type=SocialMetaResult,
        )
        st.session_state.ipb_m6_title = result.title
        st.session_state.ipb_m6_description = result.description
        st.session_state.ipb_m6_hashtags = result.hashtags
        _extract_cover_if_possible()
        set_step_status(6, "done")
        return True
    except Exception as e:
        logger.exception(e)
        set_step_status(6, "error")
        return False


def _render_meta_summary():
    title = st.session_state.get("ipb_m6_title", "")
    description = st.session_state.get("ipb_m6_description", "")
    hashtags = st.session_state.get("ipb_m6_hashtags", [])
    cover_path = st.session_state.get("ipb_m6_cover_path", "")

    if title:
        st.markdown(f"**标题：** {title}")
    if description:
        st.caption(description)
    if hashtags:
        st.caption(" ".join(f"#{tag}" for tag in hashtags))
    if cover_path and Path(cover_path).exists():
        st.image(cover_path, caption="封面预览", use_container_width=True)


def _render_cover_settings():
    st.markdown("**封面设置**")
    cover_mode = st.radio(
        "封面来源",
        options=["first_frame", "upload"],
        format_func=lambda x: "提取首帧" if x == "first_frame" else "上传图片",
        horizontal=True,
        key="ipb_m6_cover_mode",
    )

    if cover_mode == "first_frame":
        final_path = st.session_state.get("ipb_m5_final_video_path", "")
        if not final_path or not Path(final_path).exists():
            st.info("请先在模块5完成视频合成，再提取首帧")
        elif st.button("提取首帧", key="ipb_m6_extract_frame"):
            try:
                _extract_cover_if_possible(force=True)
                st.success("首帧提取成功")
                safe_rerun()
            except Exception as e:
                st.error(str(e))
                logger.exception(e)
    else:
        uploaded = st.file_uploader(
            "上传封面图片",
            type=["jpg", "jpeg", "png", "webp"],
            key="ipb_m6_cover_upload",
        )
        if uploaded is not None:
            try:
                uid = uuid.uuid4().hex[:8]
                ext = Path(uploaded.name).suffix or ".jpg"
                cover_path = get_temp_path(f"ipb_cover_{uid}{ext}")
                with open(cover_path, "wb") as f:
                    f.write(uploaded.getbuffer())
                st.session_state.ipb_m6_cover_path = cover_path
                st.image(uploaded, caption="封面预览", use_container_width=True)
            except Exception as e:
                st.error(str(e))
                logger.exception(e)


def _extract_cover_if_possible(force: bool = False):
    if not force and st.session_state.get("ipb_m6_cover_path"):
        return
    if st.session_state.get("ipb_m6_cover_mode", "first_frame") != "first_frame":
        return
    final_path = st.session_state.get("ipb_m5_final_video_path", "")
    if not final_path or not Path(final_path).exists():
        return
    uid = uuid.uuid4().hex[:8]
    cover_path = get_temp_path(f"ipb_cover_{uid}.png")
    extract_first_frame(final_path, cover_path)
    st.session_state.ipb_m6_cover_path = cover_path
