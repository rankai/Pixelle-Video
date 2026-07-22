# PUB-4 发布中心与生产链路整合 implementation batch 1 独立六维复审（2026-07-20）

审查线程：`/root/pg_a_closure_reviewer_v3`（不修改代码）

## 结论

- 状态：`implementation_pass_with_boundary`
- P0：0
- P1：0
- 允许：关闭 batch 1，写入台账并准备下一批 Entry
- 不允许：把本批视为 PG-J 完成，触发真实抖音/浏览器/授权/上传/最终发布

## 六维验证

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | `publishCenterV2` 默认关闭；`/publish` 作为统一入口；V1 `PublishAccountsView` 回退；V2 账号/运行安全投影和 package/preflight/run/events/accounts 类型化 client 已接线 |
| 逻辑正确性 | 通过 | flag-off 不调用 V2 API；flag-on 账号事实源为 `/api/publish/v2/accounts`；无 package/run 时只显示安全空态，不显示“已发布/完成” |
| 边界情况 | 通过（有界） | 本批不创建 `PublishRun`、不选择平台、不上传、不最终发布；账号登录/试点/未验证/诊断状态有投影；旧 `/ip` 的历史 `PublishWorkspace` 编排按本批兼容范围保留 |
| 代码质量 | 通过 | Desktop build 通过（仅既有 chunk size warning）；Ruff 与 `git diff --check` 通过；类型化 API 未引入第二事实源、secret 或绝对路径 |
| 测试覆盖 | 通过（有界） | Vitest 7 files/34 tests passed；Python 定向 8 passed；V2 flag fallback、账号投影、空运行态和兼容回归均有测试 |
| 实际运行结果 | 通过（本地有界） | 仅执行本地定向测试、构建与 API bounded tests；未打开浏览器、未扫码、未授权、未上传、未最终发布，外部动作计数为 0 |

## 后续修复/边界清单

1. 后续 batch 处理旧 `/ip` Step 6 的 `PublishWorkspace` 重复编排移除或收缩；本批不改旧兼容路径。
2. 后续 batch 接入真实 package/run handoff、timeline、刷新/离开/重启恢复和 adapter fallback E2E。
3. 既有 chunk size warning 与 Pydantic 弃用警告登记为 P2 技术债，不阻塞本批。

最终结论：PUB-4 implementation batch 1 通过有界独立六维复审，`implementation_pass_with_boundary`，P0/P1 均为 0。
