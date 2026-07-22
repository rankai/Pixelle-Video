# PG-I：口播产物可交接阶段级收口复审（2026-07-20）

状态：`passed_with_boundary`；独立严格审查线程已确认 PG-I 关闭，当前允许按协调队列进入 `PUB-INTEGRATION` Entry。

## 收口范围

本复审把 AC-F 的阶段验收要求与已完成批次证据合并验证，不新增业务实现：

| AC-F 要求 | 证据 | 结论 |
| --- | --- | --- |
| 原直接入口全回归 | 既有口播/数字人/状态/runner/渲染/UI confirmation 回归；本次聚合 280 passed/12 既有 Pydantic warnings | 通过（有界） |
| 新入口空白、文案、标题三来源 | batch 7 桌面 route/API 测试、local gray-cycle 三来源、AppRun adapter/API/Artifact handoff 测试 | 通过（本地隔离） |
| session/task/AppRun 状态映射稳定 | AC-5 adapter/API/runner/state/hand-off 测试；`needs_review` 非终态，accept 唯一显式完成路径 | 通过 |
| 取消/重试不产生孤儿项目或重复视频 artifact | batch 4/5/6 implementation review 与 adapter/artifact/handoff 聚合测试 | 通过（本地/SQLite） |
| 重启恢复正确口播步骤 | batch 7 pointer project/session/source revision/context 校验、pending 幂等恢复；batch 5/6 legacy handoff/reconcile 证据 | 通过（本地隔离） |
| 视频、封面、publish_copy 成为稳定 ArtifactVersion | batch 3 trusted file registration、batch 4 output binding、batch 6 canonical fingerprint/package handoff reviews | 通过（本地/可信 fixture） |
| flag-off 回到旧口播 | desktop entry contract、ApplicationCenter actionable/readiness tests、旧 `/ip` 回归 | 通过 |
| 新入口连续灰度一个发布周期 | batch 7 local isolated gray-cycle snapshot | 未执行真实连续生产灰度；保留边界，旧 `/ip` 不隐藏 |

## Stage 级验证结果

- 前端：`npm run test -- --run` — 6 files / 32 passed。
- Desktop build：`npm run build` — passed；仅既有 chunk size warning。
- AC-5/既有口播聚合：**280 passed、12 个既有 Pydantic 弃用警告**。
- QA：[`qa/AC-5-batch-7-local-gray-cycle-2026-07-20.json`](qa/AC-5-batch-7-local-gray-cycle-2026-07-20.json)；flag、project/run/session、source revision、重启前后绑定、三来源、artifact IDs 和外部动作计数均有字段；provider/browser/platform/final publish=0。
- 代码质量：Ruff clean；`git diff --check` clean。
- 独立审查：`/root/pg_a_closure_reviewer_v3`；不修改代码。

## 独立六维 Gate 结论

- 需求完整性：通过；AC-F 原入口回归、三来源、状态/取消/重试、重启、稳定 ArtifactVersion、flag-off 均有 batch 1–7 证据。
- 逻辑正确性：通过；legacy/artifact handoff、source pin、package/ref 幂等、旧/新路由所有权与状态投影一致。
- 边界情况：通过；local/SQLite/隔离 executor 明确不等价真实 provider/browser/抖音/连续生产，旧 `/ip` 保留。
- 代码与文档质量：通过；证据引用和状态口径无冲突，未修改代码。
- 测试覆盖：通过（有界）；AC-5/既有口播聚合 280 passed/12 existing warnings，batch7 前端 6 files/32，后端 52，build/Ruff/diff 通过。
- 实际运行结果：通过（本地隔离）；三来源、重启绑定、needs_review→explicit accept、Artifact/package/ref 证据通过。

P0=0，P1=0。连续生产灰度不是 PG-I 产物交接的 P1 阻断：旧 `/ip` 保留，未推进隐藏旧入口的产品决策；真实连续周期、provider/platform、最终发布继续作为 P2/后续人工边界。

## 六维复审要求

独立线程需从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六方面确认：

1. batch 1–7 的事实源和来源版本没有被桌面新入口绕过；
2. local gray evidence 不被误称为真实 provider、真实抖音或生产灰度；
3. PG-I 若以 `passed_with_boundary` 关闭，必须明确旧 `/ip` 保留、连续生产灰度和最终产品隐藏决策未完成；
4. P0/P1 必须为 0；否则返回最小修复清单，不更新 Stage Gate。

## 暂停边界

- 不启动真实 LLM/TTS/数字人 provider，不操作浏览器/抖音，不扫码、不授权、不上传、不最终发布。
- 不隐藏旧 `/ip` 一级入口；连续生产灰度和产品是否隐藏旧入口留待后续人工/产品决策。
- PG-I 通过不代表 PUB-INTEGRATION、E2E-DOUYIN、PROGRAM-ROLLOUT 或最终发布完成。
