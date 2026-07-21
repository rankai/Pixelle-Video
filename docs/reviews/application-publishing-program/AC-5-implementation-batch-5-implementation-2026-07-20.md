# AC-5 数字人口播 implementation batch 5 实现记录（2026-07-20）

状态：`implementation_pass_with_boundary`；Entry 已通过 `entry_passed_with_boundary`，本批实现已完成独立六维复审。

## 实现边界

- 仅实现本地/隔离 executor bridge 与既有 legacy session/task/AppRun 聚合；
- 复用 batch 4 的 binding、fingerprint、review attempt、ArtifactVersion 和专用 accept；
- 生产 `digitalHumanInAppCenter` 保持关闭；不调用 LLM/TTS/数字人 provider、浏览器、抖音或任何真实平台动作；
- 不修改旧 `IpBroadcastWorkflow` 核心步骤、StudioApp 旧入口、PublishRun/PublishPackage、账号或模型配置。

## 交付实现

1. 从三种来源构造受控 executor input，并固定 `project_id/app_id/app_version/session_id/app_run_id/source_revision/context_snapshot_id` binding；
2. 将本地 executor 的 draft/queued/running/needs_review、waiting/failure/cancelled 状态映射到 AppRun 与 Task projection；
3. 重启 reconcile 复用同一 session/run/task projection；重复 execute 不创建第二 session/attempt；
4. cancel 幂等、failure fail-closed、retry 新 attempt 保留旧历史且不重复导入成功产物；
5. API 仅提供安全 projection，generic completion/transition 继续拒绝数字人完成绕过。

## 实施结果与证据

- 已实现 `execute_local` 隔离 executor bridge：复用同一 session/AppRun/Task projection，固定
  `project_id/app_id/app_version/session_id/app_run_id/source_revision/context_snapshot_id` 绑定；生产
  adapter 对 local-only executor fail-closed。
- 已实现状态与恢复：queued/running/needs_review/completed/failed/cancelled 映射、orphan running
  恢复为 `APP_EXECUTOR_INTERRUPTED`、cancel 幂等、失败后 retry 新 attempt；重试部分写入只清理本次
  attempt 创建的 artifact，不删除既有历史。
- 已实现严格 local accept：生成视频/封面/publish_copy 的 exact output、来源、指纹和绑定复核；重启
  修复缺失诊断；completed replay 修复 session step6；篡改或 generic complete/transition 绕过均拒绝。
- 已实现隔离 API `execute -> accept` 安全投影，接受 `context_snapshot_id` 并拒绝幂等重放漂移；未调用
  LLM/TTS/数字人 provider、浏览器、抖音或任何真实平台动作。
- Entry 证据：contract 4 passed/4 warnings；Entry 聚合 246 passed/12 warnings。
- 实现定向证据：adapter/API/artifact/Entry **48 passed、12 warnings**；Stage 聚合由独立审查线程复跑
  **377 passed、12 warnings**；Ruff 与 `git diff --check` 通过。
- 全仓 `uv run pytest -q` 曾运行至 **508/590** 后在后续既有发布账号测试处长时间无退出，已停止；该命令不作为本批通过证据，Stage/定向测试仍为本批 Gate 依据。

## 独立六维复审

- 复审记录：[`AC-5-implementation-batch-5-implementation-review-2026-07-20.md`](AC-5-implementation-batch-5-implementation-review-2026-07-20.md)。
- 结论：`implementation_pass_with_boundary`，P0/P1=0；需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖和实际运行结果均有证据。
- 保留 P2/边界：确定性的本地/隔离 executor 不等价真实 provider；跨进程锁/CAS 与 sidecar 多 worker
  一致性后置；生产 adapter 不允许 local-only executor；prompt_version/深层内部 binding 篡改校验可后续增强。

- Gate：`APP-IPB/PG-I implementation_pass_with_boundary`；本批完成但 **PG-I 尚未关闭**，下一批必须先
  冻结 legacy session 与 artifact/package handoff 的剩余验收，不得直接进入 PUB-INTEGRATION。
