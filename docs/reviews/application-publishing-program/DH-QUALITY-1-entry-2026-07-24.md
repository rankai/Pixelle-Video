# DH-QUALITY-1 文案、标题、封面与字幕 Entry（2026-07-24）

## 状态

`entry_in_progress`。本 Entry 只冻结质量契约、失败矩阵、证据模板和回滚边界，不进入业务实现。

## 前置条件

- `DH-DUAL-2 / PG-DH-C` 已以 `implementation_pass_with_boundary` 通过，P0/P1/实质性 P2 均为 0。
- `CR-DH-DUAL-MODE-001` 仍是唯一变更请求；不改变 `PROGRAM-ROLLOUT / PG-L` 的 Windows、产品签字和真实平台 rollback 外部边界。
- 既有 AC-5 真实 Provider retry 证据仅作为基线读取，不在本 Entry 重放、不追加 Provider 调用。

## Entry 目标与冻结内容

1. 文案来源分为自定义口播文案、canonical `copywriting_artifact`、canonical `generated_marketing_copy`、canonical `title_plus_copywriting` 四类；`goal/制作目标` 不再隐式充当最终脚本。旧草案名 `marketing_copy_artifact`/`selected_title_with_copy` 只能在边界层 alias 后归一化，不能进入服务端分支。
2. 新 Run 固定 payload 路径 `content_source.script | source_artifact.variants[selected_variant_index].full_text`、`delivery.publish_title`、`delivery.publish_description`、`delivery.cover_title`、`delivery.hashtags` 五个独立字段；创建后固定来源 ArtifactVersion/variant，源文案变化不得热更新运行。
3. 选定标题必须绑定同项目完整文案版本；title-only 新 Run 拒绝，旧 Run 仅允许恢复。
4. 封面标题推荐 12–18 字、硬上限 24 个显示字符、最多两行；不得截取脚本前 40 字或描述前 80 字作为 fallback；副标题可为空且最多 28 字。
5. 新 Run 默认 `readable_v2` 字幕：1080×1920、48px 粗体、最多两行、每行 12–16 字、3px 描边、半透明底、170–220px 下边距、Noto Sans CJK SC、FFmpeg/libass 烧录；旧 Run 无 preset 时保持旧语义。
6. 结果 Artifact 必须完整交付 `final_video`、`cover`、`publish_copy`、`spoken_script`；默认预览仅为 `final_video`，原始数字人片段只在诊断区；accept 不触发发布。

## 允许范围

- 新增/修订 DH-QUALITY-1 contract、fixture、失败矩阵、质量指标、视觉抽帧模板、Artifact 完整性断言和回滚说明。
- 读取既有文案 Artifact、后期合成、AC-5 Provider retry 和 DH-DUAL-2 结果契约，建立可追溯来源绑定。
- 增加 Entry contract 测试；仅验证契约与边界，不调用真实媒体链路。

## 禁止范围

- 不修改 `DigitalHumanApplicationView`、媒体 adapter、RunningHub workflow、字幕渲染器、封面渲染器或结果 UI。
- 不调用 LLM/TTS/RunningHub/FFmpeg，不生成真实视频或封面。
- 不执行浏览器、平台上传、第三方授权或最终发布；不改变默认 feature flags；不执行破坏性迁移。

## 失败矩阵

| 场景 | 预期 | 错误码 |
| --- | --- | --- |
| 自定义脚本被隐式改写 | 拒绝或保持原文 | `DH_QUALITY_CUSTOM_SCRIPT_MUTATION` |
| 上游文案缺失/未完成 | fail-closed | `DH_QUALITY_SOURCE_ARTIFACT_INVALID` |
| 只有标题无完整文案 | 拒绝新建 Run | `DH_QUALITY_TITLE_REQUIRES_COPY` |
| 标题与文案跨项目 | 拒绝新建 Run | `DH_QUALITY_SOURCE_BINDING_MISMATCH` |
| 封面标题超过 24 字 | 生成前阻断 | `DH_QUALITY_COVER_TITLE_TOO_LONG` |
| fallback 截取脚本/描述前缀 | 拒绝 fallback | `DH_QUALITY_COVER_FALLBACK_INVALID` |
| 新 Run 缺少字幕 preset | 固定为 `readable_v2` | `DH_QUALITY_SUBTITLE_PRESET_REQUIRED` |
| 旧 Run 被新样式静默重渲染 | 保留旧样式 | `DH_QUALITY_OLD_RUN_STYLE_MUTATION` |
| final video 缺流/无字幕 | accept 返回 409，保持 needs_review | `DH_QUALITY_FINAL_ARTIFACT_INCOMPLETE` |

## 质量证据模板（后续实现阶段使用）

- 真实字幕：ASS/SRT 非空、25%/50%/75% 抽帧可读、不越安全区、无缺字。
- 媒体：`final_video` 与 clean source SHA 不同，H.264/AAC，有视频/音频流，时长差不超过 `max(0.5 秒, 2%)`。
- 封面：短标题可读、最多两行、无脚本任意截断、模板安全区不溢出。
- Artifact：最终视频、封面、发布文案和 spoken script 均有稳定 ArtifactVersion/文件引用；原始片段不作为默认下载。
- 本 Entry 不采集真实媒体截图；真实 Provider/媒体证据后置 `DH-QUALITY-2`，且必须在 PG-DH-D 通过后按一次有目的的调用执行。

## 回滚与安全边界

- 关闭新增质量 flag 后保留旧图片模式、旧 `/ip`、V1 Run 和历史 Artifact。
- 不删除 Artifact、不改写旧 Run 字幕、不切换第二模型配置源。
- Provider、平台上传、最终发布点击和默认发布开关均保持 0/关闭。

## Entry Gate

`PG-DH-D` 需要 contract/fixture/test 通过、质量与失败矩阵冻结、回滚记录完整、独立六维复审 P0/P1=0；通过后才进入文案/字幕/封面实现批次。
