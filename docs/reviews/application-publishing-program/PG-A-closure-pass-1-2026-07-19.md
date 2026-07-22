# PG-A 收口审查记录（Pass 1）

日期：2026-07-19  
Stage：`COORD-0`  
状态：`in_progress / reviewer_recheck_required`  
业务实现：未开始

## 结论

本轮完成了 COORD-0/PUB-0 的证据缺口修复，但不把本记录标记为 PG-A `passed`。九项当前版任务的证据、指标和最小 DOM fixture 已收口；任务 8 的失败是旧路径的真实 baseline outcome，恢复实现明确交给 PUB-2，不在 COORD-0 重试。最终是否放行由独立严格审查线程确认。

## 条件逐项状态

| PG-A 条件 | Pass 1 状态 | 依据 |
| --- | --- | --- |
| AC-0/PUB-0 ADR、schema、fixture、迁移 dry-run | `ready_for_recheck` | `docs/adr/008-015-*.md`、publishing/app-center schemas、SQLite dry-run、媒体 manifest、DOM fixture manifest |
| ArtifactVersion → PublishPackage V2 → PublishRun 收敛 | `passed` | shared contract、artifact/publish fixtures、semantic tests |
| artifact_versions 与 legacy_session 双来源 | `passed` | publish package source fixtures + invalid cases |
| AppRun/PublishRun/Generic Task 投影关系 | `passed` | `app-run-task-projection-matrix.json` + contract tests |
| AppShell 与 `/#/publish` 所有权 | `passed` | ADR-010 与 shared contract |
| SQLite 数据所有权 | `passed` | ADR-009、shared contract、迁移 dry-run |
| ADR-007 FastAPI 边界 | `passed` | ADR-007 accepted；当前无 Node/NestJS 迁移 |
| AppLLMPort / local-default | `passed` | AppLLMPort contract、model redaction tests |
| 管理后台 P1/P2 Deferred Capability | `passed` | 七项 AC-ADMIN-CONTROL 触发条件已登记，P0 不增加控制台 |
| 不开始真实 UI/业务实现 | `passed` | 当前改动仅 docs/contracts/tests/QA evidence；业务实现文件未改 |

## PUB-A 九项基线

统一指标与口径：[`qa/COORD-0-pub-a-nine-task-metrics-2026-07-19.json`](./qa/COORD-0-pub-a-nine-task-metrics-2026-07-19.json)  
SHA-256：`5384b7ad73591c892f53b4b9a2c5e6a9726e420fa3747d13dc492c5f773cd63f`

- 1/2/3/4/5/6/7/9：已有证据 + 指标已归档；不重复平台动作。
- 8：单次真实结果为关闭后回到 `/content/upload`，结构化 handoff 见 [`qa/COORD-0-task8-recovery-handoff-2026-07-19.json`](./qa/COORD-0-task8-recovery-handoff-2026-07-19.json)；状态保持 `failed`，恢复状态机归 PUB-2。
- 最小抖音 DOM fixture inventory：[`tests/fixtures/publishing/manifest.json`](../../../tests/fixtures/publishing/manifest.json)，覆盖 signed-in/signed-out、captcha、loading、network error、upload、progress、processing、editor fields、cover modal/error、waiting_for_human、unknown page；本轮只证明状态标记、语义 selector、隐私和 SHA inventory，1/50/100% 进度、延迟、关闭/崩溃恢复等行为 harness 后置 PUB-3。
- FinalActionGuard/V1 rollback：[`qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json`](./qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json) 仅为本地临时文件/contract smoke，不宣称平台 live smoke；`publish`、`confirm_publish`、`unknown` 均返回 `FINAL_ACTION_BLOCKED`，rollback 不产生生产写入。

## Strict reviewer 下一轮必须确认

1. `coord-0-shared-contract.md` 已标记 `frozen for COORD-0`，且任何后续变更走 Change Request。
2. `evidence_status=complete_with_boundary` 的语义为“九项 baseline 证据完整”，允许 task8 为 `failed`；不等价于恢复实现通过或 adapter release。
3. 本地 Guard/rollback smoke 是否足以满足 COORD-0/PUB-A 的契约层要求；真实平台 Guard、恢复和最终发布继续由 PUB-2/PUB-3/PUB-5 负责。
4. 确认不因全新 provider 生成、横版封面建议或最终人工发布阻塞 PG-A；这些留在后续 Stage。

在严格审查线程明确 `PG-A=passed` 前，台账仍保持 `COORD-0 / in_progress`，不得切换 `APP-SHELL / PG-B`。

## Pass 2 语义修订

根据第二轮审查，基线 fixture 的 `evidence_status` 已从容易误读的 `complete` 改为 `complete_with_boundary`，schema 描述明确它只表示九项证据和分离指标齐全，允许 task8 为 `failed`，不表示所有任务成功或 adapter 已发布。契约测试增加 task8 failed 交叉断言。DOM fixture manifest 也明确为状态/隐私/hash inventory；进度、延迟、关闭/崩溃等行为 harness 后置 PUB-3。当前仍等待最终 reviewer recheck。
