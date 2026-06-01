"""Unified execution layer for IP broadcast steps."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import streamlit as st
from loguru import logger

from web.ip_broadcast.state import (
    get_next_action,
    refresh_step_readiness,
    set_step_status,
)
from web.ip_broadcast.status_ui import set_step_notice
from web.utils.async_helpers import run_async


@dataclass(frozen=True)
class StepRunner:
    step: int
    label: str
    runner: Callable[[Any], Any]


def _get_step_runner(step_key: str) -> StepRunner | None:
    if step_key == "rewrite":
        from web.ip_broadcast.modules.m2_copywriting import run_m2

        return StepRunner(2, "文案确认", run_m2)
    if step_key == "voice":
        from web.ip_broadcast.modules.m3_voice import run_m3

        return StepRunner(3, "声音生成", run_m3)
    if step_key == "digital_human":
        from web.ip_broadcast.modules.m4_digital_human import run_m4

        return StepRunner(4, "数字人视频", run_m4)
    if step_key == "postproduce":
        from web.ip_broadcast.modules.m5_postproduction import run_m5

        return StepRunner(5, "一键成片", run_m5)
    if step_key == "publish":
        from web.ip_broadcast.modules.m7_publish import run_m7

        return StepRunner(6, "视频发布", run_m7)
    return None


def run_ipb_step(step_key: str, pixelle_video, placeholder=None) -> bool:
    """Run one step through shared dependency checks, status, and error handling."""
    spec = _get_step_runner(step_key)
    if spec is None:
        if placeholder:
            placeholder.info("当前步骤无需自动执行")
        return False

    action = get_next_action()
    if action.key != step_key:
        set_step_notice(spec.step, "warning", action.description)
        if placeholder:
            placeholder.warning(action.description)
        return False

    set_step_status(spec.step, "running")
    if placeholder:
        placeholder.info(f"正在执行：{spec.label}（步骤 {spec.step}/6）...")

    try:
        ok = bool(run_async(spec.runner(pixelle_video)))
        if ok:
            set_step_status(spec.step, "done")
            set_step_notice(spec.step, "success", f"{spec.label}完成")
            refresh_step_readiness()
            return True

        set_step_status(spec.step, "error")
        set_step_notice(spec.step, "error", f"{spec.label}执行失败")
        if placeholder:
            placeholder.error(f"步骤 {spec.step}（{spec.label}）执行失败，流程中止。")
        return False
    except Exception as e:
        set_step_status(spec.step, "error")
        set_step_notice(spec.step, "error", str(e))
        if placeholder:
            placeholder.error(f"步骤 {spec.step}（{spec.label}）出错：{e}")
        logger.exception(e)
        return False


def run_from_current_state(pixelle_video, placeholder=None) -> None:
    """Continue from the current ready step until user input is required."""
    status_placeholder = placeholder or st.empty()
    while True:
        action = get_next_action()
        if action.key in {"prepare_source", "select_portrait", "publish"}:
            status_placeholder.info(action.description)
            return
        if not run_ipb_step(action.key, pixelle_video, status_placeholder):
            return
