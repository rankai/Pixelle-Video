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
    """Local Edge TTS options: voice selector + speed slider."""
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

    speed = st.slider(
        "语速",
        min_value=0.5,
        max_value=2.0,
        step=0.1,
        value=float(st.session_state.get("ipb_m3_speed", 1.2)),
        key="ipb_m3_speed_slider",
    )
    st.session_state.ipb_m3_speed = speed


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
    """ComfyUI mode options: optional reference audio uploader."""
    tts_workflow_key = _render_tts_workflow_selector(pixelle_video)
    if tts_workflow_key:
        check_and_warn_selfhost_workflow(tts_workflow_key)

    st.caption("选择已保存的参考音频可克隆声音，不选择则使用工作流默认声音。")
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
    else:
        workflow = st.session_state.get("ipb_m3_tts_workflow", "")
        if workflow:
            kwargs["workflow"] = workflow
        ref_audio_path = st.session_state.get("ipb_m3_ref_audio_path", "")
        if ref_audio_path and os.path.exists(ref_audio_path):
            kwargs["ref_audio"] = ref_audio_path

    return kwargs


def _build_preview_output_path() -> str:
    return get_temp_path(f"ipb_preview_{uuid.uuid4().hex[:8]}.mp3")
