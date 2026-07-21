# ADR-012：发布执行器采用有状态、可恢复的阶段化模型

- 状态：`accepted for PUB-5 direction correction`
- 日期：2026-07-21
- 范围：`E2E-DOUYIN/PUB-5` 及后续快手、视频号、小红书平台适配
- 相关 ADR：`ADR-PublishRunStateMachine`、`ADR-PlatformAdapterEvidence`、`docs/adr/011-browser-runtime-strategy-ego-lite-evaluation.md`

## 结论

当前发布领域的 FastAPI、PublishPackage、PublishRun、账号/profile 锁和人工最终发布边界继续保留；需要纠偏的是平台浏览器执行器，不是后端语言。

从 `oil-oil/video-publisher-skill` 的实现与测试说明看，高成功率并非来自多加几个 selector，而来自以下组合：一个总协调器、每个平台一个持久任务空间、上传屏障、串行 UI mutation、每步 fresh verify、稳定 task-space 身份、指纹绑定 checkpoint/cover receipt、typed blocker，以及同一 job 的普通恢复。参考：[Skill 主流程](https://github.com/oil-oil/video-publisher-skill/blob/main/video-publisher/SKILL.md)、[平台公共契约](https://github.com/oil-oil/video-publisher-skill/blob/main/video-publisher/references/platform-common.md)、[Ego Lite 工作流](https://github.com/oil-oil/video-publisher-skill/blob/main/video-publisher/references/ego-browser-workflow.md)、[抖音适配契约](https://github.com/oil-oil/video-publisher-skill/blob/main/video-publisher/references/platform-douyin.md)。

## 当前路线的偏差

当前 PUB-5 实现已经有 PublishRun 和基础 checkpoint 字段，但真实执行仍主要是一次调用内的：打开页面 → 上传 → 等待 → 标题/描述/话题/封面连续 mutation → 等待人工。它与参考 skill 的关键差异如下：

| 能力 | 当前实现 | 参考 skill 要求 | 影响 |
| --- | --- | --- | --- |
| 页面/草稿身份 | Playwright profile + URL/DOM 判断 | 持久 task-space 的数字 ID 与稳定名称，重启后双重匹配 | 可能把旧草稿或回收 ID 当成目标草稿 |
| 上传语义 | `set_input_files` 后等待预览/输入框 | `already_ready` / `resume_existing` / `injected`，明确完成/处理中/失败 | 可能重复上传或把文件注入当成完成 |
| 阶段边界 | 单个 adapter 调用串完所有动作 | inspect 并行、上传屏障、UI queue 串行、最终并行 verify | 中途失败后无法精确恢复 |
| 话题 | 无专用控件时退回普通文本/回车 | 点击真实 `#添加话题`、选择真实 suggestion entity、按序前缀恢复 | 话题可能只是 `#文本` 残留，不是平台实体 |
| 封面 | 文件 input/预览 marker 即视为成功 | 主卡真实 URL、双 slot distinct、fingerprint-bound receipt、独立 verify | 封面 readback 失败或误判临时预览 |
| 恢复 | run 可回到 queued，但 adapter 从头执行 | checkpoint 与 fresh page truth 对账，失败只修缺失阶段 | 可能重复上传、覆盖或污染现有草稿 |
| 失败分类 | 部分错误被统一成 needs_attention | `FOREIGN_DRAFT`、`UPLOAD_STALLED`、`INPUT_CHANNEL_BROKEN` 等 typed blocker | 无法安全决定重试、暂停还是人工接管 |

## 决策

1. **不改为 Node.js/Express。** FastAPI 继续承担应用中心、AI/媒体执行、PublishRun 和本地桌面 sidecar；未来 SaaS 混合架构仍按 ADR-007 执行。
2. **不把外部 skill 整体复制成第二套事实源。** 该仓库声明 MIT，可在满足许可条件时参考或复用代码；但当前环境没有可审计的 `ego-browser` 生产依赖、task-space 数据迁移和桌面打包链路，直接复制会引入另一套状态/账号/证据事实源。
3. **把参考 skill 的协议落到现有 Python 领域边界。** 新的发布执行器必须按 `inspect → upload → wait → mutate → verify` 分阶段运行；每个动作只在前置页面事实满足时执行，动作结果不能直接等价于 READY。
4. **先保持 Playwright 作为当前规范 runtime，但把它限制在上述有状态协议内。** Ego Lite 只在独立受控 spike 中验证；通过身份、恢复、证据、安全 Guard、降级和桌面打包门槛后，才允许新增 `EgoLiteBrowserRuntime` 并切换默认值。该决定修订 ADR-011 的“只做手动探索”表述：允许协议兼容的受控适配，不允许当前直接切换生产默认值。

## PUB-5 纠偏后的实现顺序

1. **Executor 协议**：为每个阶段定义输入、输出、checkpoint、evidence 和 typed blocker；任何阶段失败都保留已经证明的前缀。
2. **任务/草稿身份**：在 `PublishRun.checkpoint` 中保存脱敏的 runtime kind、task-space stable name/id（或 Playwright draft fingerprint）、package fingerprint 和 attempt；ID/name 不匹配时 fail-closed。
3. **上传阶段**：先 inspect 当前页面；目标已完成则复用，处理中则只等待，只有确认没有目标媒体时才注入一次；显式失败只允许一次有界重注入。
4. **字段阶段**：标题、正文、话题、设置、封面进入单一 UI queue；每一步完成后立即 fresh readback；话题必须是实际 entity，封面必须产生可复核 receipt。
5. **恢复阶段**：重启/浏览器断开只进入 typed blocker 或同一 run 恢复，不静默创建第二个上传；runtime 失联时本次 invocation 停止后续 mutation。
6. **真实抖音测试**：只做一次有界运行；先复用当前已登录 profile，记录每阶段证据；若在封面/话题失败，不重跑上传，先修对应阶段再用同一 run 恢复。

## 非目标与安全边界

- 不点击最终发布，不把 `waiting_for_human` 误报成成功。
- 不在当前 PUB-5 同时扩展快手、视频号、小红书；它们复用协议，分别建立平台 Entry 和 adapter。
- 不把 DOM 输入存在、预览卡出现或 helper 返回成功当成媒体/封面完成证据。
- 不把本次真实抖音失败解释为平台不可做；当前失败只能说明现有执行器尚未满足上述协议。

## 验收门槛

PUB-5 只有在同一 package/run 上完成以下证据后才可关闭：

- 目标账号/profile 与页面/草稿身份一致；
- 视频上传完成且重启恢复不重复注入；
- 标题、正文、真实话题 entity、封面 accepted URL 均 fresh readback 通过；
- 每个阶段有脱敏事件和 checkpoint，失败可从最近已证明阶段恢复；
- `waiting_for_human`、FinalActionGuard、final publish click count=0；
- 独立六维审查确认无 P0/P1。
