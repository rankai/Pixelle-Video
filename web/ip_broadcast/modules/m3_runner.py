import uuid

import streamlit as st
from loguru import logger

from pixelle_video.utils.os_util import get_temp_path
from web.ip_broadcast.modules.m3_tts_config import build_tts_kwargs
from web.ip_broadcast.state import mark_voice_generated, set_step_status
from web.ip_broadcast.status_ui import (
    hide_global_loading,
    set_step_notice,
    show_global_loading,
)
from web.utils.async_helpers import run_async
from web.utils.streamlit_helpers import safe_rerun


def do_generate_voice(pixelle_video) -> None:
    """Execute TTS generation and persist result in session state."""
    text = st.session_state.get("ipb_m2_output", "").strip()
    if not text:
        st.warning("口播文案为空，无法生成语音。")
        return

    output_path = get_temp_path(f"ipb_audio_{uuid.uuid4().hex[:8]}.mp3")

    set_step_status(3, "running")
    loading = show_global_loading("正在生成语音，请稍候...")
    with st.spinner("正在生成语音…"):
        try:
            tts_kwargs = build_tts_kwargs(text, output_path)
            audio_path = run_async(pixelle_video.tts(**tts_kwargs))

            mark_voice_generated(audio_path)
            set_step_notice(3, "success", "语音生成成功")
            safe_rerun()
        except Exception as e:
            set_step_status(3, "error")
            set_step_notice(3, "error", str(e))
            st.error(str(e))
            logger.exception(e)
        finally:
            hide_global_loading(loading)


async def run_m3(pixelle_video) -> bool:
    """Auto-run entry for pipeline mode. Returns True on success."""
    text = st.session_state.get("ipb_m2_output", "").strip()
    if not text:
        logger.warning("run_m3: ipb_m2_output is empty, skipping TTS")
        return False

    output_path = get_temp_path(f"ipb_audio_{uuid.uuid4().hex[:8]}.mp3")

    try:
        tts_kwargs = build_tts_kwargs(text, output_path)
        audio_path = await pixelle_video.tts(**tts_kwargs)

        mark_voice_generated(audio_path)
        logger.info(f"run_m3 completed: {audio_path}")
        return True
    except Exception as e:
        set_step_status(3, "error")
        set_step_notice(3, "error", str(e))
        logger.exception(e)
        return False
