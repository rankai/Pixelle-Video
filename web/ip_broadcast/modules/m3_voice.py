import os
import uuid
from pathlib import Path

import streamlit as st
from loguru import logger

from pixelle_video.services.voice_reference_service import VoiceReferenceService
from pixelle_video.tts_voices import EDGE_TTS_VOICES, get_voice_display_name
from pixelle_video.utils.os_util import get_temp_path
from web.ip_broadcast.state import (
    STATUS_ICONS,
    get_step_status,
    mark_voice_generated,
    set_step_status,
)
from web.ip_broadcast.status_ui import (
    hide_global_loading,
    render_step_notice,
    set_step_notice,
    show_global_loading,
)
from web.utils.async_helpers import run_async
from web.utils.streamlit_helpers import check_and_warn_selfhost_workflow, safe_rerun

LANGUAGE_LABELS = {
    "zh-CN": "中文（普通话）",
    "en-US": "英语（美国）",
    "en-GB": "英语（英国）",
    "ko-KR": "韩语",
    "fr-FR": "法语",
    "pt-PT": "葡萄牙语",
    "de-DE": "德语",
    "ru-RU": "俄语",
    "tr-TR": "土耳其语",
    "es-ES": "西班牙语",
}

COMFY_EDGE_LANGUAGE_PREFIX = {
    "zh-CN": "Chinese",
    "en-US": "English",
    "en-GB": "English",
    "ko-KR": "Korean",
    "fr-FR": "French",
    "pt-PT": "Portuguese",
    "de-DE": "German",
    "ru-RU": "Russian",
    "tr-TR": "Turkish",
    "es-ES": "Spanish",
}

SPARK_GENDER_OPTIONS = {"male": "男声", "female": "女声"}
SPARK_TONE_OPTIONS = {"low": "低", "moderate": "标准", "high": "高"}


def render_m3_voice(pixelle_video, run_mode: str):
    """渲染模块3：声音生成"""
    step = 3
    status = get_step_status(step)
    icon = STATUS_ICONS.get(status, "○")

    with st.container(border=True):
        header_col, btn_col = st.columns([3, 1])
        with header_col:
            st.markdown(f"**{icon} 3. 声音生成**")
        with btn_col:
            generate_clicked = False
            if run_mode == "manual":
                generate_clicked = st.button(
                    "生成语音",
                    key="ipb_m3_generate_btn",
                    use_container_width=True,
                    type="primary",
                )

        # Soft hint — does NOT hide the rest of the UI
        has_copy = bool(st.session_state.get("ipb_m2_output", "").strip())
        if not has_copy:
            st.info("💡 在左侧「2. 改写文案」生成文案后即可合成语音")

        tts_mode = _render_tts_mode_selector()
        if tts_mode == "local":
            _render_local_mode_options()
        else:
            _render_comfyui_mode_options(pixelle_video)

        _render_voice_preview(pixelle_video)

        # Generate button action — guard inside, not as early return
        if generate_clicked:
            if not has_copy:
                st.warning("口播文案为空，请先完成「2. 改写文案」")
            else:
                _do_generate_voice(pixelle_video)

        # Preview existing audio if available
        audio_path = st.session_state.get("ipb_m3_audio_path", "")
        if audio_path and os.path.exists(audio_path):
            st.markdown("**预览生成的语音：**")
            st.audio(audio_path)
        render_step_notice(3)


def _render_local_mode_options():
    """Local Edge TTS options: language, voice and compact advanced controls."""
    locale_options = _available_voice_locales()
    current_locale = st.session_state.get("ipb_m3_language", "zh-CN")
    if current_locale not in locale_options:
        current_locale = "zh-CN" if "zh-CN" in locale_options else locale_options[0]

    selected_locale = st.selectbox(
        "语言",
        options=locale_options,
        index=locale_options.index(current_locale),
        format_func=lambda locale: LANGUAGE_LABELS.get(locale, locale),
        key="ipb_m3_language_selectbox",
    )
    st.session_state.ipb_m3_language = selected_locale

    voice_ids = [v["id"] for v in EDGE_TTS_VOICES if v.get("locale") == selected_locale]
    if not voice_ids:
        voice_ids = [v["id"] for v in EDGE_TTS_VOICES]

    current_voice = st.session_state.get("ipb_m3_voice", "zh-CN-YunjianNeural")
    try:
        default_idx = voice_ids.index(current_voice)
    except ValueError:
        default_idx = 0

    selected_voice = st.selectbox(
        "选择声音",
        options=voice_ids,
        index=default_idx,
        format_func=lambda vid: get_voice_display_name(vid),
        key="ipb_m3_voice_selectbox",
    )
    st.session_state.ipb_m3_voice = selected_voice

    col_speed, col_pitch, col_volume = st.columns(3)
    with col_speed:
        speed = st.slider(
            "语速",
            min_value=0.5,
            max_value=2.0,
            step=0.1,
            value=float(st.session_state.get("ipb_m3_speed", 1.2)),
            key="ipb_m3_speed_slider",
        )
        st.session_state.ipb_m3_speed = speed
    with col_pitch:
        pitch = st.slider(
            "音调",
            min_value=-50,
            max_value=50,
            step=1,
            value=int(st.session_state.get("ipb_m3_pitch", 0)),
            key="ipb_m3_pitch_slider",
            help="Edge TTS 音调，单位 Hz。",
        )
        st.session_state.ipb_m3_pitch = pitch
    with col_volume:
        volume = st.slider(
            "音量",
            min_value=-50,
            max_value=50,
            step=1,
            value=int(st.session_state.get("ipb_m3_volume", 0)),
            key="ipb_m3_volume_slider",
            help="Edge TTS 音量增减百分比。",
        )
        st.session_state.ipb_m3_volume = volume


def _render_tts_mode_selector() -> str:
    tts_mode = st.radio(
        "TTS 推理模式",
        options=["local", "comfyui"],
        format_func=lambda x: "Edge TTS" if x == "local" else "ComfyUI 工作流 / 声音克隆",
        index=0 if st.session_state.get("ipb_m3_inference_mode", "local") == "local" else 1,
        horizontal=True,
        key="ipb_m3_mode_radio",
    )
    st.session_state.ipb_m3_inference_mode = tts_mode
    if tts_mode == "local":
        st.caption("本地 Edge TTS，速度快，适合常规中文口播。")
    else:
        st.caption("使用 ComfyUI/RunningHub TTS 工作流，可配合参考音频做声音克隆。")
    return tts_mode


def _render_comfyui_mode_options(pixelle_video):
    """ComfyUI mode options: workflow-specific controls and optional reference audio."""
    tts_workflow_key = _render_tts_workflow_selector(pixelle_video)
    if tts_workflow_key:
        check_and_warn_selfhost_workflow(tts_workflow_key)

    workflow_kind = _workflow_kind(tts_workflow_key or "")
    if workflow_kind == "edge":
        _render_comfyui_edge_options()
    elif workflow_kind == "spark":
        _render_spark_options()
    elif workflow_kind == "index":
        st.caption("选择已保存的参考音频可克隆声音，不选择则使用工作流默认声音。")
        _render_voice_reference_library()
        _render_index_options()
    else:
        st.caption("未知 TTS 工作流类型，仅显示参考音频与通用参数。")
        _render_voice_reference_library()


def _render_tts_workflow_selector(pixelle_video) -> str | None:
    workflows = pixelle_video.tts.list_workflows()
    workflow_options = [wf["display_name"] for wf in workflows]
    workflow_keys = [wf["key"] for wf in workflows]
    current_key = st.session_state.get("ipb_m3_tts_workflow", "")

    default_idx = 0
    if current_key in workflow_keys:
        default_idx = workflow_keys.index(current_key)

    if not workflow_options:
        st.warning("未找到 TTS 工作流，请检查 workflows 配置。")
        st.session_state.ipb_m3_tts_workflow = ""
        return None

    selected_display = st.selectbox(
        "TTS Workflow",
        workflow_options,
        index=default_idx,
        key="ipb_m3_tts_workflow_select",
    )
    selected_idx = workflow_options.index(selected_display)
    selected_key = workflow_keys[selected_idx]
    st.session_state.ipb_m3_tts_workflow = selected_key
    return selected_key


def _render_comfyui_edge_options() -> None:
    st.caption("Edge TTS 工作流支持语言、音色、语速和音调。")
    locale_options = _available_voice_locales()
    current_locale = st.session_state.get("ipb_m3_workflow_language", "zh-CN")
    if current_locale not in locale_options:
        current_locale = "zh-CN" if "zh-CN" in locale_options else locale_options[0]

    selected_locale = st.selectbox(
        "语言",
        options=locale_options,
        index=locale_options.index(current_locale),
        format_func=lambda locale: LANGUAGE_LABELS.get(locale, locale),
        key="ipb_m3_workflow_language_selectbox",
    )
    st.session_state.ipb_m3_workflow_language = selected_locale

    voice_options = _comfy_edge_voice_options(selected_locale)
    current_voice = st.session_state.get("ipb_m3_workflow_voice", "[Chinese] zh-CN Yunjian")
    if current_voice not in voice_options:
        current_voice = voice_options[0]

    selected_voice = st.selectbox(
        "工作流音色",
        options=voice_options,
        index=voice_options.index(current_voice),
        format_func=_format_comfy_edge_voice_label,
        key="ipb_m3_workflow_voice_selectbox",
    )
    st.session_state.ipb_m3_workflow_voice = selected_voice

    col_speed, col_pitch = st.columns(2)
    with col_speed:
        speed = st.slider(
            "语速",
            min_value=0.5,
            max_value=2.0,
            step=0.1,
            value=float(st.session_state.get("ipb_m3_workflow_speed", 1.0)),
            key="ipb_m3_workflow_speed_slider",
        )
        st.session_state.ipb_m3_workflow_speed = speed
    with col_pitch:
        pitch = st.slider(
            "音调",
            min_value=-50,
            max_value=50,
            step=1,
            value=int(st.session_state.get("ipb_m3_workflow_pitch", 0)),
            key="ipb_m3_workflow_pitch_slider",
            help="RunningHub Edge TTS 工作流音调参数。",
        )
        st.session_state.ipb_m3_workflow_pitch = pitch


def _render_spark_options() -> None:
    st.caption("Spark TTS 工作流支持性别、语速、音调和采样参数。")
    col_gender, col_speed, col_pitch = st.columns(3)
    with col_gender:
        gender = st.selectbox(
            "音色性别",
            options=list(SPARK_GENDER_OPTIONS),
            index=_option_index(
                list(SPARK_GENDER_OPTIONS),
                st.session_state.get("ipb_m3_spark_gender", "male"),
            ),
            format_func=lambda value: SPARK_GENDER_OPTIONS[value],
            key="ipb_m3_spark_gender_selectbox",
        )
        st.session_state.ipb_m3_spark_gender = gender
    with col_speed:
        speed = st.selectbox(
            "语速",
            options=list(SPARK_TONE_OPTIONS),
            index=_option_index(
                list(SPARK_TONE_OPTIONS),
                st.session_state.get("ipb_m3_spark_speed", "moderate"),
            ),
            format_func=lambda value: SPARK_TONE_OPTIONS[value],
            key="ipb_m3_spark_speed_selectbox",
        )
        st.session_state.ipb_m3_spark_speed = speed
    with col_pitch:
        pitch = st.selectbox(
            "音调",
            options=list(SPARK_TONE_OPTIONS),
            index=_option_index(
                list(SPARK_TONE_OPTIONS),
                st.session_state.get("ipb_m3_spark_pitch", "moderate"),
            ),
            format_func=lambda value: SPARK_TONE_OPTIONS[value],
            key="ipb_m3_spark_pitch_selectbox",
        )
        st.session_state.ipb_m3_spark_pitch = pitch

    _render_sampling_options(
        show_max_new_tokens=True,
        show_index_params=False,
        title="Spark 高级采样参数",
    )


def _render_index_options() -> None:
    _render_sampling_options(
        show_max_new_tokens=False,
        show_index_params=True,
        title="Index TTS 高级采样参数",
    )


def _render_sampling_options(
    *,
    show_max_new_tokens: bool,
    show_index_params: bool,
    title: str,
) -> None:
    with st.expander(title, expanded=False):
        if show_index_params:
            col_mode, col_sample = st.columns(2)
            with col_mode:
                mode = st.selectbox(
                    "生成模式",
                    options=["Auto"],
                    index=0,
                    key="ipb_m3_index_mode_selectbox",
                )
                st.session_state.ipb_m3_index_mode = mode
            with col_sample:
                do_sample_mode = st.selectbox(
                    "采样开关",
                    options=["on", "off"],
                    index=0
                    if st.session_state.get("ipb_m3_index_do_sample_mode", "on") == "on"
                    else 1,
                    key="ipb_m3_index_do_sample_mode_selectbox",
                )
                st.session_state.ipb_m3_index_do_sample_mode = do_sample_mode

        col_temp, col_top_p, col_top_k = st.columns(3)
        with col_temp:
            temperature = st.slider(
                "temperature",
                min_value=0.1,
                max_value=2.0,
                step=0.05,
                value=float(st.session_state.get("ipb_m3_temperature", 0.8)),
                key=f"{title}_temperature",
            )
            st.session_state.ipb_m3_temperature = temperature
        with col_top_p:
            top_p = st.slider(
                "top_p",
                min_value=0.1,
                max_value=1.0,
                step=0.05,
                value=float(st.session_state.get("ipb_m3_top_p", 0.9)),
                key=f"{title}_top_p",
            )
            st.session_state.ipb_m3_top_p = top_p
        with col_top_k:
            top_k = st.number_input(
                "top_k",
                min_value=1,
                max_value=200,
                value=int(st.session_state.get("ipb_m3_top_k", 30)),
                step=1,
                key=f"{title}_top_k",
            )
            st.session_state.ipb_m3_top_k = int(top_k)

        if show_index_params:
            col_beams, col_repeat, col_length = st.columns(3)
            with col_beams:
                num_beams = st.number_input(
                    "num_beams",
                    min_value=1,
                    max_value=10,
                    value=int(st.session_state.get("ipb_m3_num_beams", 3)),
                    step=1,
                    key="ipb_m3_num_beams_input",
                )
                st.session_state.ipb_m3_num_beams = int(num_beams)
            with col_repeat:
                repetition_penalty = st.number_input(
                    "repetition_penalty",
                    min_value=0.0,
                    max_value=20.0,
                    value=float(st.session_state.get("ipb_m3_repetition_penalty", 10.0)),
                    step=0.1,
                    key="ipb_m3_repetition_penalty_input",
                )
                st.session_state.ipb_m3_repetition_penalty = repetition_penalty
            with col_length:
                length_penalty = st.number_input(
                    "length_penalty",
                    min_value=-5.0,
                    max_value=5.0,
                    value=float(st.session_state.get("ipb_m3_length_penalty", 0.0)),
                    step=0.1,
                    key="ipb_m3_length_penalty_input",
                )
                st.session_state.ipb_m3_length_penalty = length_penalty

            col_mel, col_sentence = st.columns(2)
            with col_mel:
                max_mel_tokens = st.number_input(
                    "max_mel_tokens",
                    min_value=100,
                    max_value=5000,
                    value=int(st.session_state.get("ipb_m3_max_mel_tokens", 1815)),
                    step=10,
                    key="ipb_m3_max_mel_tokens_input",
                )
                st.session_state.ipb_m3_max_mel_tokens = int(max_mel_tokens)
            with col_sentence:
                max_tokens_per_sentence = st.number_input(
                    "max_tokens_per_sentence",
                    min_value=20,
                    max_value=500,
                    value=int(st.session_state.get("ipb_m3_max_tokens_per_sentence", 120)),
                    step=5,
                    key="ipb_m3_max_tokens_per_sentence_input",
                )
                st.session_state.ipb_m3_max_tokens_per_sentence = int(max_tokens_per_sentence)

        if show_max_new_tokens:
            col_max, col_sample = st.columns(2)
            with col_max:
                max_new_tokens = st.number_input(
                    "max_new_tokens",
                    min_value=100,
                    max_value=8000,
                    value=int(st.session_state.get("ipb_m3_max_new_tokens", 3000)),
                    step=100,
                    key="ipb_m3_max_new_tokens_input",
                )
                st.session_state.ipb_m3_max_new_tokens = int(max_new_tokens)
            with col_sample:
                do_sample = st.checkbox(
                    "do_sample",
                    value=bool(st.session_state.get("ipb_m3_do_sample", True)),
                    key="ipb_m3_do_sample_checkbox",
                )
                st.session_state.ipb_m3_do_sample = do_sample

        seed = st.number_input(
            "seed（0 表示使用工作流默认随机策略）",
            min_value=0,
            max_value=2**32 - 1,
            value=int(st.session_state.get("ipb_m3_seed", 0)),
            step=1,
            key=f"{title}_seed",
        )
        st.session_state.ipb_m3_seed = int(seed)


def _render_voice_reference_library():
    _apply_reference_audio_form_reset()

    svc = VoiceReferenceService()
    references = svc.list_references()
    reference_paths = {item.reference_id: item.asset_path() for item in references}

    options = [""] + [item.reference_id for item in references]
    labels = {"": "不使用参考音频"}
    labels.update({item.reference_id: f"{item.name}（{item.created_at}）" for item in references})

    current_id = st.session_state.get("ipb_m3_ref_audio_id", "")
    if current_id not in options:
        current_id = ""
    selected_id = st.selectbox(
        "参考音频库",
        options=options,
        index=options.index(current_id),
        format_func=lambda ref_id: labels.get(ref_id, ref_id),
        key="ipb_m3_ref_audio_select",
    )
    st.session_state.ipb_m3_ref_audio_id = selected_id
    _set_selected_reference_audio_path(reference_paths)

    selected_path = st.session_state.get("ipb_m3_ref_audio_path", "")
    if selected_path and os.path.exists(selected_path):
        st.audio(selected_path)

    with st.expander("保存新的参考音频", expanded=False):
        name = st.text_input(
            "声音名称",
            key="ipb_m3_new_ref_audio_name",
            placeholder="例如：老板本人声音、女主播A",
        )
        uploaded_ref = st.file_uploader(
            "上传参考音频",
            type=["mp3", "wav", "flac", "m4a"],
            key=_reference_audio_uploader_key(),
        )
        if uploaded_ref is not None:
            st.audio(uploaded_ref)
        if st.button("保存上传音频", key="ipb_m3_save_uploaded_ref_btn", use_container_width=True):
            _save_reference_audio(svc, name, uploaded_ref)

        if hasattr(st, "audio_input"):
            recorded_ref = st.audio_input(
                "直接录制参考音频",
                key="ipb_m3_ref_audio_recorder",
                help="浏览器提示时允许麦克风权限即可录制。",
            )
            if recorded_ref is not None:
                st.audio(recorded_ref)
                col_save, col_clear = st.columns(2)
                with col_save:
                    save_recording = st.button(
                        "保存录音",
                        key="ipb_m3_save_recorded_ref_btn",
                        use_container_width=True,
                    )
                with col_clear:
                    clear_recording = st.button(
                        "重新录制",
                        key="ipb_m3_clear_recorded_ref_btn",
                        use_container_width=True,
                    )
                if save_recording:
                    _save_reference_audio(svc, name, recorded_ref, default_ext="wav")
                if clear_recording:
                    _clear_recorded_reference_audio()
        else:
            st.caption("当前 Streamlit 版本暂不支持浏览器录音，请先上传音频文件。")


def _set_selected_reference_audio_path(reference_paths: dict[str, str]) -> None:
    selected_id = st.session_state.get("ipb_m3_ref_audio_id", "")
    selected_path = reference_paths.get(selected_id, "")
    st.session_state.ipb_m3_ref_audio_path = selected_path if selected_path and os.path.exists(selected_path) else ""


def _clear_recorded_reference_audio() -> None:
    st.session_state.pop("ipb_m3_ref_audio_recorder", None)
    safe_rerun()


def _apply_reference_audio_form_reset() -> None:
    saved_id = st.session_state.pop("_ipb_m3_ref_audio_saved_id", "")
    if not saved_id:
        return

    st.session_state.ipb_m3_ref_audio_id = saved_id
    st.session_state.ipb_m3_ref_audio_select = saved_id
    st.session_state.ipb_m3_new_ref_audio_name = ""
    st.session_state.ipb_m3_ref_audio_uploader_nonce = (
        int(st.session_state.get("ipb_m3_ref_audio_uploader_nonce", 0)) + 1
    )
    st.session_state.pop("ipb_m3_ref_audio_recorder", None)


def _reference_audio_uploader_key() -> str:
    nonce = int(st.session_state.get("ipb_m3_ref_audio_uploader_nonce", 0))
    return f"ipb_m3_ref_audio_uploader_{nonce}"


def _save_reference_audio(
    svc: VoiceReferenceService,
    name: str,
    uploaded_audio,
    default_ext: str | None = None,
) -> None:
    clean_name = name.strip()
    if not clean_name:
        st.warning("请先填写声音名称。")
        return
    if uploaded_audio is None:
        st.warning("请先上传或录制参考音频。")
        return

    try:
        ext = default_ext or uploaded_audio.name.rsplit(".", 1)[-1].lower()
        info = svc.save_reference(clean_name, uploaded_audio.getvalue(), ext)
        st.session_state.ipb_m3_ref_audio_id = info.reference_id
        st.session_state.ipb_m3_ref_audio_path = info.asset_path()
        st.session_state._ipb_m3_ref_audio_saved_id = info.reference_id
        st.success(f"参考音频「{clean_name}」已保存。")
        safe_rerun()
    except Exception as e:
        st.error(str(e))
        logger.exception(e)


def _render_voice_preview(pixelle_video):
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
                    output_path = _build_preview_output_path()
                    kwargs = _build_tts_kwargs(preview_text, output_path)
                    audio_path = run_async(pixelle_video.tts(**kwargs))
                    st.success("试听生成完成")
                    if audio_path and (Path(audio_path).exists() or str(audio_path).startswith("http")):
                        st.audio(audio_path)
                    else:
                        st.error("试听音频生成失败")
                except Exception as e:
                    st.error(str(e))
                    logger.exception(e)


def _do_generate_voice(pixelle_video):
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
            tts_kwargs = _build_tts_kwargs(text, output_path)
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
        tts_kwargs = _build_tts_kwargs(text, output_path)
        audio_path = await pixelle_video.tts(**tts_kwargs)

        mark_voice_generated(audio_path)
        logger.info(f"run_m3 completed: {audio_path}")
        return True
    except Exception as e:
        set_step_status(3, "error")
        logger.exception(e)
        return False


def _build_tts_kwargs(text: str, output_path: str) -> dict:
    inference_mode = st.session_state.get("ipb_m3_inference_mode", "local")
    kwargs = {
        "text": text,
        "inference_mode": inference_mode,
        "output_path": output_path,
    }

    if inference_mode == "local":
        kwargs["voice"] = st.session_state.get("ipb_m3_voice", "zh-CN-YunjianNeural")
        kwargs["speed"] = float(st.session_state.get("ipb_m3_speed", 1.2))
        kwargs["pitch"] = int(st.session_state.get("ipb_m3_pitch", 0))
        kwargs["volume"] = int(st.session_state.get("ipb_m3_volume", 0))
    else:
        workflow = st.session_state.get("ipb_m3_tts_workflow", "")
        if workflow:
            kwargs["workflow"] = workflow
        ref_audio_path = st.session_state.get("ipb_m3_ref_audio_path", "")
        if ref_audio_path and os.path.exists(ref_audio_path):
            kwargs["ref_audio"] = ref_audio_path
        _append_workflow_tts_params(kwargs, workflow)

    return kwargs


def _build_preview_output_path() -> str:
    return get_temp_path(f"ipb_preview_{uuid.uuid4().hex[:8]}.mp3")


def _append_workflow_tts_params(kwargs: dict, workflow: str) -> None:
    workflow_kind = _workflow_kind(workflow)
    if workflow_kind == "edge":
        kwargs["voice"] = st.session_state.get("ipb_m3_workflow_voice", "[Chinese] zh-CN Yunjian")
        kwargs["speed"] = float(st.session_state.get("ipb_m3_workflow_speed", 1.0))
        kwargs["pitch"] = int(st.session_state.get("ipb_m3_workflow_pitch", 0))
    elif workflow_kind == "spark":
        kwargs["gender"] = st.session_state.get("ipb_m3_spark_gender", "male")
        kwargs["speed"] = st.session_state.get("ipb_m3_spark_speed", "moderate")
        kwargs["pitch"] = st.session_state.get("ipb_m3_spark_pitch", "moderate")
        kwargs["temperature"] = float(st.session_state.get("ipb_m3_temperature", 0.8))
        kwargs["top_k"] = int(st.session_state.get("ipb_m3_top_k", 30))
        kwargs["top_p"] = float(st.session_state.get("ipb_m3_top_p", 0.9))
        kwargs["max_new_tokens"] = int(st.session_state.get("ipb_m3_max_new_tokens", 3000))
        kwargs["do_sample"] = bool(st.session_state.get("ipb_m3_do_sample", True))
        _append_seed(kwargs)
    elif workflow_kind == "index":
        kwargs["mode"] = st.session_state.get("ipb_m3_index_mode", "Auto")
        kwargs["do_sample_mode"] = st.session_state.get("ipb_m3_index_do_sample_mode", "on")
        kwargs["temperature"] = float(st.session_state.get("ipb_m3_temperature", 0.8))
        kwargs["top_p"] = float(st.session_state.get("ipb_m3_top_p", 0.9))
        kwargs["top_k"] = int(st.session_state.get("ipb_m3_top_k", 30))
        kwargs["num_beams"] = int(st.session_state.get("ipb_m3_num_beams", 3))
        kwargs["repetition_penalty"] = float(st.session_state.get("ipb_m3_repetition_penalty", 10.0))
        kwargs["length_penalty"] = float(st.session_state.get("ipb_m3_length_penalty", 0.0))
        kwargs["max_mel_tokens"] = int(st.session_state.get("ipb_m3_max_mel_tokens", 1815))
        kwargs["max_tokens_per_sentence"] = int(
            st.session_state.get("ipb_m3_max_tokens_per_sentence", 120)
        )
        _append_seed(kwargs)


def _append_seed(kwargs: dict) -> None:
    seed = int(st.session_state.get("ipb_m3_seed", 0))
    if seed > 0:
        kwargs["seed"] = seed


def _workflow_kind(workflow: str) -> str:
    workflow_name = (workflow or "").lower()
    if "spark" in workflow_name:
        return "spark"
    if "index" in workflow_name:
        return "index"
    if "edge" in workflow_name:
        return "edge"
    return "generic"


def _available_voice_locales() -> list[str]:
    locales = []
    for voice in EDGE_TTS_VOICES:
        locale = voice.get("locale")
        if locale and locale not in locales:
            locales.append(locale)
    return locales or ["zh-CN"]


def _comfy_edge_voice_options(locale: str) -> list[str]:
    voices = [
        _edge_voice_to_comfy_label(voice)
        for voice in EDGE_TTS_VOICES
        if voice.get("locale") == locale
    ]
    return voices or ["[Chinese] zh-CN Yunjian"]


def _edge_voice_to_comfy_label(voice: dict) -> str:
    locale = voice.get("locale", "zh-CN")
    language = COMFY_EDGE_LANGUAGE_PREFIX.get(locale, locale)
    name = voice.get("id", "zh-CN-YunjianNeural").removeprefix(f"{locale}-")
    name = name.removesuffix("Neural")
    return f"[{language}] {locale} {name}"


def _format_comfy_edge_voice_label(value: str) -> str:
    try:
        _language, rest = value.split("] ", 1)
        locale, name = rest.split(" ", 1)
        return f"{LANGUAGE_LABELS.get(locale, locale)} · {name}"
    except ValueError:
        return value


def _option_index(options: list[str], current: str) -> int:
    return options.index(current) if current in options else 0
