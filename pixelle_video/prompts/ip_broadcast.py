"""LLM prompt builders for the IP broadcast module"""


# ── 提取脚本 ─────────────────────────────────────────────────────────────────

def build_script_extraction_prompt(raw_text: str) -> str:
    return f"""请从以下内容中提取干净的口播脚本。去除无关信息（时间戳、弹幕、评论等），只保留核心口播内容，保持原有逻辑和语气。

原始内容：
{raw_text}

直接输出提取后的脚本，不要有前缀说明。"""


# ── IP大脑（生成式，基于结构化表单变量） ────────────────────────────────────

def build_ip_brain_generation_prompt(
    video_type: str,
    copy_type: str,
    industry_persona: str,
    selling_points: str,
    other_reqs: str,
    business_goal: str = "",
    script_structure: list[str] | None = None,
    target_word_count: int | None = None,
    style_prompt: str = "",
    intent_note: str = "",
) -> str:
    """根据用户填写的表单变量，注入到统一提示词模板，直接生成IP口播文案。"""

    # 可选字段拼接（空则不展示该行）
    persona_line = f"\n- 行业与人设：{industry_persona.strip()}" if industry_persona.strip() else ""
    selling_line = f"\n- 卖点与价格：{selling_points.strip()}" if selling_points.strip() else ""
    reqs_line = f"\n- 其他要求：{other_reqs.strip()}" if other_reqs.strip() else ""
    goal_line = f"\n- 本条视频目标：{business_goal.strip()}" if business_goal.strip() else ""
    intent_line = f"\n- 想特别强调的内容：{intent_note.strip()}" if intent_note.strip() else ""
    style_line = f"\n- 写作风格：{style_prompt.strip()}" if style_prompt.strip() else ""
    structure_line = _format_script_structure(script_structure)
    word_count = target_word_count or 200
    legacy_type_lines = ""
    if not business_goal.strip():
        legacy_type_lines = f"\n- 视频类型：{video_type}\n- 文案风格：{copy_type}"

    return f"""你是一位专业的短视频口播文案策划，擅长为不同领域的博主打造有辨识度的IP文案。

请根据以下配置，直接生成一篇完整的口播文案，目标字数约{word_count}字，语言自然流畅，适合真人出镜朗读。

【配置信息】{legacy_type_lines}{goal_line}{persona_line}{selling_line}{intent_line}{style_line}{reqs_line}{structure_line}

【文案要求】
- 开头要有强钩子，吸引用户停留
- 中间围绕卖点或人设价值展开，逻辑清晰
- 结尾有明确的行动号召（点赞/关注/私信/购买等）
- 语气要符合本条视频目标和写作风格
- 如配置了推荐结构，按该结构展开，但不要添加小标题、编号或分段标题
- 按自然语义分成3-5个短段落，每段单独换行，方便后续画面规划
- 直接输出文案正文，不要有前缀说明或标题"""


# ── 热点选题（从他人爆款文案中学习，生成选题） ──────────────────────────────

def build_hot_topics_from_viral_prompt(viral_content: str) -> str:
    """从粘贴的爆款文案中学习风格，生成10个同类热点选题。"""
    return f"""你是一位专业的短视频选题策划。请认真阅读以下爆款视频文案，分析其选题方向、内容结构和受众关注点，然后生成10个同类型的热点选题。

【爆款文案参考】
{viral_content}

【选题要求】
- 选题要继承爆款文案的内容方向和受众定位
- 每个选题具体、有话题性，能引发互动或共鸣
- 选题角度多样，覆盖不同切入点（痛点、干货、故事、情绪等）
- 选题字数15字以内，简洁有力

请以JSON格式返回，包含字段：
- topics: 选题列表（10个字符串）

只返回JSON，不要有其他文字。"""


def build_script_from_topic_prompt(topic: str, viral_style_hint: str) -> str:
    """根据选中的选题和爆款风格摘要，生成一篇口播文案。"""
    style_section = f"\n\n【参考风格】\n{viral_style_hint.strip()}" if viral_style_hint.strip() else ""

    return f"""你是一位专业的短视频口播文案撰写人。请根据以下选题，撰写一篇完整的口播文案。{style_section}

【选题】
{topic}

【文案要求】
- 字数200-400字，适合真人出镜朗读
- 开头有强吸引力钩子
- 内容围绕选题展开，逻辑清晰
- 结尾有行动号召
- 直接输出文案正文，不要有前缀说明"""


# ── 改写文案（模块2使用） ────────────────────────────────────────────────────

def build_rewrite_prompt(
    source_text: str,
    style_prompt: str,
    word_count: int,
    business_goal: str = "",
    script_structure: list[str] | None = None,
    intent_note: str = "",
) -> str:
    goal_section = f"\n本条视频目标：{business_goal.strip()}\n" if business_goal.strip() else "\n"
    intent_section = (
        f"想特别强调的内容：{intent_note.strip()}\n" if intent_note.strip() else ""
    )
    structure_section = _format_script_structure(script_structure)
    return f"""你是一位专业的本地生活短视频文案改写专家，擅长把门店老板、主理人或一线经营者的表达改写成自然可信的口播。

请按照要求改写以下文案，让它像老板本人在镜头前和顾客说话，而不是广告播音稿。

原始文案：
{source_text}

{goal_section}{intent_section}
改写要求：
{style_prompt}{structure_section}

目标字数：约{word_count}字

要求：
- 保留核心信息和卖点
- 语言通顺自然，适合本地生活门店老板口播
- 控制在目标字数范围内
- 如配置了推荐结构，按该结构优化内容顺序，但不要添加小标题、编号或分段标题
- 按自然语义分成3-6个短段落，每段单独换行，方便后续画面规划
- 如果原始文案已经分段，改写后必须保留相近的段落数量和换行结构
- 不要夸大效果，不要使用绝对化承诺，不要编造门店没有提供的信息
- 结尾要给出清楚但不生硬的行动指引，例如到店、私信、团购、收藏或评论咨询
- 直接输出改写后的文案，不要有前缀说明"""


def _format_script_structure(script_structure: list[str] | None) -> str:
    if not script_structure:
        return ""
    structure = " → ".join(item.strip() for item in script_structure if item and item.strip())
    if not structure:
        return ""
    return f"\n- 推荐结构：{structure}"


# ── 社交媒体元数据（模块6使用） ──────────────────────────────────────────────

def build_social_meta_prompt(copy_text: str, platform: str = "通用") -> str:
    return f"""你是一位专业的短视频运营专家。根据以下口播文案，生成适合{platform}平台的标题、描述和话题标签。

文案内容：
{copy_text}

请以JSON格式返回，包含字段：
- title: 视频标题（15-20字，吸引点击）
- description: 视频描述（50-100字，包含关键词）
- hashtags: 话题标签列表（5-8个，不含#号）

只返回JSON，不要有其他文字。"""
