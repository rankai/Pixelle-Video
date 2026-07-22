# AC-2 / APP-CORE Entry Review

- Stage：`APP-CORE`
- Gate：`PG-C`
- Review mode：独立严格审查，只读审查线程；主线程仅在本清单授权范围内收敛契约
- Reviewer：`/root/pg_a_closure_reviewer_v3`
- 当前结论：`pass_with_boundary`

## 已确认的前置条件

- `PG-B` 为 `passed_with_boundary`；APP-SHELL 已完成。
- 当前仍只有 Registry 实现，没有 ContentProject/AppRun/Artifact/Version/Handoff 的业务实现。
- 允许先做契约、失败测试和临时 SQLite dry-run；不得把这些准备工作标记为 PG-C 通过。

## 必须先收敛的 P1

### 1. AppRun canonical state

AppRun 统一使用：

```text
draft -> queued -> running -> needs_review -> completed
                  |             |
                  v             v
                failed       cancelled
```

`AppRun.state` 仅允许 `draft`、`queued`、`running`、`needs_review`、`completed`、`failed`、`cancelled`。
`completed` 表示用户接受产物版本；`succeeded` 仅保留给 PublishRun/发布步骤；
`waiting_for_login`、`waiting_for_human`、`needs_attention` 是发布/Task 等待态，不写入 AppRun。
Generic Task 对 AppRun 做同名状态投影；PublishRun 仍可使用其现有发布状态集合。
逐跳转规则以 `docs/contracts/app-center/app-run-state-transitions.json` 为准，终态不得继续执行；`failed -> queued` 只能创建新 Attempt 并保留旧错误证据。

### 2. SQLite executable contract

`docs/contracts/app-center/app-center-v1.sql` 是 AC-2 repository 的唯一表结构契约，必须覆盖：

- project schema/status/goal/brand/context snapshot；
- context schema/payload/brand revision/fingerprint；
- AppRun app version、state version、idempotency、input/context、session、completion；
- RunAttempt task/diagnostic/error/model metadata/usage/timing；
- Artifact source/status/name；ArtifactVersion source/file refs/fingerprint/version number；
- Handoff project/source/target/mapping fields。

任意 ID 重命名、拆表或新增第二事实源都必须走 Change Request。

当前命名已冻结为 `run_attempts.state` 与 `artifact_handoffs`；6.3 不再使用 `status` 或 `handoffs` 别名。

### 4. Entry failure matrices

迁移安全、AppLLMPort 和 Generic Task 投影的失败边界分别记录在：

- `docs/contracts/app-center/migration-safety-contract.json`
- `docs/contracts/coordination/app-llm-port.contract.json`（唯一 AppLLMPort 事实源）
- `docs/contracts/coordination/task-projection-failure-matrix.json`

这些是实现前置契约和失败测试输入，不代表 runner、AppLLMPort 或 Task 投影已经实现。

### 3. Registry ownership

- `pixelle_video.app_center.registry.BUILTIN_MANIFESTS` 是 P0 可执行 manifest 的唯一事实源。
- SQLite `app_registry` 只是初始化时事务写入的只读、带版本快照；没有用户写 manifest API。
- seed 以 `(app_id, version)` 幂等，必须在任何 AppRun/Handoff FK 写入前提交。
- SQLite 快照不能引入新的 executor、feature flag、模型配置或用户脚本。

## Entry 允许清单

- 修改 app-center schema/状态/投影/Registry ownership contract；
- 为非法状态跳转、SQL 字段/约束、seed 先决条件编写失败测试和临时内存 SQLite dry-run；
- 设计并登记 migration runner 的锁、备份、checksum、未来版本拒写和损坏恢复接口；
- 复核现有 `ConfigManager.llm`/`LLMService` 的 AppLLMPort 边界，但暂不接入真实 Executor。
- 为复合 `(app_id, app_version)` 外键和 Registry seed 顺序编写内存 SQLite 约束测试；
- 为迁移锁/备份/checksum/future-version/corruption、AppLLMPort 凭证隔离和 Task 投影清理编写失败矩阵测试。

## Entry 禁止清单

- 不写 ContentProject/AppRun repository、runner、API 或 Creation UI 业务实现；
- 不上线真实文案、标题、图文、数字人应用，不调用新 provider；
- 不改 publishing/asset 数据库所有权，不实现 PUB-2 恢复或平台自动化；
- 不引入第二模型配置源、请求级 model/provider/key、NestJS/Redis/PostgreSQL/SaaS；
- 不把 Registry 代码和 SQLite 当作两套可编辑事实源。

## PG-C Entry 复验要求

严格审查线程必须确认：

1. 状态 schema、非法跳转矩阵、output schema 和 projection 没有 `AppRun.succeeded` 歧义；
2. SQL 与 6.3 字段可逐表对照，重复 migration 不破坏结构；
3. Registry source/seed/FK 顺序和无用户写 API 有可执行证据；
4. 迁移 runner 的安全边界已进入实现任务清单；
5. 本轮已通过 Entry，主线程可以扩展到 repository/runner/LLMPort/fake executor；这些实现及真实安全行为测试必须在 PG-C 前完成，且不得扩大到真实 P0 应用或发布平台。
