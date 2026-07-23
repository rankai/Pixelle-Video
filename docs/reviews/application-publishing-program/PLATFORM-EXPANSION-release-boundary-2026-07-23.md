# PLATFORM-EXPANSION release/rollback boundary（2026-07-23）

## 批次结论

本批完成三平台适配后的本地 release/rollback 边界收口。它不是平台正式发布 Gate，也不提升快手、视频号或小红书的 `release_state`；作用是把“未验证平台不得创建真实 PublishRun、UI 只能复制/下载回退、临时回滚可恢复到 `unverified`”固化为机器契约和可复验测试。

状态：`passed_with_explicit_boundaries`；独立六维复审已完成，P0/P1/实质性 P2 均为 0。

## 实现范围

- 新增 [`platform-expansion-release-boundary.contract.json`](../../contracts/publishing/platform-expansion-release-boundary.contract.json)，冻结三平台状态、未验证门禁、复制/下载回退、FinalActionGuard 和临时 SQLite 回滚范围。
- 新增 `tests/platform_expansion_release_boundary_test.py`：
  - 三平台初始 `unverified`、抖音 `pilot` 不变；
  - 未验证平台在创建 run 前统一返回 `PLATFORM_RELEASE_NOT_READY`，无 `publish_runs_v2` 写入、无浏览器启动；
  - 临时 SQLite 中逐平台执行“promotion → revoke”，账号 profile/login 状态保持，最终全部恢复 `unverified`；
  - 路径/凭证样式 evidence ref 被拒绝；
  - 三份真实平台证据仍为边界结果、release 未提升、最终点击为 0。
- 快手 live evidence 增加与视频号、小红书一致的显式 `release_gate` 投影，避免机器审查依赖隐含字段。

## 验证结果

- Python 定向聚合：`79 passed`（12 个既有 Pydantic 弃用警告）。
- Desktop：Vitest `10 files / 55 passed`；`npm run build` 通过。
- Ruff（发布服务与本批测试）、JSON parse、`git diff --check` 均通过。
- 详细机器证据：[`PLATFORM-EXPANSION-release-boundary-2026-07-23.json`](qa/PLATFORM-EXPANSION-release-boundary-2026-07-23.json)。

## 六维复审结论

独立审查线程 `/root/platform_expansion_foundation_reviewer` 只读复验需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖和实际运行结果：P0=0、P1=0、实质性 P2=0。复验确认未验证门禁发生在 TaskManager/browser 之前；promotion→revoke 恢复 `unverified`；现有三平台证据、最终点击 0 和 release gate 一致。

据此 `PLATFORM-EXPANSION` Gate 更新为 `passed_with_boundary`，按协调台账恢复 `PROGRAM-ROLLOUT/PG-L` Windows 外部闭环入口。

## 明确保留的边界

- 三平台 `release_state` 仍为 `unverified`，不执行真实 release promotion。
- 视频号、小红书重启后未保存草稿的 `STATE_AMBIGUOUS` 边界继续有效；快手封面 blob preview、标题不支持和话题文本 fallback 继续有效。
- 不读取凭证/cookie/storage，不自动扫码/验证码，不点击最终发布；本批 external actions 与 final click 均为 0。
- PG-L 的 Windows 安装/启动/重启/sidecar health、产品签字、真实平台双向 rollback 和 WebView SLA 仍未完成。
