import os
import uuid

import streamlit as st

from pixelle_video.tts_voices import EDGE_TTS_VOICES, get_voice_display_name
from pixelle_video.utils.os_util import get_temp_path
from web.ip_broadcast.modules.m3_voice_references import render_voice_reference_library
from web.utils.streamlit_helpers import check_and_warn_selfhost_workflow

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


def render_tts_mode_selector() -> str:
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


def render_local_mode_options() -> None:
    locale_options = available_voice_locales()
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
    default_idx = voice_ids.index(current_voice) if current_voice in voice_ids else 0

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
        st.session_state.ipb_m3_speed = st.slider(
            "语速",
            min_value=0.5,
            max_value=2.0,
            step=0.1,
            value=float(st.session_state.get("ipb_m3_speed", 1.2)),
            key="ipb_m3_speed_slider",
        )
    with col_pitch:
        st.session_state.ipb_m3_pitch = st.slider(
            "音调",
            min_value=-50,
            max_value=50,
            step=1,
            value=int(st.session_state.get("ipb_m3_pitch", 0)),
            key="ipb_m3_pitch_slider",
            help="Edge TTS 音调，单位 Hz。",
        )
    with col_volume:
        st.session_state.ipb_m3_volume = st.slider(
            "音量",
            min_value=-50,
            max_value=50,
            step=1,
            value=int(st.session_state.get("ipb_m3_volume", 0)),
            key="ipb_m3_volume_slider",
            help="Edge TTS 音量增减百分比。",
        )


def render_comfyui_mode_options(pixelle_video) -> None:
    tts_workflow_key = render_tts_workflow_selector(pixelle_video)
    if tts_workflow_key:
        check_and_warn_selfhost_workflow(tts_workflow_key)

    workflow_kind = workflow_kind_for(tts_workflow_key or "")
    if workflow_kind == "edge":
        render_comfyui_edge_options()
    elif workflow_kind == "spark":
        render_spark_options()
    elif workflow_kind == "index":
        st.caption("选择已保存的参考音频可克隆声音，不选择则使用工作流默认声音。")
        render_voice_reference_library()
        render_index_options()
    else:
        st.caption("未知 TTS 工作流类型，仅显示参考音频与通用参数。")
        render_voice_reference_library()


def render_tts_workflow_selector(pixelle_video) -> str | None:
    workflows = pixelle_video.tts.list_workflows()
    workflow_options = [wf["display_name"] for wf in workflows]
    workflow_keys = [wf["key"] for wf in workflows]
    current_key = st.session_state.get("ipb_m3_tts_workflow", "")

    default_idx = workflow_keys.index(current_key) if current_key in workflow_keys else 0
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


def render_comfyui_edge_options() -> None:
    st.caption("Edge TTS 工作流支持语言、音色、语速和音调。")
    locale_options = available_voice_locales()
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

    voice_options = comfy_edge_voice_options(selected_locale)
    current_voice = st.session_state.get("ipb_m3_workflow_voice", "[Chinese] zh-CN Yunjian")
    if current_voice not in voice_options:
        current_voice = voice_options[0]

    selected_voice = st.selectbox(
        "工作流音色",
        options=voice_options,
        index=voice_options.index(current_voice),
        format_func=format_comfy_edge_voice_label,
        key="ipb_m3_workflow_voice_selectbox",
    )
    st.session_state.ipb_m3_workflow_voice = selected_voice

    col_speed, col_pitch = st.columns(2)
    with col_speed:
        st.session_state.ipb_m3_workflow_speed = st.slider(
            "语速",
            min_value=0.5,
            max_value=2.0,
            step=0.1,
            value=float(st.session_state.get("ipb_m3_workflow_speed", 1.0)),
            key="ipb_m3_workflow_speed_slider",
        )
    with col_pitch:
        st.session_state.ipb_m3_workflow_pitch = st.slider(
            "音调",
            min_value=-50,
            max_value=50,
            step=1,
            value=int(st.session_state.get("ipb_m3_workflow_pitch", 0)),
            key="ipb_m3_workflow_pitch_slider",
            help="RunningHub Edge TTS 工作流音调参数。",
        )


def render_spark_options() -> None:
    st.caption("Spark TTS 工作流支持性别、语速、音调和采样参数。")
    col_gender, col_speed, col_pitch = st.columns(3)
    with col_gender:
        gender = st.selectbox(
            "音色性别",
            options=list(SPARK_GENDER_OPTIONS),
            index=option_index(list(SPARK_GENDER_OPTIONS), st.session_state.get("ipb_m3_spark_gender", "male")),
            format_func=lambda value: SPARK_GENDER_OPTIONS[value],
            key="ipb_m3_spark_gender_selectbox",
        )
        st.session_state.ipb_m3_spark_gender = gender
    with col_speed:
        speed = st.selectbox(
            "语速",
            options=list(SPARK_TONE_OPTIONS),
            index=option_index(list(SPARK_TONE_OPTIONS), st.session_state.get("ipb_m3_spark_speed", "moderate")),
            format_func=lambda value: SPARK_TONE_OPTIONS[value],
            key="ipb_m3_spark_speed_selectbox",
        )
        st.session_state.ipb_m3_spark_speed = speed
    with col_pitch:
        pitch = st.selectbox(
            "音调",
            options=list(SPARK_TONE_OPTIONS),
            index=option_index(list(SPARK_TONE_OPTIONS), st.session_state.get("ipb_m3_spark_pitch", "moderate")),
            format_func=lambda value: SPARK_TONE_OPTIONS[value],
            key="ipb_m3_spark_pitch_selectbox",
        )
        st.session_state.ipb_m3_spark_pitch = pitch
    render_sampling_options(show_max_new_tokens=True, show_index_params=False, title="Spark 高级采样参数")


def render_index_options() -> None:
    render_sampling_options(show_max_new_tokens=False, show_index_params=True, title="Index TTS 高级采样参数")


def render_sampling_options(*, show_max_new_tokens: bool, show_index_params: bool, title: str) -> None:
    with st.expander(title, expanded=False):
        if show_index_params:
            _render_index_sampling_header()
        _render_common_sampling_controls(title)
        if show_index_params:
            _render_index_sampling_controls()
        if show_max_new_tokens:
            _render_spark_sampling_controls()
        seed = st.number_input(
            "seed（0 表示使用工作流默认随机策略）",
            min_value=0,
            max_value=2**32 - 1,
            value=int(st.session_state.get("ipb_m3_seed", 0)),
            step=1,
            key=f"{title}_seed",
        )
        st.session_state.ipb_m3_seed = int(seed)


def _render_index_sampling_header() -> None:
    col_mode, col_sample = st.columns(2)
    with col_mode:
        st.session_state.ipb_m3_index_mode = st.selectbox(
            "生成模式",
            options=["Auto"],
            index=0,
            key="ipb_m3_index_mode_selectbox",
        )
    with col_sample:
        st.session_state.ipb_m3_index_do_sample_mode = st.selectbox(
            "采样开关",
            options=["on", "off"],
            index=0 if st.session_state.get("ipb_m3_index_do_sample_mode", "on") == "on" else 1,
            key="ipb_m3_index_do_sample_mode_selectbox",
        )


def _render_common_sampling_controls(title: str) -> None:
    col_temp, col_top_p, col_top_k = st.columns(3)
    with col_temp:
        st.session_state.ipb_m3_temperature = st.slider(
            "temperature",
            min_value=0.1,
            max_value=2.0,
            step=0.05,
            value=float(st.session_state.get("ipb_m3_temperature", 0.8)),
            key=f"{title}_temperature",
        )
    with col_top_p:
        st.session_state.ipb_m3_top_p = st.slider(
            "top_p",
            min_value=0.1,
            max_value=1.0,
            step=0.05,
            value=float(st.session_state.get("ipb_m3_top_p", 0.9)),
            key=f"{title}_top_p",
        )
    with col_top_k:
        st.session_state.ipb_m3_top_k = int(
            st.number_input(
                "top_k",
                min_value=1,
                max_value=200,
                value=int(st.session_state.get("ipb_m3_top_k", 30)),
                step=1,
                key=f"{title}_top_k",
            )
        )


def _render_index_sampling_controls() -> None:
    col_beams, col_repeat, col_length = st.columns(3)
    with col_beams:
        st.session_state.ipb_m3_num_beams = int(
            st.number_input("num_beams", min_value=1, max_value=10, value=int(st.session_state.get("ipb_m3_num_beams", 3)), step=1, key="ipb_m3_num_beams_input")
        )
    with col_repeat:
        st.session_state.ipb_m3_repetition_penalty = st.number_input(
            "repetition_penalty", min_value=0.0, max_value=20.0, value=float(st.session_state.get("ipb_m3_repetition_penalty", 10.0)), step=0.1, key="ipb_m3_repetition_penalty_input"
        )
    with col_length:
        st.session_state.ipb_m3_length_penalty = st.number_input(
            "length_penalty", min_value=-5.0, max_value=5.0, value=float(st.session_state.get("ipb_m3_length_penalty", 0.0)), step=0.1, key="ipb_m3_length_penalty_input"
        )

    col_mel, col_sentence = st.columns(2)
    with col_mel:
        st.session_state.ipb_m3_max_mel_tokens = int(
            st.number_input("max_mel_tokens", min_value=100, max_value=5000, value=int(st.session_state.get("ipb_m3_max_mel_tokens", 1815)), step=10, key="ipb_m3_max_mel_tokens_input")
        )
    with col_sentence:
        st.session_state.ipb_m3_max_tokens_per_sentence = int(
            st.number_input("max_tokens_per_sentence", min_value=20, max_value=500, value=int(st.session_state.get("ipb_m3_max_tokens_per_sentence", 120)), step=5, key="ipb_m3_max_tokens_per_sentence_input")
        )


def _render_spark_sampling_controls() -> None:
    col_max, col_sample = st.columns(2)
    with col_max:
        st.session_state.ipb_m3_max_new_tokens = int(
            st.number_input("max_new_tokens", min_value=100, max_value=8000, value=int(st.session_state.get("ipb_m3_max_new_tokens", 3000)), step=100, key="ipb_m3_max_new_tokens_input")
        )
    with col_sample:
        st.session_state.ipb_m3_do_sample = st.checkbox(
            "do_sample",
            value=bool(st.session_state.get("ipb_m3_do_sample", True)),
            key="ipb_m3_do_sample_checkbox",
        )


def build_tts_kwargs(text: str, output_path: str) -> dict:
    inference_mode = st.session_state.get("ipb_m3_inference_mode", "local")
    kwargs = {"text": text, "inference_mode": inference_mode, "output_path": output_path}

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
        append_workflow_tts_params(kwargs, workflow)
    return kwargs


def build_preview_output_path() -> str:
    return get_temp_path(f"ipb_preview_{uuid.uuid4().hex[:8]}.mp3")


def append_workflow_tts_params(kwargs: dict, workflow: str) -> None:
    workflow_kind = workflow_kind_for(workflow)
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
        append_seed(kwargs)
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
        kwargs["max_tokens_per_sentence"] = int(st.session_state.get("ipb_m3_max_tokens_per_sentence", 120))
        append_seed(kwargs)


def append_seed(kwargs: dict) -> None:
    seed = int(st.session_state.get("ipb_m3_seed", 0))
    if seed > 0:
        kwargs["seed"] = seed


def workflow_kind_for(workflow: str) -> str:
    workflow_name = (workflow or "").lower()
    if "spark" in workflow_name:
        return "spark"
    if "index" in workflow_name:
        return "index"
    if "edge" in workflow_name:
        return "edge"
    return "generic"


def available_voice_locales() -> list[str]:
    locales = []
    for voice in EDGE_TTS_VOICES:
        locale = voice.get("locale")
        if locale and locale not in locales:
            locales.append(locale)
    return locales or ["zh-CN"]


def comfy_edge_voice_options(locale: str) -> list[str]:
    voices = [
        edge_voice_to_comfy_label(voice)
        for voice in EDGE_TTS_VOICES
        if voice.get("locale") == locale
    ]
    return voices or ["[Chinese] zh-CN Yunjian"]


def edge_voice_to_comfy_label(voice: dict) -> str:
    locale = voice.get("locale", "zh-CN")
    language = COMFY_EDGE_LANGUAGE_PREFIX.get(locale, locale)
    name = voice.get("id", "zh-CN-YunjianNeural").removeprefix(f"{locale}-")
    name = name.removesuffix("Neural")
    return f"[{language}] {locale} {name}"


def format_comfy_edge_voice_label(value: str) -> str:
    try:
        _language, rest = value.split("] ", 1)
        locale, name = rest.split(" ", 1)
        return f"{LANGUAGE_LABELS.get(locale, locale)} · {name}"
    except ValueError:
        return value


def option_index(options: list[str], current: str) -> int:
    return options.index(current) if current in options else 0
