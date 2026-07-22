# PUB-5 Stateful Executor Batch 1（2026-07-21）

## 结论

状态：`implementation_pass_with_boundary`。本批只收口执行器协议和可恢复本地 wiring，未关闭 PG-K，也未把模拟运行时当作真实抖音证据。

## 本批交付

- 阶段化执行协议：`inspect → upload → wait → mutate → verify`。
- schema v2 checkpoint：连续阶段前缀、`last_stage`、package/account/platform/attempt/profile 绑定、媒体与远端媒体 identity、typed blocker。
- 上传模式：`already_ready`、`resume_existing`、`injected`；可读文件 metadata 不匹配时 fail-closed，不重复注入。
- 重启恢复：file input 消失时只有 persisted remote media identity 与 fresh remote ID 对账成功才复用；否则 `STATE_AMBIGUOUS`。
- 话题证据：必须是有 `entity_id` 的真实实体，按请求顺序对账。
- 封面证据：本地 cover SHA、accepted HTTPS URL、task-space 绑定；resume 比对 canonical URL，避免签名 query 轮换误触发重做。
- RunService/API：checkpoint CAS、stage/blocker binding、状态投影和轻量服务 fake seam。
- FinalActionGuard：最终发布 click 永远为 0，终态仍需人工确认。

## 验证依据

- `uv run pytest -q tests/publish_*.py`：123 passed，12 个既有 Pydantic V2 弃用警告。
- scoped Ruff：通过。
- `git diff --check`：通过。
- 独立审查：六维 `implementation_pass_with_boundary`，P0/P1=0。

## 明确边界

- 本批只使用 fixture/模拟 runtime；既有 PG-G 手工 smoke 不包含本批 checkpoint callback、remote media identity、TopicEntityEvidence 和 CoverReceipt 持久化证据。
- 真实抖音 DOM selector、真实账号/profile、平台远端媒体 ID、话题实体和封面 URL 仍需下一步一次有界 headful E2E 验证。
- 不点击最终发布；扫码、挑战、第三方授权、平台状态不确定或需要人工接管时立即暂停。

## Headful partial evidence（2026-07-21）

- 同一 PublishRun 曾真实持久化 `inspect → upload → wait`，视频没有重复注入；旧运行时随后因话题写入形成 `##问答` 而停在 `TOPIC_READBACK_MISMATCH`。
- 只做一次聚焦 DOM/网络诊断后确认：点击 `#添加话题` 已注入 `#`；建议接口返回 `cid`；选择后编辑器产生 `data-mention="#"` 语义节点。运行时已改为只输入标签并绑定建议响应中的 `cid`，拒绝纯文本假阳性。
- 只做一次封面控件诊断后确认：图片注入异步打开 `role=modal` 裁切弹窗；限定点击弹窗内“保存”；保存后观察到新的 HTTPS CDN 图片回读，拒绝 blob/本地路径。
- 重新加载包含修复的 sidecar 后，旧 checkpoint 的 upload→post/video 路由变化触发了安全 `STATE_AMBIGUOUS/inspect`；已实现 canonical editor route 与已知同编辑器路由兼容，但仅在稳定 `task_space_id` 相同、host/path 属于已知编辑器空间且 cover receipt 名称 canonical 等价时放行；跨 ID 或异域/异路径均 fail-closed，尚未为验证该新代码而重新上传。

可审计的脱敏记录见 [`qa/PUB-5-stateful-headful-2026-07-21.json`](./qa/PUB-5-stateful-headful-2026-07-21.json)。这些证据不关闭 PG-K，也不等价于同一 package/run 已到 `verify` 或 `waiting_for_human`。

## Bounded read-only recovery probe（2026-07-21）

- 复用已登录的 Douyin profile 只读打开上传入口：`logged_in=true`，但页面没有视频预览、file metadata 或远端媒体标识。
- 当前 canonical task-space 与旧 checkpoint 不一致，因此无法证明是同一草稿；本次没有上传、字段 mutation、重试或发布动作。
- 该结果将恢复边界保持为 `STATE_AMBIGUOUS`，等待可证明的同草稿身份或人工确认后再做一次 bounded recovery。

## Bounded same-run recovery（2026-07-21）

- 在确认当前页面为空上传入口后，对原 `PublishRun` 发起一次 resume；执行器在 `inspect` 发现当前 task-space 与旧 checkpoint 不一致，记录 typed blocker `FOREIGN_DRAFT`。
- 该恢复在上传阶段之前停止：未发生第二次视频注入、字段 mutation、封面保存或最终发布；run 当前为 `needs_attention / inspect / FOREIGN_DRAFT`。
- 这证明了 fail-closed 边界，但仍不构成 PG-K 的完整成功证据；需要可证明的同草稿身份后才能继续。

## Bounded same-run attempt 3 and guarded reconciliation（2026-07-21）

- 依照复审放行，仅对同一 `PublishRun` 执行一次新的 bounded recovery；没有重新创建任务，也没有第二次重试上传。
- 本次真实 headful attempt 持久化完整阶段前缀：`inspect → upload → wait → mutate → verify`；视频注入计数为 1，后续没有重复注入。
- `mutate`/`verify` 证据包含 2 个带远端 entity ID 的话题实体、封面 HTTPS CDN receipt、`final_action_guard_armed=true`，且 `final_publish_click_count=0`。
- 运行时在写入 adapter result 时暴露了 state-version 竞态，短暂记录 `RUNNER_ERROR`；已改为回读最新 run version 后再追加事件，并增加受约束的 `verified_checkpoint_reconciled` 迁移。
- 代码修复后只执行一次 DB/service 层 `verify` 收口（不启动浏览器、不上传、不点击发布），源 run 已为 `waiting_for_human / await_human_publish`，版本递增且事件存在。
- 因此 PG-K 为 `passed_with_boundary`，不是已发布；最终发布仍由人工确认门保护。

## Restart recovery P1 修复与复验（2026-07-21）

- 独立复审发现：sidecar 初始化调用 `recover_after_restart()` 时，旧查询错误地把 `waiting_for_human` 当作 inflight，导致已验证 run 被降级为 `PROCESS_RESTART/needs_attention`。
- 修复 `recover_inflight_runs()`：只恢复 `queued/running`；`waiting_for_human` 是持久化的人工作业边界，重启必须保持原状态、checkpoint、Guard 和人工门。
- 新增回归测试：waiting-for-human 重启保持不变；queued/running 仍会进入 `PROCESS_RESTART/needs_attention`。
- 修复后重启 sidecar 并回读源 run：仍为 `waiting_for_human / await_human_publish`，版本 49，阶段前缀完整、话题 2、封面 receipt 1、最终点击 0；无浏览器动作。
- 本项 P1 已修复；独立复审确认 `PG-K=passed_with_boundary`，不等价于最终发布成功。

## 下一入口

按总协调台账 `current_stage=E2E-DOUYIN/PUB-5`，保留本批 `passed_with_boundary` 证据；不得新建第二次上传任务或绕过台账进入其他平台。下一步需由协调层决定是否进入后续平台批次，不能把本批人工发布门误记为自动发布完成。
