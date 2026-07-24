# DH-QUALITY-1 文案、标题、封面与字幕业务实现（2026-07-24）

## 状态

implementation_pass_with_boundary。本批完成质量业务实现、定向测试和桌面构建；未调用真实 Provider、浏览器、平台或最终发布，独立六维复审按用户要求延后到 Program 完成。

## 已实现

- digital_human_input 在 V2 边界接受并归一化 marketing_copy_artifact、selected_title_with_copy，canonical payload 只保留四种内容模式。
- 自定义口播要求 content_source.script，不再把 goal/制作目标隐式转换为新 V2 脚本；delivery 缺省固定 readable_v2/enabled。
- delivery.publish_title、publish_description、cover_title、hashtags 与 spoken_script 分离；标签去除 # 前缀并拒绝空项。
- 封面标题 24 字/两行/单行 12 字硬限制，副标题 28 字硬限制；readable_v2 不使用脚本或描述前缀作为封面 fallback。
- V2 session 固定来源 ArtifactVersion、variant、数字人 scene/revision、delivery 和 spoken_script；旧 V1 session 继续保留旧状态。
- readable_v2 后期字幕固定 48px、3px 描边、190px 下边距覆盖；旧运行没有 preset 时保持原模板语义。
- V2 生成结果注册 video、cover、publish_copy、spoken_script 四类 Artifact；V1/旧本地隔离路径仍使用三类兼容集合。
- 桌面端支持自定义口播、已有文案、自动生成文案 Artifact、选定标题+完整文案；选定标题新建必须补选同项目完整文案版本；发布字段和封面字段可编辑，结果默认仍为 final_video。

## 验证

- Python 质量实现与双模式回归：107 passed, 12 warnings（warnings 为既有 Pydantic deprecation）。
- 质量实现专测：11 passed，覆盖 alias、字段类型、goal 拒绝、封面限制、readable_v2 样式、四 Artifact accept。
- Desktop 定向 Vitest：19 passed。
- Desktop TypeScript/Vite build：通过。
- Ruff、format、JSON、git diff --check：通过。

## 边界

- 未执行真实 TTS、RunningHub、FFmpeg 真实媒体质量抽帧或平台动作；这些属于后续 DH-QUALITY-2/DH-DUAL-3 的 live/恢复证据。
- 最终发布按钮和自动点击保持关闭；accept 只完成人工接收，不触发任何平台发布。
- 本批没有重写旧 Run 的字幕或历史 Artifact。
