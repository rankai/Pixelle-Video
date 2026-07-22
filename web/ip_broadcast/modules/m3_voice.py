import os

import streamlit as st

from web.ip_broadcast.modules.m3_preview import render_voice_preview as _render_voice_preview
from web.ip_broadcast.modules.m3_runner import (
    do_generate_voice as _do_generate_voice,
)
from web.ip_broadcast.modules.m3_runner import (
    run_m3,
)
from web.ip_broadcast.modules.m3_tts_config import (
    append_seed as _append_seed,
)
from web.ip_broadcast.modules.m3_tts_config import (
    append_workflow_tts_params as _append_workflow_tts_params,
)
from web.ip_broadcast.modules.m3_tts_config import (
    available_voice_locales as _available_voice_locales,
)
from web.ip_broadcast.modules.m3_tts_config import (
    build_preview_output_path as _build_preview_output_path,
)
from web.ip_broadcast.modules.m3_tts_config import (
    build_tts_kwargs as _build_tts_kwargs,
)
from web.ip_broadcast.modules.m3_tts_config import (
    comfy_edge_voice_options as _comfy_edge_voice_options,
)
from web.ip_broadcast.modules.m3_tts_config import (
    edge_voice_to_comfy_label as _edge_voice_to_comfy_label,
)
from web.ip_broadcast.modules.m3_tts_config import (
    format_comfy_edge_voice_label as _format_comfy_edge_voice_label,
)
from web.ip_broadcast.modules.m3_tts_config import (
    option_index as _option_index,
)
from web.ip_broadcast.modules.m3_tts_config import (
    render_comfyui_edge_options as _render_comfyui_edge_options,
)
from web.ip_broadcast.modules.m3_tts_config import (
    render_comfyui_mode_options as _render_comfyui_mode_options,
)
from web.ip_broadcast.modules.m3_tts_config import (
    render_index_options as _render_index_options,
)
from web.ip_broadcast.modules.m3_tts_config import (
    render_local_mode_options as _render_local_mode_options,
)
from web.ip_broadcast.modules.m3_tts_config import (
    render_sampling_options as _render_sampling_options,
)
from web.ip_broadcast.modules.m3_tts_config import (
    render_spark_options as _render_spark_options,
)
from web.ip_broadcast.modules.m3_tts_config import (
    render_tts_mode_selector as _render_tts_mode_selector,
)
from web.ip_broadcast.modules.m3_tts_config import (
    render_tts_workflow_selector as _render_tts_workflow_selector,
)
from web.ip_broadcast.modules.m3_tts_config import (
    workflow_kind_for as _workflow_kind,
)
from web.ip_broadcast.modules.m3_voice_references import (
    apply_reference_audio_form_reset as _apply_reference_audio_form_reset,
)
from web.ip_broadcast.modules.m3_voice_references import (
    clear_recorded_reference_audio as _clear_recorded_reference_audio,
)
from web.ip_broadcast.modules.m3_voice_references import (
    reference_audio_uploader_key as _reference_audio_uploader_key,
)
from web.ip_broadcast.modules.m3_voice_references import (
    render_voice_reference_library as _render_voice_reference_library,
)
from web.ip_broadcast.modules.m3_voice_references import (
    save_reference_audio as _save_reference_audio,
)
from web.ip_broadcast.modules.m3_voice_references import (
    set_selected_reference_audio_path as _set_selected_reference_audio_path,
)
from web.ip_broadcast.state import STATUS_ICONS, get_step_status
from web.ip_broadcast.status_ui import render_step_notice

__all__ = [
    "_append_seed",
    "_append_workflow_tts_params",
    "_apply_reference_audio_form_reset",
    "_available_voice_locales",
    "_build_preview_output_path",
    "_build_tts_kwargs",
    "_clear_recorded_reference_audio",
    "_comfy_edge_voice_options",
    "_do_generate_voice",
    "_edge_voice_to_comfy_label",
    "_format_comfy_edge_voice_label",
    "_option_index",
    "_reference_audio_uploader_key",
    "_render_comfyui_edge_options",
    "_render_comfyui_mode_options",
    "_render_index_options",
    "_render_local_mode_options",
    "_render_sampling_options",
    "_render_spark_options",
    "_render_tts_mode_selector",
    "_render_tts_workflow_selector",
    "_render_voice_preview",
    "_render_voice_reference_library",
    "_save_reference_audio",
    "_set_selected_reference_audio_path",
    "_workflow_kind",
    "render_m3_voice",
    "run_m3",
]


def render_m3_voice(pixelle_video, run_mode: str):
    """渲染模块3：声音生成"""
    step = 3
    status = get_step_status(step)
    icon = STATUS_ICONS.get(status, "○")
    generate_clicked = False

    with st.container(border=True):
        st.markdown(f"**{icon} 3. 声音生成**")

        has_copy = bool(st.session_state.get("ipb_m2_output", "").strip())
        if not has_copy:
            st.info("💡 在左侧「2. 改写文案」生成文案后即可合成语音")

        tts_mode = _render_tts_mode_selector()
        if tts_mode == "local":
            _render_local_mode_options()
        else:
            _render_comfyui_mode_options(pixelle_video)

        _render_voice_preview(pixelle_video)

        if run_mode == "manual":
            generate_clicked = st.button(
                "生成语音",
                key="ipb_m3_generate_btn",
                use_container_width=True,
                type="primary",
            )

        if generate_clicked:
            if not has_copy:
                st.warning("口播文案为空，请先完成「2. 改写文案」")
            else:
                _do_generate_voice(pixelle_video)

        audio_path = st.session_state.get("ipb_m3_audio_path", "")
        if audio_path and os.path.exists(audio_path):
            st.markdown("**预览生成的语音：**")
            st.audio(audio_path)
        render_step_notice(3)
