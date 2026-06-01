from pathlib import Path

import streamlit as st
from loguru import logger

from web.ip_broadcast.modules.m3_tts_config import (
    build_preview_output_path,
    build_tts_kwargs,
)
from web.utils.async_helpers import run_async


def render_voice_preview(pixelle_video) -> None:
    with st.expander("语音试听", expanded=False):
        preview_text = st.text_input(
            "试听文本",
            value=st.session_state.get("ipb_m3_preview_text", "大家好，这是一段测试语音。"),
            key="ipb_m3_preview_text",
        )
        if st.button("试听声音", key="ipb_m3_preview_btn", use_container_width=True):
            if not preview_text.strip():
                st.warning("请输入试听文本")
                return
            with st.spinner("正在生成试听语音..."):
                try:
                    output_path = build_preview_output_path()
                    kwargs = build_tts_kwargs(preview_text, output_path)
                    audio_path = run_async(pixelle_video.tts(**kwargs))
                    st.success("试听生成完成")
                    if audio_path and (Path(audio_path).exists() or str(audio_path).startswith("http")):
                        st.audio(audio_path)
                    else:
                        st.error("试听音频生成失败")
                except Exception as e:
                    st.error(str(e))
                    logger.exception(e)
