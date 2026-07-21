# PROGRAM-ROLLOUT implementation batch 4 独立六维复审（2026-07-21）

结论：`implementation_pass_with_boundary`；P0=0，P1=0。允许进入后续 PG-L 证据批次，但不能关闭 PG-L 或默认放开灰度。

独立审查线程：`/root/pg_a_closure_reviewer_v3`。审查线程未修改代码。

## 六维结果

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过（有界） | 覆盖 profile-lock contention、crash recovery、create-run/account-list/active-run UI state p95、UI shell p95、双向 rollback、端口释放；Windows/真实 rollback/签字/观察窗明确留在 PG-L 边界 |
| 逻辑正确性 | 通过 | `is_desktop_mode() && PIXELLE_ROLLOUT_LOCAL_NOOP` 才允许 `auto_start=False`；默认未设置时仍 `auto_start=True`；token/capability/origin guard 未绕过 |
| 边界情况 | 通过（有界） | 2/2 第二 owner 被锁阻断并释放；2/2 exit=17 孤儿锁恢复；临时 SQLite/JSON/profile；V2→V1→V2 保留 history/active/profile，upload delta=0 |
| 代码质量 | 通过 | 本批脚本、API seam、测试 `ruff` 通过；`git diff --check` 通过；无浏览器/平台 selector/最终发布路径 |
| 测试覆盖 | 通过（有界） | batch4 contract 4 passed；相关 PUB-2/integration/batch3/4/desktop API 聚合 40 passed；Vitest 10 files/53；12 个既有 Pydantic warnings |
| 实际运行结果 | 通过（有界） | smoke `passed_local_bounded`；create-run p95 5.492ms、account-list 1.548ms、active-run state 1.068ms、active UI combined 1.763ms、UI shell 0.917ms；API/UI ports released；browser/external/final clicks=0 |

## 构建与安全边界

- `uv run python desktop/scripts/build_sidecar.py`：通过；
- `PATH=/Users/nickfury/.cargo/bin:$PATH npm run tauri build`：通过；
- no-op create-run 是隔离本地性能 seam，不代表生产请求关闭 executor；生产默认仍自动调度，但本批没有调用该默认路径；
- API/UI/observation probe 的 Generic Task 投影均指向临时 `PIXELLE_DESKTOP_TASKS_DB`；全局 `data/desktop_tasks.sqlite` 前后 count/status checksum/mtime/size 不变，修复后新增写入为 0。修复前误探针留下的历史失败任务未删除或覆盖；
- stderr 中可能出现开发配置模板绝对路径，但没有把原始 stdout/stderr 纳入 QA 证据；QA 仅保存结构化、脱敏摘要；
- 没有扫码、第三方授权、浏览器导航、平台上传、最终发布或破坏性清理。

## 未关闭项

Windows 构建、真实平台双向 rollback、产品负责人签字、7 天/20 个 bounded run 稳定观察窗口、原生 WebView 绘制 SLA 仍未完成；PG-L 保持 `open`，不允许正式灰度或默认启用发布 V2。
