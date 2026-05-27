import uuid
from pathlib import Path

import streamlit as st

from pixelle_video.models.ip_broadcast import SocialMetaResult
from pixelle_video.prompts.ip_broadcast import build_social_meta_prompt
from pixelle_video.services.ip_broadcast_templates import render_ip_broadcast_cover
from pixelle_video.services.subtitle_service import extract_first_frame
from pixelle_video.utils.os_util import get_temp_path
from web.utils.async_helpers import run_async


def render_publish_asset_settings() -> None:
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


def render_publish_asset_summary() -> None:
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


def ensure_publish_assets(pixelle_video, final_video_path: str) -> None:
    run_async(ensure_publish_assets_async(pixelle_video, final_video_path))


async def ensure_publish_assets_async(pixelle_video, final_video_path: str) -> None:
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
