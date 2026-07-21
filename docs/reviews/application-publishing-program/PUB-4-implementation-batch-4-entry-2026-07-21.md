# PUB-4 implementation batch 4 Entry（2026-07-21）

状态：`entry_passed_with_boundary`；batch 3 已 `implementation_pass_with_boundary`，本 Entry 已经独立六维复审，PG-J 尚未关闭。

## 本批目标

只收口 PUB-4/PG-J 的剩余本地运行证据：刷新、离开返回、应用重启后的 canonical package handoff 保持；adapter 失败时复制/下载 fallback 可用；resolver 的唯一、失效、多候选状态在 backend runtime 中确定性 fail-closed。跨进程 CAS/锁清理、真实平台动作和最终发布不在本批。

## 允许范围

- `desktop/src/features/publishing/**`、`StudioApp.tsx` 的 package-only handoff、刷新/离开返回和安全 fallback 测试 seam；
- resolver TestClient/API contract 运行验证与必要的测试 fixture；
- 本地隔离 Tauri/sidecar lifecycle 或等价可审计 runtime evidence；
- `docs/contracts/publishing/**`、测试和 QA 证据。

## 禁止范围

- 不打开抖音或其他平台，不扫码、授权、上传、创建真实 PublishRun 或点击最终发布；
- 不修改 PublishPackage/PublishRun 核心事实源的 schema，不做破坏性迁移；
- 不切换 Playwright/EgoLite，不引入第二模型源，不做管理员/RBAC/套餐/支付/多租户；
- 不把跨进程 CAS、锁清理或真实平台成功伪装成本批通过。

## 必须验证的负例

- refresh/leave/restart 不得丢失或重新创建 package handoff；
- adapter failure 不得显示已发布或暴露绝对路径/secret，复制/下载仍可用；
- resolver 唯一候选返回 200，失效/多候选分别返回 409；
- 所有外部动作计数为 0。

## 退出条件

- Entry contract/fixtures/test 通过；
- 独立六维审查确认 `entry_passed_with_boundary`、P0/P1=0 后才进入 batch 4 implementation；
- 本 Entry 不代表 PG-J、PUB-5、真实平台/provider 或最终发布完成。

## 独立六维复审

见 [`PUB-4-implementation-batch-4-entry-review-2026-07-21.md`](PUB-4-implementation-batch-4-entry-review-2026-07-21.md)，结论 `entry_passed_with_boundary`，P0/P1=0。真实 refresh/leave/restart、fallback 和 resolver runtime 证据转入本 Entry 放行后的 implementation 阶段。
