# PUB-4 implementation batch 2 独立六维复审（2026-07-20）

结论：`implementation_pass_with_boundary`；P0=0；P1=0。

审查线程：`/root/pg_a_closure_reviewer_v3`（不修改代码）。

## 验证依据

- AppShell 保留并持久化允许的 `/publish` query；StudioApp 按 base path 渲染统一发布中心；未知 query fail-closed。
- `package_id`、`artifact_id`、`run_id` handoff/recovery refs 分层；artifact-only 通过 `/api/publish/v2/packages/resolve` 解析 trusted package，并校验 `artifact_refs`。
- 统一校验 `run.package_id` 与解析 package；API/preflight/stale 错误清空投影；事件校验 `run_id`、严格递增 `event_seq`、重复 ID/序号拒绝。
- Desktop：7 files / 41 tests passed；`npm run build` passed（既有 chunk warning）。
- Python：`tests/publish_v2_api_test.py tests/publish_integration_batch_2_entry_contract_test.py` 7 passed；12 个既有 Pydantic 弃用警告；Ruff 与 `git diff --check` 通过。
- 外部动作：浏览器、扫码、授权、上传、创建 run、最终发布均为 0。

## 后续边界

本结论只关闭 PUB-4 implementation batch 2，不关闭 PG-J。真实 Tauri 打包重启/离开返回、resolver 独立 backend contract/OpenAPI 登记、旧 `/ip` 重复编排收缩和 adapter fallback 留后续批次；不把本地 mock/contract 证据误报为真实平台完成。
