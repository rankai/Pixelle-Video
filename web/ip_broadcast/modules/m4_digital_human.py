import os
import subprocess
import uuid

import streamlit as st
from loguru import logger

from pixelle_video.utils.os_util import get_temp_path
from web.ip_broadcast.state import STATUS_ICONS, get_step_status, set_step_status
from web.ip_broadcast.status_ui import render_step_notice, set_step_notice, show_global_loading
from web.utils.async_helpers import run_async
from web.utils.streamlit_helpers import safe_rerun


def render_m4_digital_human(pixelle_video, run_mode: str):
    """渲染模块4：数字人视频生成"""
    step = 4
    status = get_step_status(step)
    icon = STATUS_ICONS.get(status, "○")

    with st.container(border=True):
        header_col, btn_col = st.columns([3, 1])
        with header_col:
            st.markdown(f"**{icon} 4. 数字人视频**")
        with btn_col:
            generate_clicked = False
            if run_mode == "manual":
                generate_clicked = st.button(
                    "生成视频",
                    key="ipb_m4_generate_btn",
                    use_container_width=True,
                    type="primary",
                )

        # Soft hint — portrait library is always accessible
        has_audio = bool(st.session_state.get("ipb_m3_audio_path", "").strip())
        if not has_audio:
            st.info("💡 在左侧「3. 声音生成」完成后即可合成数字人视频")

        # ----------------------------------------------------------------
        # Portrait library management (collapsed by default)
        # ----------------------------------------------------------------
        with st.expander("📁 形象库管理", expanded=False):
            _render_portrait_library(pixelle_video)

        # ----------------------------------------------------------------
        # Portrait selection (outside expander)
        # ----------------------------------------------------------------
        _render_portrait_selection(pixelle_video)
        _render_workflow_options()

        # Generate button action — guard inside, not as early return
        if generate_clicked:
            if not has_audio:
                st.warning("请先完成「3. 声音生成」")
            else:
                _do_generate_video(pixelle_video)

        # Preview existing video if available
        dh_video_path = st.session_state.get("ipb_m4_dh_video_path", "")
        if dh_video_path and os.path.exists(dh_video_path):
            st.markdown("**预览生成的数字人视频：**")
            st.video(dh_video_path)
        render_step_notice(4)


def _get_portrait_svc(pixelle_video):
    """Return PortraitService, constructing it on-demand if the cached core is stale."""
    svc = getattr(pixelle_video, "portrait", None)
    if svc is None:
        from pixelle_video.services.portrait_service import PortraitService as _PS
        pixelle_video.portrait = _PS()
        svc = pixelle_video.portrait
    return svc


def _get_dh_svc(pixelle_video):
    """Return DigitalHumanService, constructing it on-demand if the cached core is stale."""
    svc = getattr(pixelle_video, "digital_human", None)
    if svc is None:
        from pixelle_video.services.digital_human_service import DigitalHumanService as _DHS
        pixelle_video.digital_human = _DHS(pixelle_video)
        svc = pixelle_video.digital_human
    return svc


def _render_portrait_library(pixelle_video):
    """Render the portrait grid + upload form inside the expander."""
    portrait_svc = _get_portrait_svc(pixelle_video)
    portraits = portrait_svc.list_portraits()

    if portraits:
        st.markdown("**已有形象**")
        cols_per_row = 4
        rows = [portraits[i : i + cols_per_row] for i in range(0, len(portraits), cols_per_row)]
        for row in rows:
            cols = st.columns(cols_per_row)
            for col, p in zip(cols, row):
                with col:
                    if p.exists():
                        if p.is_video():
                            st.video(p.asset_path())
                        else:
                            st.image(p.asset_path(), width=120)
                    else:
                        st.caption("（素材缺失）")
                    st.caption(p.name)
                    st.caption("视频形象" if p.is_video() else "图片形象")
                    st.caption(p.created_at)
                    if st.button("🗑️", key=f"del_portrait_{p.portrait_id}"):
                        try:
                            portrait_svc.delete_portrait(p.portrait_id)
                            # Clear selection if deleted portrait was selected
                            if st.session_state.get("ipb_m4_portrait_id") == p.portrait_id:
                                st.session_state.ipb_m4_portrait_id = ""
                        except Exception as e:
                            st.error(str(e))
                            logger.exception(e)
                        safe_rerun()
    else:
        st.info("暂无形象，请在下方上传。")

    st.markdown("---")
    st.markdown("**上传新形象**")
    st.caption("支持静态图片，也支持闭口形象视频（mp4/mov/webm）。视频会作为数字人生成的形象素材传入。")

    new_name = st.text_input(
        "形象名称",
        key="ipb_new_portrait_name",
        placeholder="请输入形象名称",
    )
    uploaded_img = st.file_uploader(
        "选择图片或闭口视频",
        type=["jpg", "jpeg", "png", "webp", "mp4", "mov", "webm"],
        key="ipb_new_portrait_uploader",
    )

    if st.button("保存形象", key="ipb_save_portrait_btn"):
        if not new_name.strip():
            st.warning("请填写形象名称。")
        elif uploaded_img is None:
            st.warning("请上传形象图片或闭口视频。")
        else:
            try:
                ext = uploaded_img.name.rsplit(".", 1)[-1].lower()
                portrait_svc.save_portrait(new_name.strip(), uploaded_img.getvalue(), ext)
                st.success(f"形象「{new_name.strip()}」已保存。")
            except Exception as e:
                st.error(str(e))
                logger.exception(e)
            safe_rerun()


def _render_portrait_selection(pixelle_video):
    """Render radio-button portrait selector + thumbnail preview."""
    portrait_svc = _get_portrait_svc(pixelle_video)
    portraits = portrait_svc.list_portraits()

    if not portraits:
        st.info("暂无形象，请在上方形象库中上传。")
        st.session_state.ipb_m4_portrait_id = ""
        return

    options = [p.portrait_id for p in portraits]
    labels = {p.portrait_id: f"{p.name}（{p.created_at}）" for p in portraits}

    current_id = st.session_state.get("ipb_m4_portrait_id", "")
    try:
        default_idx = options.index(current_id) if current_id in options else 0
    except ValueError:
        default_idx = 0

    selected_id = st.radio(
        "选择数字人形象",
        options=options,
        index=default_idx,
        format_func=lambda pid: labels.get(pid, pid),
        key="ipb_m4_portrait_radio",
    )
    st.session_state.ipb_m4_portrait_id = selected_id

    # Show preview thumbnail for selected portrait
    portrait_map = {p.portrait_id: p for p in portraits}
    if selected_id and selected_id in portrait_map:
        selected_portrait = portrait_map[selected_id]
        if selected_portrait.exists():
            if selected_portrait.is_video():
                st.video(selected_portrait.asset_path())
                st.caption(f"{selected_portrait.name}（闭口视频形象）")
            else:
                st.image(selected_portrait.asset_path(), width=120, caption=selected_portrait.name)


def _render_workflow_options():
    from pixelle_video.services.digital_human_service import list_digital_human_workflows

    workflows = list_digital_human_workflows()
    if not workflows:
        st.warning("未找到数字人工作流，请检查 workflows/runninghub 或 workflows/selfhost。")
        return

    workflow_keys = [wf["key"] for wf in workflows]
    current_workflow = st.session_state.get(
        "ipb_m4_workflow",
        "workflows/runninghub/digital_combination.json",
    )
    default_idx = workflow_keys.index(current_workflow) if current_workflow in workflow_keys else 0

    selected_key = st.selectbox(
        "数字人工作流",
        options=workflow_keys,
        index=default_idx,
        format_func=lambda key: next(
            (wf["display_name"] for wf in workflows if wf["key"] == key),
            key,
        ),
        key="ipb_m4_workflow_select",
    )
    st.session_state.ipb_m4_workflow = selected_key

    selected_workflow = next((wf for wf in workflows if wf["key"] == selected_key), {})
    if selected_workflow.get("description"):
        st.caption(selected_workflow["description"])

    if selected_workflow.get("supports_duration") or selected_workflow.get("supports_prompt"):
        with st.expander("工作流参数", expanded=True):
            if selected_workflow.get("supports_duration"):
                default_duration = _probe_duration_safe(
                    st.session_state.get("ipb_m3_audio_path", "")
                )
                current_duration = float(st.session_state.get("ipb_m4_duration", 0.0) or 0.0)
                if current_duration <= 0 and default_duration:
                    current_duration = round(default_duration, 1)
                st.number_input(
                    "生成时长（秒）",
                    min_value=0.1,
                    max_value=300.0,
                    step=0.1,
                    value=current_duration or 5.0,
                    key="ipb_m4_duration",
                    help="默认按语音时长填写，可手动调整。",
                )
            if selected_workflow.get("supports_prompt"):
                st.text_area(
                    "提示词描述",
                    key="ipb_m4_prompt",
                    height=90,
                    placeholder="例如：自然口播，正面镜头，表情稳定，唇形同步",
                )


def _probe_duration_safe(media_path: str) -> float:
    if not media_path or not os.path.exists(media_path):
        return 0.0
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                media_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _do_generate_video(pixelle_video):
    """Execute digital human video generation and persist result."""
    audio_path = st.session_state.get("ipb_m3_audio_path", "").strip()
    if not audio_path or not os.path.exists(audio_path):
        st.warning("语音文件不存在，请重新生成语音（模块3）。")
        return

    portrait_id = st.session_state.get("ipb_m4_portrait_id", "").strip()
    if not portrait_id:
        st.warning("请先选择一个数字人形象。")
        return

    portrait_svc = _get_portrait_svc(pixelle_video)
    portrait_path = portrait_svc.get_portrait_path(portrait_id)
    if not portrait_path or not os.path.exists(portrait_path):
        st.error("所选形象文件不存在，请重新上传。")
        return

    output_path = get_temp_path(f"ipb_dh_{uuid.uuid4().hex[:8]}.mp4")

    set_step_status(4, "running")
    show_global_loading("正在生成数字人视频，请稍候...")
    with st.spinner("正在生成数字人视频，请稍候…"):
        try:
            dh_video_path = run_async(
                _get_dh_svc(pixelle_video).generate(
                    portrait_path=portrait_path,
                    audio_path=audio_path,
                    output_path=output_path,
                    workflow=st.session_state.get("ipb_m4_workflow"),
                    duration=float(st.session_state.get("ipb_m4_duration", 0.0) or 0.0),
                    prompt=st.session_state.get("ipb_m4_prompt", ""),
                )
            )
            st.session_state.ipb_m4_dh_video_path = dh_video_path
            set_step_status(4, "done")
            set_step_notice(4, "success", "数字人视频生成成功")
            safe_rerun()
        except Exception as e:
            set_step_status(4, "error")
            set_step_notice(4, "error", str(e))
            st.error(str(e))
            logger.exception(e)


async def run_m4(pixelle_video) -> bool:
    """Auto-run entry for pipeline mode. Returns True on success."""
    audio_path = st.session_state.get("ipb_m3_audio_path", "").strip()
    if not audio_path or not os.path.exists(audio_path):
        logger.warning("run_m4: ipb_m3_audio_path is empty or missing, skipping")
        return False

    portrait_id = st.session_state.get("ipb_m4_portrait_id", "").strip()
    if not portrait_id:
        logger.warning("run_m4: no portrait selected, skipping")
        return False

    portrait_path = _get_portrait_svc(pixelle_video).get_portrait_path(portrait_id)
    if not portrait_path or not os.path.exists(portrait_path):
        logger.warning(f"run_m4: portrait file not found for id={portrait_id}")
        return False

    output_path = get_temp_path(f"ipb_dh_{uuid.uuid4().hex[:8]}.mp4")

    try:
        dh_video_path = await _get_dh_svc(pixelle_video).generate(
            portrait_path=portrait_path,
            audio_path=audio_path,
            output_path=output_path,
            workflow=st.session_state.get("ipb_m4_workflow"),
            duration=float(st.session_state.get("ipb_m4_duration", 0.0) or 0.0),
            prompt=st.session_state.get("ipb_m4_prompt", ""),
        )
        st.session_state.ipb_m4_dh_video_path = dh_video_path
        set_step_status(4, "done")
        logger.info(f"run_m4 completed: {dh_video_path}")
        return True
    except Exception as e:
        set_step_status(4, "error")
        logger.exception(e)
        return False
