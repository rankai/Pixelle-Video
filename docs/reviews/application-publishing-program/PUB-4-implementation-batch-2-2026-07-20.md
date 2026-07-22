# PUB-4 发布中心与生产链路整合 implementation batch 2（2026-07-20）

状态：`implementation_pass_with_boundary`；batch 2 Entry 已 `entry_passed_with_boundary`，并经独立六维复审。本批仅实现安全 package/run handoff 与只读 timeline/recovery，不进入真实发布。

## 实现内容

- `PublishCenterView` 从 canonical `#/publish?package_id=...&run_id=...` 读取 handoff/recovery refs。
- 通过既有 V2 API 读取 package、preflight、run、events；不创建 PublishRun、不选择平台、不上传。
- package-only handoff 显示“已接收应用产物 handoff”；package+run 恢复显示同一 run 与事件序列。
- package/run API 错误、失效包或 preflight 非 ready 时清空投影并显示安全错误，不显示 published/completed 假状态。
- flag-off 继续使用旧 `PublishAccountsView`，不发 V2 请求。

## 定向验证

- `npm run test -- --run`：**7 files / 41 tests passed**；新增 canonical hash handoff、artifact→trusted package resolution、artifact ref 切换、query unknown-field reject、package/run 与 artifact/run mismatch、event order/ownership guard、API/preflight/stale fail-closed、package/preflight/run/events 调用与 timeline 投影测试。
- `npm run build`：passed；保留既有 chunk size warning。
- `uv run ruff check tests/publish_integration_batch_2_entry_contract_test.py`：passed。
- `uv run pytest -q tests/publish_v2_api_test.py tests/publish_integration_batch_2_entry_contract_test.py`：**7 passed**、12 个既有 Pydantic 弃用警告；`git diff --check`：passed。
- 外部动作：0；未打开浏览器、未扫码/授权、未上传、未创建 run、未最终发布。

## 待独立复审

需从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六维复验；P0/P1=0 后才可关闭 batch 2。AppShell 已保留允许的 publish query 与 localStorage 恢复指针，并对未知 query fail-closed；PublishCenter 已校验 package/run 与 artifact/run 一致性、artifact ref 切换、事件归属、严格递增与重复事件。真实打包 Tauri 重启、旧 `/ip` 重复编排收缩和 adapter fallback 仍不在本批宣称完成。

## 独立六维复审结论

审查线程：`/root/pg_a_closure_reviewer_v3`（不修改代码）。

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | package/run 与 artifact handoff、trusted resolver、preflight/package/run/events 只读投影、flag fallback 已落地 |
| 逻辑正确性 | 通过 | AppShell 保留/持久化 query；StudioApp 识别 query；package/run 与 artifact/run 一致性、artifact_refs、事件归属/顺序/重复均 fail-closed |
| 边界情况 | 通过（有界） | 未知 query、API/preflight/stale 错误清空投影；不创建 run、不选平台、不浏览器、不上传、不最终发布 |
| 代码质量 | 通过 | Desktop build、Ruff、`git diff --check` 通过；仅既有 chunk size warning |
| 测试覆盖 | 通过（有界） | Vitest 7 files/41 passed；Python publish_v2+batch2 Entry 7 passed；新增 handoff 切换、两类 mismatch、event guard、stale/error |
| 实际运行结果 | 通过（本地有界） | 仅 UI/API mock/contract tests；外部动作 0 |

结论：`implementation_pass_with_boundary`，P0=0、P1=0。P2/后续为真实 Tauri 重启/离开返回 E2E、resolver 独立 backend contract/OpenAPI 登记、旧 `/ip` 重复编排收缩和 adapter fallback。
