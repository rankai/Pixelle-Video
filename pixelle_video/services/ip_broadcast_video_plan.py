"""Video plan recommendations for IP broadcast workflows."""

from __future__ import annotations

from typing import Any

_GOAL_RULES = {
    "团购转化": {
        "default_strategy": "团购视频优先展示优惠、套餐和到店场景。",
        "digital_label": "老板出镜",
        "uploaded_label": "建议插入菜品/套餐视频",
        "uploaded_prompt": "菜品、套餐、门店环境或顾客到店画面",
        "keyword_sets": [
            (["套餐", "优惠", "价格", "菜品", "牛肉", "锅底", "新品"], ["菜品", "套餐", "产品"]),
            (["到店", "聚餐", "门店", "环境", "下班", "附近"], ["门店", "环境", "聚餐"]),
        ],
    },
    "门店探店": {
        "default_strategy": "探店视频优先展示门头、环境、产品和体验细节。",
        "digital_label": "老板出镜",
        "uploaded_label": "建议插入门店/体验视频",
        "uploaded_prompt": "门店门头、环境、服务、体验或产品细节画面",
        "keyword_sets": [
            (["门店", "环境", "位置", "门头", "空间"], ["门店", "环境", "门头"]),
            (["体验", "服务", "菜品", "项目", "细节"], ["体验", "服务", "产品"]),
        ],
    },
    "新品推荐": {
        "default_strategy": "新品视频优先展示新品特写、制作过程和使用场景。",
        "digital_label": "老板出镜",
        "uploaded_label": "建议插入新品/产品视频",
        "uploaded_prompt": "新品特写、制作过程、使用场景或顾客体验画面",
        "keyword_sets": [
            (["新品", "新款", "上新", "亮点", "产品"], ["新品", "产品", "特写"]),
            (["使用", "场景", "体验", "尝鲜"], ["使用场景", "体验"]),
        ],
    },
    "老板人设": {
        "default_strategy": "人设视频默认老板出镜，中段可插入案例或门店素材。",
        "digital_label": "老板出镜",
        "uploaded_label": "建议插入案例/门店视频",
        "uploaded_prompt": "案例过程、门店现场、产品细节或客户反馈画面",
        "keyword_sets": [
            (["案例", "客户", "门店", "产品", "过程"], ["案例", "门店", "产品"]),
        ],
    },
    "客户案例": {
        "default_strategy": "案例视频优先展示服务过程、前后变化和真实反馈。",
        "digital_label": "老板出镜",
        "uploaded_label": "建议插入客户/服务视频",
        "uploaded_prompt": "客户案例、服务过程、前后变化或真实反馈画面",
        "keyword_sets": [
            (["客户", "案例", "问题", "过程", "结果", "变化"], ["客户", "案例", "服务过程"]),
        ],
    },
}


def generate_video_plan(
    business_goal: str,
    script: str,
    visual_strategy: str = "",
    intent_note: str = "",
) -> dict[str, Any]:
    segments = _split_segments(script)
    if intent_note.strip() and not any(intent_note.strip() in text for _, _, text in segments):
        segments = [(segment_id, index, f"{text} {intent_note.strip()}") for segment_id, index, text in segments]
    if not segments:
        return {
            "goal": business_goal,
            "status": "empty",
            "summary": "暂无可规划文案",
            "visual_strategy": visual_strategy,
            "segments": [],
        }

    rule = _GOAL_RULES.get(business_goal)
    if not rule:
        plan_segments = [
            _build_plan_segment(segment_id, index, text, "digital_human", "老板出镜", [], "")
            for segment_id, index, text in segments
        ]
        return _build_plan(business_goal, visual_strategy, plan_segments)

    plan_segments = []
    for segment_id, index, text in segments:
        if index == 1:
            plan_segments.append(
                _build_plan_segment(
                    segment_id,
                    index,
                    text,
                    "digital_human",
                    str(rule["digital_label"]),
                    [],
                    "",
                )
            )
            continue

        asset_keywords = _match_asset_keywords(text, rule["keyword_sets"])
        if asset_keywords:
            plan_segments.append(
                _build_plan_segment(
                    segment_id,
                    index,
                    text,
                    "uploaded_video",
                    str(rule["uploaded_label"]),
                    asset_keywords,
                    str(rule["uploaded_prompt"]),
                )
            )
        else:
            plan_segments.append(
                _build_plan_segment(
                    segment_id,
                    index,
                    text,
                    "digital_human",
                    str(rule["digital_label"]),
                    [],
                    "",
                )
            )

    return _build_plan(
        business_goal,
        visual_strategy or str(rule["default_strategy"]),
        plan_segments,
    )


def apply_video_plan_to_visual_groups(plan: dict[str, Any]) -> list[dict[str, Any]]:
    groups = []
    for item in plan.get("segments", []):
        if not isinstance(item, dict) or item.get("visual_type") != "uploaded_video":
            continue
        segment_id = str(item.get("segment_id") or "").strip()
        if not segment_id:
            continue
        groups.append(
            {
                "group_id": f"plan_group_{segment_id}",
                "segment_ids": [segment_id],
                "visual_type": "uploaded_video",
                "prompt": str(item.get("prompt") or ""),
                "uploaded_video_path": "",
                "video_asset_id": "",
                "status": "recommended",
                "asset_keywords": [str(keyword) for keyword in item.get("asset_keywords", [])],
            }
        )
    return groups


def _split_segments(script: str) -> list[tuple[str, int, str]]:
    items = [line.strip() for line in script.splitlines() if line.strip()]
    if not items and script.strip():
        items = [script.strip()]
    return [(str(index), index, text) for index, text in enumerate(items, start=1)]


def _match_asset_keywords(
    text: str,
    keyword_sets: list[tuple[list[str], list[str]]],
) -> list[str]:
    for triggers, asset_keywords in keyword_sets:
        if any(trigger in text for trigger in triggers):
            return asset_keywords
    return []


def _build_plan_segment(
    segment_id: str,
    index: int,
    text: str,
    visual_type: str,
    label: str,
    asset_keywords: list[str],
    prompt: str,
) -> dict[str, Any]:
    return {
        "segment_id": segment_id,
        "index": index,
        "text": text,
        "visual_type": visual_type,
        "label": label,
        "asset_keywords": asset_keywords,
        "prompt": prompt,
        "reason": _segment_reason(visual_type, label),
    }


def _build_plan(
    business_goal: str,
    visual_strategy: str,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    digital_count = sum(1 for item in segments if item.get("visual_type") == "digital_human")
    uploaded_count = sum(1 for item in segments if item.get("visual_type") == "uploaded_video")
    summary_parts = []
    if digital_count:
        summary_parts.append(f"老板出镜 {digital_count} 段")
    if uploaded_count:
        summary_parts.append(f"插入门店视频 {uploaded_count} 段")
    return {
        "goal": business_goal,
        "status": "ready",
        "summary": " · ".join(summary_parts) or "默认全程老板出镜",
        "visual_strategy": visual_strategy,
        "segments": segments,
    }


def _segment_reason(visual_type: str, label: str) -> str:
    if visual_type == "uploaded_video":
        return f"{label}能让门店内容更直观。"
    return "老板本人出镜更适合建立信任。"
