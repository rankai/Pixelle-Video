from pathlib import Path

import streamlit as st
from loguru import logger

from web.ip_broadcast.state import STATUS_ICONS, get_step_status, set_step_status


def render_m7_publish(pixelle_video, run_mode: str):
    status = get_step_status(7)
    icon = STATUS_ICONS.get(status, "○")
    with st.container(border=True):
        st.markdown(f"**{icon} 7. 视频发布**")

    final_path = st.session_state.get("ipb_m5_final_video_path", "")
    if not final_path or not Path(final_path).exists():
        st.warning("⚠️ 尚未合成最终视频，请先完成模块5")
        return

    # Summary card
    with st.container(border=True):
        st.markdown("**内容摘要**")

        cover_path = st.session_state.get("ipb_m6_cover_path", "")
        if cover_path and Path(cover_path).exists():
            thumb_col, info_col = st.columns([1, 3])
            with thumb_col:
                st.image(cover_path, use_container_width=True)
            with info_col:
                _render_meta_info()
        else:
            _render_meta_info()

    st.divider()

    # Download section
    st.markdown("**下载视频**")
    dl_col, note_col = st.columns([1, 2])
    with dl_col:
        try:
            with open(final_path, "rb") as f:
                video_bytes = f.read()
            st.download_button(
                label="⬇️ 下载最终视频",
                data=video_bytes,
                file_name="video.mp4",
                mime="video/mp4",
                use_container_width=True,
            )
        except Exception as e:
            st.error(str(e))
            logger.exception(e)
    with note_col:
        st.caption("适用于抖音 / 快手 / B站 / 视频号")

    st.divider()

    # Publishing section (coming soon)
    st.markdown("**一键发布**")
    pub_cols = st.columns(4)
    platforms = [
        ("抖音", "ipb_pub_douyin"),
        ("快手", "ipb_pub_kuaishou"),
        ("B站", "ipb_pub_bilibili"),
        ("视频号", "ipb_pub_shipinhao"),
    ]
    for col, (label, key) in zip(pub_cols, platforms):
        with col:
            st.button(
                f"发布到{label}",
                key=key,
                disabled=True,
                help="即将支持",
                use_container_width=True,
            )

    st.info("🔜 平台一键发布功能即将推出")
    # NOTE: step status is set to "done" only inside run_m7() (auto mode)
    # or when the user explicitly downloads, not here in the render path.


def _render_meta_info():
    title = st.session_state.get("ipb_m6_title", "")
    description = st.session_state.get("ipb_m6_description", "")
    hashtags = st.session_state.get("ipb_m6_hashtags", [])

    if title:
        st.markdown(f"**标题：** {title}")
    else:
        st.caption("标题：未设置")

    if description:
        st.markdown(f"**描述：** {description}")
    else:
        st.caption("描述：未设置")

    if hashtags:
        tags_display = "  ".join(f"`#{t}`" for t in hashtags)
        st.markdown(f"**标签：** {tags_display}")
    else:
        st.caption("标签：未设置")


async def run_m7(pixelle_video) -> bool:
    final_path = st.session_state.get("ipb_m5_final_video_path", "")
    if final_path and Path(final_path).exists():
        set_step_status(7, "done")
        return True
    return False
