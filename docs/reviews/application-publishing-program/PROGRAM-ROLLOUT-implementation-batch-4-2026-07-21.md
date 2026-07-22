# PROGRAM-ROLLOUT implementation batch 4：崩溃/锁竞争、p95 与回滚演练（2026-07-21）

状态：`implementation_pass_with_boundary`。本批补齐了可在本地安全执行的 crash recovery、profile-lock contention、API/UI shell p95 与 V2→V1→V2 rollback rehearsal；不触发浏览器、平台、上传或最终发布。

## 实现

- `scripts/program_rollout_batch4_smoke.py`：启动隔离 sidecar 与 Vite preview，采集 health/apps/diagnostics/content-projects 以及 `account_list_api`、`create_run_api`、`active_run_state_api` 的 20 样本 p50/p95；Vite UI shell 还执行 active-run state 的组合请求；退出后验证 API/UI 端口释放。
- rollout probe 同时通过 `PIXELLE_DESKTOP_TASKS_DB` 隔离 Generic Task 投影库，避免向用户现有 `data/desktop_tasks.sqlite` 写入；默认路径和生产行为保持不变。
- `PIXELLE_ROLLOUT_LOCAL_NOOP=true` 仅在隔离 desktop probe 中启用，使 `/api/publish/v2/runs` 测量 durable create-run 而不 schedule executor；生产默认仍 `auto_start=true`，探针不允许打开浏览器或访问平台。
- 同一临时 profile root 下执行 2 次跨进程锁竞争：第二 owner 必须收到 `ProfileLockError`，释放后可再次获取。
- 执行 2 次故意进程退出后的锁恢复：新进程使用 stale-lock policy 清理孤儿锁后重新获取。
- 在临时 JSON 状态中演练 `v2 → v1 → v2`，只切换入口模式，保留 profile、历史 run、active/waiting run 和 upload 计数。
- 所有结果明确记录 `external_actions=0`、`browser_actions=0`、`final_publish_clicks=0`；没有删除真实 profile、session 或发布数据。

## 证据

- `uv run python scripts/program_rollout_batch4_smoke.py`：`passed_local_bounded`。
- API p95：health 0.972 ms、desktop health 0.405 ms、apps 0.453 ms、diagnostics 4.295 ms、content projects 1.136 ms、account list 1.548 ms、create-run 5.492 ms、active-run state 1.068 ms（各 20 样本）。
- 必须指标均满足 Entry 阈值：create-run ≤300 ms、account-list ≤200 ms、active-run UI state ≤1,500 ms；UI shell p95 0.917 ms、active-run UI state 1.763 ms（各 20 样本）。这些是本地 HTTP/Vite bounded 指标，不解释为真实 WebView 绘制或平台 SLA。
- profile-lock contention：2/2 阻断第二 owner，2/2 释放后可复用。
- crash recovery：2/2 进程异常退出后成功重获锁（exit=17 为故意 `os._exit` 的 bounded fixture）。
- rollback：`v2 → v1 → v2`，历史/active/profile 保留，`upload_count_delta=0`、`destructive_deletes=0`、外部动作和最终发布点击均为 0。
- API/UI/observation probe 均设置 `PIXELLE_DESKTOP_TASKS_DB` 指向临时库；全局 `data/desktop_tasks.sqlite` 前后签名不变、修复后新增写入为 0。修复前历史误探针的 20 条失败任务按安全要求保留，未删除或覆盖。
- 本批不把脚本启动日志原文作为证据，QA 仅登记脱敏后的结构化摘要，避免模板绝对路径进入证据包。

## 边界与下一步

- 这是隔离本地 sidecar/Vite 与临时锁/状态的 bounded rehearsal，不等价于原生 WebView 黑盒崩溃、生产多进程负载、平台上传 SLA 或真实双向 runtime rollback。
- Windows 构建、真实平台回滚、产品负责人签字、7 天/20 个 bounded run 稳定观察窗仍未完成；PG-L 保持 open。
- 交独立严格审查线程按六维复验；复验通过后才可进入下一批，不能默认开启发布 V2 或放开抖音灰度。
