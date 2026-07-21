# COORD-0 任务 8 恢复缺口与 PUB-2 交接协议

日期：2026-07-19；状态：`failed / handoff_to_PUB-2`；负责人：Luna（后续 PUB-2 实现）

## 已验证事实

现有 Playwright 基线在同一抖音 profile 上完成了“上传有效 MP4 → 进入视频编辑器 → 关闭第一个上下文 → 重开同一 profile”的一次性测试。关闭前确实进入编辑器；重开后回到 `/creator-micro/content/upload`，没有发现同一编辑器 URL、草稿句柄或可证明的恢复状态。因此 COORD-0 将任务 8 标记为 `failed`，不把它解释为未来 PUB-2 实现的结论。

证据：`COORD-0-douyin-playwright-midclose-recovery-2026-07-19.md`；截图 SHA `10a8717e…`。当前阶段只记录事实，不修改恢复代码、selector 或生产数据。

## PUB-2 必须实现的契约接缝

后续实现必须以 `ADR-PublishRunStateMachine.md`、`publish-run.schema.json`、`publish-run-waiting-human.json` 和 `publish-step-result-waiting-human.json` 为共同契约：

1. 每次发布尝试创建一个可追踪的 `PublishRun` 和幂等键；关闭/重启不创建第二个事实源。
2. 上传完成并进入编辑器后，持久化 checkpoint（至少包括 package、account、attempt、current_step、页面/草稿引用的脱敏摘要）。
3. 重开时优先恢复同一 run 和 checkpoint；找不到可安全恢复的句柄时进入 `needs_attention`，不得静默创建第二次上传。
4. 登录挑战进入 `waiting_for_login`；等待人工填写/确认进入 `waiting_for_human`；两者都不能映射成 `succeeded`。
5. 同一 profile 必须有锁；锁冲突、上下文仍存活或恢复证据不一致时停止并报告 `needs_attention`，不得并行打开第二个发布上下文。
6. 关闭发生在上传前、上传后、字段填写后、封面保存后，都要有可验证的恢复/回滚行为和相应 step result；重试必须产生新 attempt 并保留旧证据。
7. 最终发布仍是人工确认边界；自动化只能停在 `await_human_publish`，`FinalActionGuard` 拒绝自动点击最终发布。

## PUB-2 验收用例（实现后再执行）

| 用例 | 预期结果 |
| --- | --- |
| 上传前关闭并重开 | 同一 run 可安全恢复或明确 `needs_attention`；不产生重复上传 |
| 编辑器就绪后关闭并重开 | 恢复同一 package/run 和 checkpoint；不回到无上下文的“新上传” |
| 关闭后旧上下文仍持有 profile 锁 | 新上下文拒绝并进入 `needs_attention` |
| 重开遇到登录挑战 | `waiting_for_login`，不宣称成功 |
| 字段/封面完成后恢复 | 保留已完成 step result，按幂等键继续 |
| 到达最终发布按钮 | 只生成 `waiting_for_human`；Guard 拒绝自动发布 |

## 阶段边界

本交接协议不授权在 COORD-0 编写业务实现，也不授权再次盲目重复当前失败测试。进入 PUB-2 前必须先通过 PG-A，并在实现后基于同一套 schema/fixture 补充录像、事件 JSON、截图哈希和人工复验结论；若平台行为变化，新增 Change Request，不覆盖本次失败事实。

