# PUB-4 implementation batch 4 Entry 独立复审（2026-07-21）

结论：`entry_passed_with_boundary`；P0=0；P1=0。

审查线程：`/root/pg_a_closure_reviewer_v3`（不修改代码）。

## 六维验证

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | Entry 明确冻结 refresh/leave-return/restart handoff、adapter failure copy/download fallback、resolver unique/stale/ambiguous 状态和外部动作 0。 |
| 逻辑正确性 | 通过 | contract 字段、fixture IDs、状态码与 fail-closed 规则一致；禁止范围不与 batch 4 目标冲突。 |
| 边界情况 | 通过（有界） | 明确不宣称 PG-J、跨进程 CAS/锁清理、真实平台或 final publish；所有外部动作保持 0。 |
| 代码质量 | 通过 | Entry test 只读 JSON、断言稳定；Ruff 与 `git diff --check` 通过。 |
| 测试覆盖 | 通过（Entry 有界） | 独立聚合 Entry/implementation contract 10 passed；batch4 Entry 单测 2 passed。 |
| 实际运行结果 | 通过（Entry 阶段） | Entry 仅冻结 implementation 输入；真实 refresh/leave/restart、fallback、resolver TestClient 运行证据留给 batch 4 implementation。 |

## Implementation 必须继承的门禁

- 真实本地 runtime 证明 refresh/leave/restart 不丢失或重复创建 canonical package handoff；
- adapter failure fallback 可复制/下载且不泄露绝对路径、secret、cookie、token；
- resolver unique=200、stale/ambiguous=409 的 TestClient 证据；
- external_actions 全为 0；不宣称跨进程 CAS/锁清理、真实平台或最终发布。
