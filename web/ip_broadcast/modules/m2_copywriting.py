"""模块2：改写/生成文案 — 基于IP风格和选题改写或全新生成口播文案"""

import streamlit as st
from loguru import logger

from pixelle_video.prompts.ip_broadcast import build_rewrite_prompt
from web.ip_broadcast.state import (
    STATUS_ICONS,
    get_step_status,
    set_final_script,
    set_step_status,
)
from web.utils.async_helpers import run_async

DEFERRED_ACTION_M2_GENERATE = "m2_generate"


def render_m2_copywriting(pixelle_video, run_mode: str):
    step_icon = STATUS_ICONS.get(get_step_status(2), "○")
    with st.container(border=True):
        st.markdown(f"**{step_icon} 2. 文案确认**")
        source_label = st.session_state.get("ipb_source_label", "")
        if source_label:
            st.caption(f"来源：{source_label}")

        _ensure_editor_matches_final_script()
        st.text_area(
            "最终口播文案",
            height=260,
            key="ipb_final_script_editor",
            placeholder="在模块1生成文案后会自动填入，也可以直接在这里编辑...",
            on_change=_sync_final_script_from_editor,
        )

        with st.expander("改写设置", expanded=False):
            st.text_area(
                "写作风格指令",
                height=80,
                key="ipb_m2_style_prompt",
                placeholder="例如：口语化、亲切自然、有感染力",
            )
            st.number_input(
                "目标字数",
                min_value=50,
                max_value=1000,
                step=50,
                key="ipb_m2_word_count",
            )

        if run_mode == "manual" and st.button(
            "AI 改写/优化文案",
            key="ipb_m2_generate_btn",
            type="primary",
            use_container_width=True,
        ):
            _request_generate()



def _get_source_text() -> str:
    """Return the current final script to rewrite."""
    return st.session_state.get("ipb_final_script", "")


def _ensure_editor_matches_final_script():
    final_script = st.session_state.get("ipb_final_script", "")
    if st.session_state.get("_ipb_editor_synced_value") != final_script:
        st.session_state["ipb_final_script_editor"] = final_script
        st.session_state["_ipb_editor_synced_value"] = final_script


def _sync_final_script_from_editor():
    editor_value = st.session_state.get("ipb_final_script_editor", "")
    set_final_script(editor_value)
    st.session_state["_ipb_editor_synced_value"] = editor_value


def _request_generate():
    st.session_state["_ipb_deferred_action"] = DEFERRED_ACTION_M2_GENERATE


def _do_generate(pixelle_video):
    """Shared generation logic for both button placements."""
    source = _get_source_text().strip()
    if not source:
        st.warning("请先在模块1生成文案，或直接填写「最终口播文案」")
        return

    style = st.session_state.get("ipb_m2_style_prompt", "口语化、亲切自然、有感染力")
    word_count = st.session_state.get("ipb_m2_word_count", 200)

    set_step_status(2, "running")
    try:
        with st.spinner("生成中..."):
            output = run_async(
                pixelle_video.llm(
                    prompt=build_rewrite_prompt(source, style, word_count)
                )
            )
        set_final_script(output)
        set_step_status(2, "done")
        st.success("文案生成完成")
        st.rerun()
    except Exception as e:
        set_step_status(2, "error")
        st.error(str(e))
        logger.exception(e)


async def run_m2(pixelle_video) -> bool:
    """Run module 2 in auto mode. Returns True on success."""
    source = _get_source_text().strip()

    if not source:
        logger.warning("run_m2: no source text available from module 1, skipping")
        return False

    style = st.session_state.get("ipb_m2_style_prompt", "口语化、亲切自然、有感染力")
    word_count = st.session_state.get("ipb_m2_word_count", 200)

    set_step_status(2, "running")
    try:
        output = await pixelle_video.llm(
            prompt=build_rewrite_prompt(source, style, word_count)
        )
        set_final_script(output)
        set_step_status(2, "done")
        return True
    except Exception as e:
        set_step_status(2, "error")
        logger.exception(e)
        return False
