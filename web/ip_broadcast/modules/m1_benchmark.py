"""模块1：素材来源 — 生成可直接进入后续流程的口播文案草稿。"""

import streamlit as st
from loguru import logger

from pixelle_video.models.ip_broadcast import HotTopicsResult
from pixelle_video.prompts.ip_broadcast import (
    build_hot_topics_from_viral_prompt,
    build_ip_brain_generation_prompt,
    build_script_extraction_prompt,
    build_script_from_topic_prompt,
)
from pixelle_video.services.ip_learning import (
    IPVideoScriptResult,
    ProfileFetchBlocked,
    extract_many_video_scripts,
    fetch_latest_video_urls_from_profile,
    parse_manual_video_inputs,
)
from web.ip_broadcast.state import STATUS_ICONS, get_step_status, set_source_text, set_step_status
from web.ip_broadcast.status_ui import render_step_notice, set_step_notice, show_global_loading
from web.utils.async_helpers import run_async

# ── 素材来源选项 ────────────────────────────────────────────────────────────
SOURCE_MODES = ["视频链接", "粘贴脚本", "行业+人设", "IP学习"]
_VIDEO_TYPES = ["口播文案", "种草带货", "干货教程", "故事分享", "情绪表达", "品牌推广"]
_COPY_TYPES = ["人设型", "干货型", "情绪共鸣型", "痛点解决型", "促销转化型"]


def render_m1_benchmark(pixelle_video, run_mode: str):
    step_icon = STATUS_ICONS.get(get_step_status(1), "⬜")

    with st.container(border=True):
        st.markdown(f"**{step_icon} 1. 素材来源**")
        source_mode = st.radio(
            "选择来源",
            SOURCE_MODES,
            horizontal=True,
            key="ipb_source_mode",
        )

        if source_mode == "视频链接":
            _render_url_source(pixelle_video)
        elif source_mode == "粘贴脚本":
            _render_paste_source(pixelle_video)
        elif source_mode == "行业+人设":
            _render_tab_brain(pixelle_video)
        else:
            _render_ip_learning(pixelle_video)
        render_step_notice(1)


# ── Tab 1：提取脚本 ──────────────────────────────────────────────────────────

def _render_url_source(pixelle_video):
    url_input = st.text_input(
        "视频链接或抖音分享文本",
        key="ipb_m1_url_input",
        placeholder="可粘贴 https://v.douyin.com/...，也可粘贴“复制打开抖音...”分享文本",
    )
    st.caption("含真实短链会直接解析；仅含口令码时会尝试口令解析服务。")
    if st.button(
        "提取并生成文案",
        key="ipb_m1_url_extract_btn",
        use_container_width=True,
        type="primary",
    ):
        _extract_from_url(pixelle_video, url_input)


def _render_paste_source(pixelle_video):
    raw_paste = st.text_area(
        "粘贴脚本文字",
        height=160,
        key="ipb_m1_paste_input",
        placeholder="将视频口播文案粘贴到此处...",
    )
    if st.button(
        "清洗并生成文案",
        key="ipb_m1_extract_btn",
        use_container_width=True,
        type="primary",
    ):
        raw_text = raw_paste.strip()
        if not raw_text:
            st.warning("请先粘贴脚本内容")
        else:
            _clean_and_set_source(pixelle_video, raw_text, "粘贴脚本")


# ── Tab 2：行业+人设 ─────────────────────────────────────────────────────────

def _render_tab_brain(pixelle_video):
    """基于结构化表单变量直接生成IP口播文案。完全独立，不依赖其他来源。"""
    st.caption("填写行业、人设和卖点，一键生成专属口播文案")

    col1, col2 = st.columns(2)
    with col1:
        video_type = st.selectbox(
            "视频类型",
            options=_VIDEO_TYPES,
            key="ipb_brain_video_type",
        )
    with col2:
        copy_type = st.selectbox(
            "文案类型",
            options=_COPY_TYPES,
            key="ipb_brain_copy_type",
        )

    industry_persona = st.text_area(
        "行业 + 人设（可选）",
        height=80,
        key="ipb_brain_industry_persona",
        placeholder="例如：餐饮店，我叫斌哥，在固安，有十年餐饮经验",
    )

    selling_points = st.text_area(
        "卖点 + 价格（可选）",
        height=80,
        key="ipb_brain_selling_points",
        placeholder="例如：纸张柔软亲肤，正常价99，今天只要59",
    )

    other_reqs = st.text_area(
        "其他要求（可选）",
        height=80,
        key="ipb_brain_other_reqs",
        placeholder="例如：适合30-50岁人群，节奏轻快",
    )

    if st.button("生成口播文案", key="ipb_brain_generate_btn", use_container_width=True, type="primary"):
        try:
            show_global_loading("正在生成行业人设口播文案，请稍候...")
            with st.spinner("生成中..."):
                result = run_async(
                    pixelle_video.llm(
                        prompt=build_ip_brain_generation_prompt(
                            video_type=video_type,
                            copy_type=copy_type,
                            industry_persona=industry_persona,
                            selling_points=selling_points,
                            other_reqs=other_reqs,
                        )
                    )
                )
            st.session_state.ipb_brain_result = result
            set_source_text(result, "行业+人设")
            set_step_notice(1, "success", "IP文案生成完成")
        except Exception as e:
            set_step_notice(1, "error", str(e))
            st.error(str(e))
            logger.exception(e)

    if st.session_state.get("ipb_brain_result"):
        st.text_area(
            "生成的IP文案",
            value=st.session_state.ipb_brain_result,
            height=200,
            key="ipb_brain_result_display",
            disabled=True,
        )


# ── Tab 3：IP学习 ────────────────────────────────────────────────────────────

def _render_ip_learning(pixelle_video):
    """学习一个IP主页的近期口播内容，生成选题，再为选题生成文案。"""
    st.caption("输入一个IP主页，自动学习最近5条视频口播文案并生成选题")

    profile_url = st.text_area(
        "IP主页链接或主页分享文本",
        key="ipb_ip_profile_url",
        height=80,
        placeholder="例如：https://www.douyin.com/user/... 或复制来的主页分享文本",
    )
    st.caption("会尝试读取本机浏览器登录态；若仍遇到登录、验证码或扫码验证，请使用下方手动链接兜底。")

    if st.button("学习该IP最新视频并生成选题", key="ipb_ip_profile_learn_btn", use_container_width=True, type="primary"):
        st.session_state.ipb_ip_show_manual_fallback = False
        _learn_from_profile(pixelle_video, profile_url)

    fallback_expanded = bool(st.session_state.get("ipb_ip_show_manual_fallback", False))
    with st.expander("手动兜底：粘贴最近5条视频链接", expanded=fallback_expanded):
        manual_links = st.text_area(
            "视频链接或抖音分享文本",
            height=150,
            key="ipb_ip_manual_video_links",
            placeholder="每行一条视频链接，或每段粘贴一条完整抖音分享文本，最多处理5条",
        )
        if st.button("提取这些视频并生成选题", key="ipb_ip_manual_learn_btn", use_container_width=True):
            inputs = parse_manual_video_inputs(manual_links)
            if not inputs:
                st.warning("请先粘贴至少 1 条视频链接或分享文本")
            else:
                _learn_from_video_inputs(pixelle_video, inputs, "手动视频链接")

    _render_ip_learning_results(pixelle_video)


def _learn_from_profile(pixelle_video, profile_url: str):
    if not profile_url.strip():
        set_step_notice(1, "warning", "请先输入 IP 主页链接或主页分享文本")
        st.warning("请先输入 IP 主页链接或主页分享文本")
        return

    try:
        show_global_loading("正在抓取该IP最近5条视频并学习，请稍候...")
        with st.spinner("正在抓取该IP最近5条视频链接..."):
            urls = run_async(fetch_latest_video_urls_from_profile(profile_url, limit=5))
        if not urls:
            st.session_state.ipb_ip_show_manual_fallback = True
            set_step_notice(1, "warning", "未抓取到视频链接，请手动粘贴最近 5 条视频链接继续学习。")
            st.warning("未抓取到视频链接，请手动粘贴最近 5 条视频链接继续学习。")
            return
        st.session_state.ipb_ip_video_urls = urls
        _learn_from_video_inputs(pixelle_video, urls, "IP主页")
    except ProfileFetchBlocked as e:
        st.session_state.ipb_ip_show_manual_fallback = True
        set_step_notice(1, "warning", str(e))
        st.warning(str(e))
    except Exception as e:
        st.session_state.ipb_ip_show_manual_fallback = True
        set_step_notice(1, "error", f"主页抓取失败：{e}")
        st.error(f"主页抓取失败：{e}")
        logger.exception(e)


def _learn_from_video_inputs(pixelle_video, video_inputs: list[str], label: str):
    from pixelle_video.config import config_manager
    from pixelle_video.services.script_extractor import VideoScriptExtractor

    llm_cfg = config_manager.get_llm_config()
    extractor = VideoScriptExtractor(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
    )

    try:
        show_global_loading("正在提取视频口播并生成选题，请稍候...")
        with st.spinner("正在逐条提取口播文案..."):
            results = run_async(extract_many_video_scripts(extractor, video_inputs, limit=5))
        _store_ip_learning_results(results)

        scripts = [item.script for item in results if item.ok and item.script]
        if not scripts:
            set_step_notice(1, "warning", "未能从这些视频中提取到可用口播文案，请检查链接或手动粘贴脚本。")
            st.warning("未能从这些视频中提取到可用口播文案，请检查链接或手动粘贴脚本。")
            return

        with st.spinner("正在基于学习结果生成选题..."):
            result: HotTopicsResult = run_async(
                pixelle_video.llm(
                    prompt=build_hot_topics_from_viral_prompt("\n\n".join(scripts)),
                    response_type=HotTopicsResult,
                )
            )
        st.session_state.ipb_ip_learning_topics = result.topics
        st.session_state.ipb_ip_selected_topic = ""
        st.session_state.ipb_ip_topic_script = ""
        set_step_notice(1, "success", f"已学习 {len(scripts)} 条视频文案，生成 {len(result.topics)} 个选题")
    except Exception as e:
        set_step_notice(1, "error", f"{label}学习失败：{e}")
        st.error(f"{label}学习失败：{e}")
        logger.exception(e)


def _store_ip_learning_results(results: list[IPVideoScriptResult]):
    st.session_state.ipb_ip_learning_scripts = [
        {"source": item.source, "script": item.script} for item in results if item.ok
    ]
    st.session_state.ipb_ip_learning_errors = [
        {"source": item.source, "error": item.error} for item in results if not item.ok
    ]


def _render_ip_learning_results(pixelle_video):
    scripts: list[dict] = st.session_state.get("ipb_ip_learning_scripts", [])
    errors: list[dict] = st.session_state.get("ipb_ip_learning_errors", [])

    if scripts or errors:
        st.caption(_ip_learning_result_summary(scripts, errors))
        with st.expander("查看每条视频文案", expanded=False):
            for idx, item in enumerate(scripts, start=1):
                st.markdown(f"**视频 {idx}：已提取**")
                st.caption(item["source"])
                st.text_area(
                    f"口播文案 {idx}",
                    value=item["script"],
                    height=120,
                    key=f"ipb_ip_script_display_{idx}",
                    disabled=True,
                )
            for idx, item in enumerate(errors, start=1):
                st.warning(f"第 {idx} 条提取失败：{item['error']}")
                st.caption(item["source"])

    topics: list = st.session_state.get("ipb_ip_learning_topics", [])
    if topics:
        current = st.session_state.get("ipb_ip_selected_topic", "")
        default_idx = topics.index(current) if current in topics else 0
        selected = st.radio(
            "选择一个选题",
            options=topics,
            index=default_idx,
            key="ipb_ip_topic_radio",
        )
        st.session_state.ipb_ip_selected_topic = selected

        if st.button("为此选题生成文案", key="ipb_ip_script_btn", use_container_width=True):
            try:
                viral_hint = "\n\n".join(item["script"] for item in scripts)[:1200]
                show_global_loading("正在为选题生成口播文案，请稍候...")
                with st.spinner("生成文案..."):
                    script = run_async(
                        pixelle_video.llm(
                            prompt=build_script_from_topic_prompt(selected, viral_hint)
                        )
                )
                st.session_state.ipb_ip_topic_script = script
                set_source_text(script, "IP学习")
                set_step_notice(1, "success", "文案生成完成")
            except Exception as e:
                set_step_notice(1, "error", str(e))
                st.error(str(e))
                logger.exception(e)

    if st.session_state.get("ipb_ip_topic_script"):
        st.text_area(
            "选题对应的口播文案",
            value=st.session_state.ipb_ip_topic_script,
            height=180,
            key="ipb_ip_topic_script_display",
            disabled=True,
        )


def _ip_learning_result_summary(scripts: list[dict], errors: list[dict]) -> str:
    parts = [f"已提取 {len(scripts)} 条"]
    if errors:
        parts.append(f"失败 {len(errors)} 条")
    return "，".join(parts)


# ── 辅助函数 ─────────────────────────────────────────────────────────────────

def _extract_from_url(pixelle_video, url: str):
    """Extract script from a video URL using multi-strategy pipeline."""
    if not url.strip():
        set_step_notice(1, "warning", "请先输入视频链接或分享文本")
        st.warning("请先输入视频链接或分享文本")
        return

    from pixelle_video.config import config_manager
    from pixelle_video.services.script_extractor import VideoScriptExtractor

    llm_cfg = config_manager.get_llm_config()
    extractor = VideoScriptExtractor(
        api_key=llm_cfg["api_key"],
        base_url=llm_cfg["base_url"],
    )
    try:
        show_global_loading("正在从视频链接提取口播文案，请稍候...")
        with st.spinner("正在从视频URL提取文案（首次可能需要1-2分钟）..."):
            script = run_async(extractor.extract(url))
        script = script.strip()
        if not script:
            set_step_notice(1, "warning", "没有提取到口播文案，请检查链接或手动粘贴文案")
            st.warning("没有提取到口播文案，请检查链接或手动粘贴文案")
            return
        st.session_state.ipb_m1_raw_script = script
        set_source_text(script, "视频链接")
        set_step_notice(1, "success", f"文案提取成功（{len(script)} 字符）")
    except Exception as e:
        set_step_notice(1, "error", f"提取失败：{e}")
        st.error(f"提取失败：{e}")
        logger.exception(e)


def _clean_and_set_source(pixelle_video, raw_text: str, label: str):
    try:
        show_global_loading("正在清洗并生成口播文案，请稍候...")
        with st.spinner("正在清洗并生成口播文案..."):
            cleaned = run_async(pixelle_video.llm(prompt=build_script_extraction_prompt(raw_text)))
        st.session_state.ipb_m1_raw_script = cleaned
        set_source_text(cleaned, label)
        set_step_notice(1, "success", f"文案已准备好（{len(cleaned)} 字符）")
    except Exception as e:
        set_step_notice(1, "error", str(e))
        st.error(str(e))
        logger.exception(e)


async def run_m1(pixelle_video) -> bool:
    """Module 1 contains four independent interactive tools.
    Auto mode skips this step — users operate each tab manually."""
    set_step_status(1, "done")
    return True
