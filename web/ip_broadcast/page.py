"""IP broadcast page — top-level renderer with manual/auto run modes"""

import streamlit as st
from loguru import logger

from web.ip_broadcast.state import (
    get_completed_step_count,
    get_next_action,
    init_ip_broadcast_state,
    refresh_step_readiness,
    set_step_status,
)
from web.utils.async_helpers import run_async
from web.utils.streamlit_helpers import safe_rerun


def render_ip_broadcast_page(pixelle_video):
    init_ip_broadcast_state()

    st.markdown("## 🎙️ 老板IP口播智能体")
    st.caption("从对标学习到一键发布，全链路AI短视频生产流水线")

    refresh_step_readiness()
    run_mode = "manual"
    _render_production_console(pixelle_video)

    if st.session_state.get("_ipb_continue_requested"):
        st.session_state._ipb_continue_requested = False
        _run_from_current_state(pixelle_video)
        safe_rerun()

    st.divider()

    # ── 3-column layout: source/copy, voice/avatar, final/publish ──
    from web.ip_broadcast.modules.m1_benchmark import render_m1_benchmark
    from web.ip_broadcast.modules.m2_copywriting import render_m2_copywriting
    from web.ip_broadcast.modules.m3_voice import render_m3_voice
    from web.ip_broadcast.modules.m4_digital_human import render_m4_digital_human
    from web.ip_broadcast.modules.m5_postproduction import render_m5_postproduction
    from web.ip_broadcast.modules.m7_publish import render_m7_publish

    col1, col2, col3 = st.columns([1.05, 1, 1.05])

    with col1:
        render_m1_benchmark(pixelle_video, run_mode)
        render_m2_copywriting(pixelle_video, run_mode)

    with col2:
        render_m3_voice(pixelle_video, run_mode)
        render_m4_digital_human(pixelle_video, run_mode)

    with col3:
        render_m5_postproduction(pixelle_video, run_mode)
        render_m7_publish(pixelle_video, run_mode)

    _run_deferred_action(pixelle_video)


def _render_production_console(pixelle_video):
    action = get_next_action()
    done_count = get_completed_step_count()

    with st.container(border=True):
        title_col, action_col = st.columns([3, 1])
        with title_col:
            st.markdown("**生产主控台**")
            st.caption(f"下一步：{action.description}")
            st.progress(done_count / 6, text=f"进度：{done_count}/6")
        with action_col:
            st.markdown("<div style='height:26px'></div>", unsafe_allow_html=True)
            clicked = st.button(
                f"一键继续：{action.label}",
                key="ipb_primary_next_btn",
                type="primary",
                use_container_width=True,
                disabled=action.disabled or action.key in {"prepare_source", "publish"},
            )
            if clicked:
                st.session_state._ipb_continue_requested = True

        if action.key == "prepare_source":
            st.info("请选择下方「素材来源」，生成一段口播文案后即可继续。")
        elif action.key == "select_portrait":
            st.warning("请在「4. 数字人视频」中选择或上传形象后继续。")
        elif action.key == "publish":
            st.success("成片和发布素材已准备好，请在「6. 视频发布」下载。")


def _run_from_current_state(pixelle_video):
    """Continue from the current ready step until a user decision is required."""
    from web.ip_broadcast.modules.m2_copywriting import run_m2
    from web.ip_broadcast.modules.m3_voice import run_m3
    from web.ip_broadcast.modules.m4_digital_human import run_m4
    from web.ip_broadcast.modules.m5_postproduction import run_m5
    from web.ip_broadcast.modules.m7_publish import run_m7

    runners = {
        "rewrite": (2, run_m2, "文案确认"),
        "voice": (3, run_m3, "声音生成"),
        "digital_human": (4, run_m4, "数字人视频"),
        "postproduce": (5, run_m5, "一键成片"),
        "publish": (6, run_m7, "视频发布"),
    }

    placeholder = st.empty()
    while True:
        action = get_next_action()
        if action.key in {"prepare_source", "select_portrait", "publish"}:
            placeholder.info(action.description)
            return

        runner = runners.get(action.key)
        if not runner:
            placeholder.info(action.description)
            return

        step_num, runner_fn, label = runner
        set_step_status(step_num, "running")
        placeholder.info(f"正在执行：{label}（步骤 {step_num}/6）...")
        try:
            ok = run_async(runner_fn(pixelle_video))
            if ok:
                set_step_status(step_num, "done")
            else:
                set_step_status(step_num, "error")
                placeholder.error(f"步骤 {step_num}（{label}）执行失败，流程中止。")
                return
        except Exception as e:
            set_step_status(step_num, "error")
            placeholder.error(f"步骤 {step_num}（{label}）出错：{e}")
            logger.exception(e)
            return


def _run_deferred_action(pixelle_video):
    action = st.session_state.pop("_ipb_deferred_action", None)
    if not action:
        return

    from web.ip_broadcast.modules.m2_copywriting import (
        DEFERRED_ACTION_M2_GENERATE,
        _do_generate,
    )

    if action == DEFERRED_ACTION_M2_GENERATE:
        st.info("正在执行：AI 改写/优化文案。下方模块会保持显示。")
        _do_generate(pixelle_video)
