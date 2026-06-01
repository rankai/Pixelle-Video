import os

import streamlit as st
from loguru import logger

from pixelle_video.services.voice_reference_service import VoiceReferenceService
from web.utils.streamlit_helpers import safe_rerun


def render_voice_reference_library() -> None:
    apply_reference_audio_form_reset()

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
    set_selected_reference_audio_path(reference_paths)

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
            key=reference_audio_uploader_key(),
        )
        if uploaded_ref is not None:
            st.audio(uploaded_ref)
        if st.button("保存上传音频", key="ipb_m3_save_uploaded_ref_btn", use_container_width=True):
            save_reference_audio(svc, name, uploaded_ref)

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
                    save_reference_audio(svc, name, recorded_ref, default_ext="wav")
                if clear_recording:
                    clear_recorded_reference_audio()
        else:
            st.caption("当前 Streamlit 版本暂不支持浏览器录音，请先上传音频文件。")


def set_selected_reference_audio_path(reference_paths: dict[str, str]) -> None:
    selected_id = st.session_state.get("ipb_m3_ref_audio_id", "")
    selected_path = reference_paths.get(selected_id, "")
    st.session_state.ipb_m3_ref_audio_path = (
        selected_path if selected_path and os.path.exists(selected_path) else ""
    )


def clear_recorded_reference_audio() -> None:
    st.session_state.pop("ipb_m3_ref_audio_recorder", None)
    safe_rerun()


def apply_reference_audio_form_reset() -> None:
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


def reference_audio_uploader_key() -> str:
    nonce = int(st.session_state.get("ipb_m3_ref_audio_uploader_nonce", 0))
    return f"ipb_m3_ref_audio_uploader_{nonce}"


def save_reference_audio(
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
