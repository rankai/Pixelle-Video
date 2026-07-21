# AC-5 数字人口播 implementation batch 6 Entry（2026-07-20）

状态：`entry_passed_with_boundary`；batch 5 已以 `implementation_pass_with_boundary` 通过，PG-I 仍未关闭。

## Entry 目的

本批只冻结 PG-I 剩余的跨领域 handoff 验收，不直接修改业务代码。目标是证明同一口播产物在
legacy session adapter 与新 `ArtifactVersion` 来源之间不会产生不同事实、重复视频或重复
`publish_package_ref`，并把旧 session 恢复到新 AppRun 的三来源链路写成可执行契约。

## 允许范围（Entry 阶段）

- 新增/修订 `docs/contracts/app-center/**`、`docs/contracts/publishing/**` 的机器可读契约与脱敏 fixture；
- 新增 `tests/**` 的 Entry contract、fingerprint、幂等和三来源 handoff 负例；
- 新增本批 review/evidence 文档；
- 只读检查现有 `IpBroadcastAppAdapter`、`PublishPackageService`、`PublishCoreRepository`、
  `publish_package_ref` 生成与旧 session 恢复路径。

## Entry 禁止范围

- 不修改 `IpBroadcastWorkflow`、StudioApp、桌面 UI、PublishRun 核心状态机或生产 feature flag；
- 不调用 LLM/TTS/数字人 provider、浏览器、抖音授权/上传/最终发布；
- 不新增模型源、管理员/RBAC/套餐/支付/多租户能力；
- Entry 通过前不修改 package service 或 adapter handoff 实现。

## 必须冻结的共同契约

### 1. Canonical output identity

同一 `project_id + publishing_schema_version + video SHA + cover SHA + canonical publish_copy`
形成唯一 handoff identity。`source_revision` 仍是绑定与恢复的必需校验字段，但不是跨来源 package
fingerprint 的输入；它描述上游事实版本，不应让同一份最终媒体/文案因为来源表示不同而产生第二个包。
绝对路径、provider 临时字段、session 临时状态、AppRun ID 和 artifact ID 不进入跨来源内容指纹。
`source_kind` 仍保留用于审计，但不得导致同一内容产生两个 package fingerprint。

### 2. Legacy session → AppRun recovery

- 已绑定 session 只能恢复到其绑定的 project/app/version/context/source revision；
- 未绑定 session 必须显式 claim，禁止页面初始化自动认领；
- 重启/reconcile 重用同一 AppRun、Task projection 和 output ArtifactVersion；
- 跨项目、source revision drift、旧入口重复执行均 fail-closed。

### 3. Package and ref idempotency

- 同一 handoff identity 重复创建 package 返回同一不可变 package/fingerprint；
- artifact 来源与 legacy adapter 的 package snapshot 内容一致，差异只体现在审计 source kind；
- 同一 project/package 只允许一个 active `publish_package_ref`，重复调用不得追加重复 ref；
- 新 ArtifactVersion 或内容指纹变化必须生成新 package，并按既有规则使旧 ref/package 失效；
- 失败补偿只能清理当前尝试新建对象，不删除旧 session、旧 ArtifactVersion 或旧 package/ref 历史。

### 4. Three-source handoff matrix

`blank_project`、`copywriting`、`selected_title` 三种输入各自固定来源版本、context snapshot、
source revision；均可经过隔离 executor → explicit accept → package handoff。缺来源、混合来源、
跨项目版本、空标题/发布文案和上下文漂移均不得进入 package。

### 5. Error/state registry

本批只复用现有 adapter/publishing 错误码，不在 Entry 阶段创造同义码：
`SOURCE_MODE_EXACTLY_ONE`、`SOURCE_VERSION_PROJECT_MISMATCH`、`SOURCE_REVISION_MISMATCH`、
`APP_RUN_BINDING_MISMATCH`、`ARTIFACT_PUBLISH_COPY_INVALID`、`ARTIFACT_REGISTRATION_PARTIAL` 等
必须登记在 contract registry，并由每个负例 fixture 机器校验。`waiting_for_human` 与 `needs_review`
均保持非 completed，不能被 package handoff 自动完成。

## Entry fixtures / tests

至少覆盖以下 12 个机器可读场景：

1. legacy session 显式 claim → 同一 AppRun 恢复；
2. legacy session 未 claim / 跨项目 / source drift 拒绝；
3. blank/copywriting/selected_title 三来源的合法 handoff；
4. 同内容 legacy 与 artifact snapshot 的 canonical fingerprint 相等；
5. 路径/provider/session 临时字段不会改变 canonical fingerprint；
6. 同一 package 重放返回同一 package/fingerprint；
7. 同一 package ref 重放不新增 ref；
8. 新 ArtifactVersion 生成新 package 并使旧 ref 失效；
9. duplicate video artifact / mixed source / partial output fail-closed；
10. retry partial write 保留旧 package/ref/artifact 历史；
11. `waiting_for_human`、`needs_review` 不能自动变成 package completed；
12. feature flag off 保留旧入口且无新 package/ref 写入。

## Entry 通过条件

- 上述契约、fixture 和负例全部可执行；
- 现有 package service/core/adapter 的事实源与字段命名无冲突；
- P0/P1=0，Ruff、diff check 通过；
- 独立审查线程从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六维复验；
- Entry 通过后才允许实现 handoff，且仍不得执行真实 provider/浏览器/平台动作。

## Entry 复审结果

- 独立审查线程：`/root/pg_a_closure_reviewer_v3`。
- 结论：`entry_passed_with_boundary`，P0/P1=0；3 项 Entry contract tests passed，覆盖 24 个 fixture；
  Ruff 与 `git diff --check` 通过。
- Entry 已确认：错误码复用现有 registry；canonical SHA-256 实际计算；legacy/artifact 投影一致；
  版本变化同时失效旧 package/ref；waiting_for_human 与 needs_review 均不得完成。
- 保留实现边界：legacy restart/old-entry duplicate 的运行时行为和真实 package handoff E2E 必须在
  batch 6 implementation 完成，未完成前不得声称 PG-I 关闭。

## 下一步

进入 [`AC-5-implementation-batch-6-implementation-2026-07-20.md`](AC-5-implementation-batch-6-implementation-2026-07-20.md)，
只实现 contract 已冻结的 handoff；不触发真实 provider、浏览器、抖音授权/上传/最终发布。
