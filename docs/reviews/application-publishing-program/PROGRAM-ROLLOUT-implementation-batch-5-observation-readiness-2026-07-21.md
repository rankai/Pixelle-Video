# PROGRAM-ROLLOUT implementation batch 5：PG-L 观察窗准备（2026-07-21）

> 历史记录：本批执行时按 7 天策略登记；当前有效策略已由 [`PROGRAM-ROLLOUT-observation-window-policy-amendment-2026-07-21.md`](PROGRAM-ROLLOUT-observation-window-policy-amendment-2026-07-21.md) 修订为至少 1 小时。本文件中的旧数字保留为历史事实。

状态：`implementation_pass_with_boundary`。本批只建立可审计的观察窗样本和 rollback trigger 清单，不把本地 no-op 运行冒充 7 天稳定观察或产品签字。

## 实现与证据

- `scripts/program_rollout_observation_probe.py` 在临时应用/发布/Generic Task SQLite、临时媒体与临时 profile 根目录启动 sidecar；设置 desktop-only `PIXELLE_ROLLOUT_LOCAL_NOOP=true`，创建并回读 20 个 durable PublishRun，不写入用户现有任务库。
- 20/20 次 create-run 都有 `run_id` 且 state readback 成功；最新复跑的 create latency 最大 9.906 ms；API 端口释放为 true。
- 通过 `PIXELLE_DESKTOP_TASKS_DB` 使用临时 Generic Task 库；probe 前后全局 `data/desktop_tasks.sqlite` 的 count/status checksum/mtime/size 不变，新增写入为 0。
- 修复前一次错误探针曾向全局任务库遗留 20 条失败的 `publish_run` 任务；这些历史记录按安全要求保留，未删除、未覆盖，也不计入修复后证据。
- `executor_scheduled=0`、`browser_actions=0`、`external_actions=0`、`final_publish_clicks=0`；没有真实浏览器、平台或账号动作。
- rollback trigger 清单冻结为：P0/P1 regression、duplicate upload、final publish click、profile corruption。

## 关键边界

- `window_days_elapsed=0`，要求 `required_window_days=7`；本批只是 20 次本地 no-op durable run 样本，不能关闭 PG-L。
- 产品负责人 signoff 仍为 `pending`；Windows 构建、真实平台回滚、真实 WebView SLA 仍未完成。
- 稳定观察必须由后续连续时间窗口补齐，不能通过重复运行脚本或修改时间戳伪造。

## 下一步

交独立严格审查线程复验；通过后保留观察窗台账为 open，并等待真实 7 天窗口、产品签字及允许范围内的回滚确认，仍不默认开启发布 V2。
