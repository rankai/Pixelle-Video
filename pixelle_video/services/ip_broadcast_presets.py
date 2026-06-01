"""Business presets for IP broadcast workflows."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class IpBroadcastPreset:
    preset_id: str
    display_name: str
    description: str
    script_structure: list[str]
    recommended_word_count: int
    default_style_prompt: str
    default_template_id: str
    default_subtitle_enabled: bool
    recommended_visual_strategy: str
    publish_platform_hints: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


_PRESETS = [
    IpBroadcastPreset(
        preset_id="boss_persona",
        display_name="老板人设口播",
        description="适合老板建立专业可信的人设，强调观点、经验和行动建议。",
        script_structure=["痛点开场", "观点输出", "案例解释", "行动建议"],
        recommended_word_count=220,
        default_style_prompt="老板本人第一视角，真诚、专业、有经验感，少说空话。",
        default_template_id="boss_clean",
        default_subtitle_enabled=True,
        recommended_visual_strategy="默认全程数字人，必要时用案例视频覆盖中段。",
        publish_platform_hints=["douyin", "shipinhao"],
    ),
    IpBroadcastPreset(
        preset_id="store_visit",
        display_name="门店探店",
        description="适合门店环境、服务体验和套餐卖点介绍。",
        script_structure=["场景引入", "核心卖点", "体验细节", "到店引导"],
        recommended_word_count=180,
        default_style_prompt="像朋友推荐门店，具体、可信、有画面感，少堆形容词。",
        default_template_id="boss_premium",
        default_subtitle_enabled=True,
        recommended_visual_strategy="开头数字人，中段用门店环境视频全屏覆盖。",
        publish_platform_hints=["douyin", "xiaohongshu"],
    ),
    IpBroadcastPreset(
        preset_id="new_product",
        display_name="新品推荐",
        description="适合新品上市、功能卖点和使用场景介绍。",
        script_structure=["新品亮点", "解决问题", "使用场景", "购买引导"],
        recommended_word_count=180,
        default_style_prompt="突出新品价值，语言直接，避免夸张承诺。",
        default_template_id="boss_authority",
        default_subtitle_enabled=True,
        recommended_visual_strategy="卖点段落用产品视频或图片视频覆盖。",
        publish_platform_hints=["douyin", "kuaishou"],
    ),
    IpBroadcastPreset(
        preset_id="group_buying",
        display_name="团购转化",
        description="适合短链路促销、到店套餐和限时活动。",
        script_structure=["优惠钩子", "套餐内容", "适合人群", "下单引导"],
        recommended_word_count=150,
        default_style_prompt="强转化、节奏快、信息清楚，突出真实优惠和行动指令。",
        default_template_id="boss_authority",
        default_subtitle_enabled=True,
        recommended_visual_strategy="套餐内容段用门店或产品视频覆盖。",
        publish_platform_hints=["douyin", "kuaishou"],
    ),
    IpBroadcastPreset(
        preset_id="customer_case",
        display_name="客户案例",
        description="适合服务成果、客户变化和可信背书。",
        script_structure=["客户背景", "遇到的问题", "解决过程", "结果变化"],
        recommended_word_count=220,
        default_style_prompt="讲真实案例，克制表达结果，强调过程和可信细节。",
        default_template_id="boss_clean",
        default_subtitle_enabled=True,
        recommended_visual_strategy="案例过程可使用用户上传素材覆盖。",
        publish_platform_hints=["xiaohongshu", "shipinhao"],
    ),
]


def list_ip_broadcast_presets() -> list[IpBroadcastPreset]:
    return list(_PRESETS)


def get_ip_broadcast_preset(preset_id: str | None) -> IpBroadcastPreset | None:
    for preset in _PRESETS:
        if preset.preset_id == preset_id:
            return preset
    return None
