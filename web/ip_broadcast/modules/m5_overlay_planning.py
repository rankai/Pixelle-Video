from typing import Any

import streamlit as st

from web.ip_broadcast.modules.m5_video_assets import (
    render_group_video_asset_selector,
)
from web.ip_broadcast.state import (
    create_overlay_group,
    remove_overlay_group,
    sync_story_segments_from_script,
)
from web.utils.streamlit_helpers import safe_rerun


def render_overlay_planning() -> None:
    st.markdown("**画面规划（可选）**")
    script = st.session_state.get("ipb_final_script", "")
    if script and not st.session_state.get("ipb_story_segments"):
        sync_story_segments_from_script(script)

    segments = st.session_state.get("ipb_story_segments", [])
    groups = st.session_state.get("ipb_visual_groups", [])
    st.caption(
        f"已识别 {len(segments)} 个文案段落。默认全程数字人；开启后只在第 5 步覆盖画面，不会重复生成语音或数字人。"
    )

    enabled = st.toggle(
        "添加覆盖画面",
        key="ipb_overlay_enabled",
        help="用于在指定文案段落对应的时间范围内叠加上传视频或 AI 视频。",
    )
    st.session_state.ipb_storyboard_enabled = enabled

    if st.button("按当前文案更新段落", key="ipb_overlay_refresh_btn", use_container_width=True):
        sync_story_segments_from_script(script)
        st.success("画面规划段落已更新")
        safe_rerun()

    if not segments:
        st.caption("在第 2 步文案中用回车分段后，这里会显示可规划的段落。")
        return

    if not enabled:
        return

    st.markdown("**勾选连续段落创建覆盖组**")
    selected_segment_ids = render_overlay_segment_picker(segments, groups)
    if st.button("创建覆盖组", key="ipb_overlay_create_group_btn", use_container_width=True):
        try:
            create_overlay_group(selected_segment_ids)
            clear_overlay_segment_picker(segments)
            st.success("覆盖组已创建")
            safe_rerun()
        except Exception as e:
            st.error(str(e))

    visible_groups = visible_overlay_groups(groups)
    with st.expander("编辑覆盖组", expanded=bool(visible_groups)):
        if not visible_groups:
            st.caption("勾选一个或多个连续段落后创建覆盖组，再在这里配置覆盖视频。")
            return

        for group in visible_groups:
            _render_overlay_group_editor(group, segments)


def _render_overlay_group_editor(group: dict[str, Any], segments: list[dict[str, Any]]) -> None:
    group_segments = [
        segment for segment in segments
        if segment["segment_id"] in group.get("segment_ids", [])
    ]
    label = "、".join(f"第{segment['index']}段" for segment in group_segments)
    with st.container(border=True):
        title_col, action_col = st.columns([3, 1])
        with title_col:
            st.markdown(f"**覆盖组 {group['group_id']}：{label}**")
        with action_col:
            if st.button(
                "取消覆盖组",
                key=f"ipb_overlay_remove_{group['group_id']}",
                use_container_width=True,
            ):
                remove_overlay_group(group["group_id"])
                safe_rerun()
        for segment in group_segments:
            st.caption(f"{segment['index']}. {segment['text'][:80]}")
        overlay_type = normalize_overlay_type(group)
        overlay_type = st.radio(
            "覆盖类型",
            options=["none", "uploaded_video", "ai_video"],
            format_func=lambda value: {
                "none": "不覆盖，保留数字人",
                "uploaded_video": "上传视频覆盖",
                "ai_video": "AI 视频覆盖",
            }[value],
            horizontal=True,
            index=["none", "uploaded_video", "ai_video"].index(overlay_type),
            key=f"ipb_overlay_type_{group['group_id']}",
        )
        group["overlay_type"] = overlay_type
        group["visual_type"] = {
            "none": "digital_human",
            "uploaded_video": "uploaded_video",
            "ai_video": "ai_video",
        }[overlay_type]
        if overlay_type == "none":
            return

        group["overlay_mode"] = st.radio(
            "覆盖方式",
            options=["fullscreen", "pip"],
            format_func=lambda value: "全屏覆盖" if value == "fullscreen" else "画中画",
            horizontal=True,
            index=["fullscreen", "pip"].index(group.get("overlay_mode", "fullscreen")),
            key=f"ipb_overlay_mode_{group['group_id']}",
        )
        if overlay_type == "uploaded_video":
            render_group_video_asset_selector(group)
        elif overlay_type == "ai_video":
            group["prompt"] = st.text_area(
                "AI 视频提示词",
                value=group.get("prompt") or "商务口播相关真实场景，镜头稳定",
                height=80,
                key=f"ipb_overlay_prompt_{group['group_id']}",
            )


def render_overlay_segment_picker(
    segments: list[dict[str, Any]],
    groups: list[dict[str, Any]],
) -> list[str]:
    group_by_segment = {
        segment_id: group
        for group in groups
        for segment_id in group.get("segment_ids", [])
    }
    selected_segment_ids = []
    with st.container(border=True):
        for segment in segments:
            segment_id = segment["segment_id"]
            current_group = group_by_segment.get(segment_id, {})
            group_label = ""
            if current_group.get("is_overlay_group") or normalize_overlay_type(current_group) != "none":
                group_label = f" · 已在 {current_group.get('group_id', '覆盖组')}"
            picked = st.checkbox(
                f"第{segment['index']}段{group_label}",
                key=overlay_pick_key(segment_id),
            )
            st.caption(segment.get("text", "")[:96])
            if picked:
                selected_segment_ids.append(segment_id)
    st.caption("提示：一次只能创建连续段落的覆盖组。未加入覆盖组的段落默认保留数字人画面。")
    return selected_segment_ids


def clear_overlay_segment_picker(segments: list[dict[str, Any]]) -> None:
    st.session_state["ipb_overlay_picker_nonce"] = int(
        st.session_state.get("ipb_overlay_picker_nonce", 0)
    ) + 1


def overlay_pick_key(segment_id: str) -> str:
    nonce = int(st.session_state.get("ipb_overlay_picker_nonce", 0))
    return f"ipb_overlay_pick_{nonce}_{segment_id}"


def visible_overlay_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        group for group in groups
        if group.get("is_overlay_group")
        or normalize_overlay_type(group) != "none"
        or len(group.get("segment_ids", [])) > 1
    ]


def normalize_overlay_type(group: dict[str, Any]) -> str:
    overlay_type = group.get("overlay_type")
    if overlay_type in {"none", "uploaded_video", "ai_video"}:
        return overlay_type
    visual_type = group.get("visual_type")
    if visual_type in {"uploaded_video", "ai_video"}:
        return visual_type
    return "none"


def estimate_overlay_timeline(
    segments: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    audio_duration: float,
) -> list[dict[str, Any]]:
    if not segments or audio_duration <= 0:
        return []

    char_counts = [max(len(segment.get("text", "")), 1) for segment in segments]
    total_chars = sum(char_counts) or 1
    segment_ranges: dict[str, tuple[float, float]] = {}
    current = 0.0
    for segment, chars in zip(segments, char_counts):
        start = current
        current += audio_duration * (chars / total_chars)
        segment_ranges[segment["segment_id"]] = (start, current)

    timeline = []
    for group in groups:
        overlay_type = normalize_overlay_type(group)
        if overlay_type == "none":
            continue
        ranges = [
            segment_ranges[segment_id]
            for segment_id in group.get("segment_ids", [])
            if segment_id in segment_ranges
        ]
        if not ranges:
            continue
        start_time = min(item[0] for item in ranges)
        end_time = max(item[1] for item in ranges)
        item = {
            "group_id": group["group_id"],
            "start_time": round(start_time, 2),
            "end_time": round(end_time, 2),
            "duration": round(end_time - start_time, 2),
            "overlay_type": overlay_type,
            "overlay_mode": group.get("overlay_mode", "fullscreen"),
        }
        group["start_time"] = item["start_time"]
        group["end_time"] = item["end_time"]
        timeline.append(item)
    return timeline
