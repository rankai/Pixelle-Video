# PUB-4 发布中心与生产链路整合 implementation batch 1（2026-07-20）

状态：`implementation_pass_with_boundary`；Entry 已 `entry_passed_with_boundary`，发布中心 V2 的只读事实源/路由接线和安全投影已完成，并经独立六维复审；不进入真实发布执行。

## 本批目标

1. 新增独立 `publishCenterV2` 桌面 flag，默认关闭；关闭时 `/publish` 保持现有账号页/V1 回退。
2. 新增统一发布中心 V2 入口组件，读取 `/api/publish/v2/accounts` 等既有事实源，不维护第二份账号状态或“可用”静态文案。
3. 发布中心初始只提供“发布运行”和“发布账号”安全投影；无 package/run 时明确空状态，不伪造已发布/成功。
4. 为 package/run/events/preflight API 建立类型安全的桌面 client；本批只读/预检，不创建 run、不选择平台、不上传、不最终发布。
5. 保持旧 `PublishWorkspace` 业务编排不变；删除重复编排留后续 batch，先锁定路由/事实源边界。

## 允许范围

- `desktop/src/featureFlags.ts`、`desktop/src/api.ts`。
- 新增 `desktop/src/features/publishing/PublishCenterView.tsx` 及其测试。
- `desktop/src/StudioApp.tsx` 最小路由渲染切换；`PublishAccountsView` 作为 flag-off fallback 保留。
- `desktop/src/features/app-center/AppShell.tsx` 只做必要的 `/publish` 路由保持。
- 对应文档、QA evidence、Entry/implementation review。

## 禁止范围

- 不删除/重写旧 `PublishWorkspace`；不修改 `IpBroadcastWorkflow`。
- 不调用真实浏览器、抖音扫码/授权/上传/最终发布；不创建真实 PublishRun。
- 不引入第二模型源、管理员/RBAC/套餐/支付/多租户、第二浏览器 runtime。
- 不做破坏性迁移、profile/session 清理或远程状态写入。

## 验收矩阵

| 验收项 | 必须成立 |
| --- | --- |
| flag-off | `/publish` 回退现有账号页；V2 client 不发请求；旧生产入口可达 |
| flag-on | 发布中心显示 V2 安全投影；账号状态来自 `/api/publish/v2/accounts`；未连接/试点/未验证语义可见 |
| empty state | 无 package/run 时提示从项目/产物进入；不显示 published/completed 假状态 |
| API client | package、preflight、run、events、accounts 方法路径和类型稳定；本批无 POST run/平台动作 |
| UI | 发布运行/账号 tab 可键盘到达；窄窗口使用现有响应式布局；失败状态不丢账号摘要 |
| compatibility | 旧 `PublishWorkspace` 与 `PublishAccountsView` 测试不回归；build/Ruff/diff 通过 |

## 退出条件

- 实现、定向测试、desktop build、Ruff、`git diff --check` 和 implementation evidence 完成。
- 独立线程六维复验通过且 P0/P1=0，结论为 `implementation_pass_with_boundary` 后才进入 batch 2。
- 本批不关闭 PG-J；真实账号选择、package/run handoff、刷新/离开/重启恢复和 adapter fallback E2E 后置 batch 2/3。

## 当前证据

- 前端：`npm run test -- --run` — **7 files / 34 tests passed**；新增 `PublishCenterView` flag-off fallback 与 V2 account projection 测试。
- Desktop build：`npm run build` — passed；保留既有 chunk size warning。
- Python/API bounded：`tests/publish_integration_entry_contract_test.py tests/publish_v2_api_test.py tests/publish_account_api_test.py` — **8 passed、12 个既有 Pydantic 弃用警告**。
- 代码质量：Ruff clean；`git diff --check` clean。
- 外部动作：0；本批未创建 PublishRun、未打开浏览器、未扫码/授权/上传/最终发布。

## 独立六维复审

审查线程：`/root/pg_a_closure_reviewer_v3`（不修改代码）。

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | 默认关闭、`/publish` canonical route、V1 fallback、V2 只读账号/运行投影、typed client 均落地 |
| 逻辑正确性 | 通过 | flag-off 不请求 V2；flag-on 读取 `/api/publish/v2/accounts`；空状态不伪造已发布 |
| 边界情况 | 通过（有界） | 不创建 run、不选平台、不上传、不最终发布；旧 `/ip` 历史 `PublishWorkspace` 保留，重复编排后置 batch 2/3 |
| 代码质量 | 通过 | build、Ruff、`git diff --check` 通过；未暴露 secret/path |
| 测试覆盖 | 通过（有界） | Vitest 7 files/34 passed；Python bounded 8 passed；既有 12 个 Pydantic 弃用警告已登记 |
| 实际运行结果 | 通过（本地有界） | 仅定向测试/build/API bounded；外部动作计数为 0 |

结论：`implementation_pass_with_boundary`，P0=0、P1=0。该结论只关闭 PUB-4 implementation batch 1，不关闭 PG-J；package/run handoff、timeline、刷新/离开/重启恢复、adapter fallback E2E 和旧重复编排移除后置后续批次。
