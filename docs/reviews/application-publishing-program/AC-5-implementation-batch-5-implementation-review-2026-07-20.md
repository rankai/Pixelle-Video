# AC-5 数字人口播 implementation batch 5 独立六维复审（2026-07-20）

## 复审范围

- 复审对象：本地/隔离 `execute_local` executor bridge、session/task/AppRun 聚合、绑定与恢复、local
  artifact fingerprint/accept、retry compensation、隔离 API execute→accept。
- 明确排除：真实 LLM/TTS/数字人 provider、浏览器、抖音授权/上传/发布、桌面新入口、生产 flag 开启。
- 审查线程：`/root/pg_a_closure_reviewer_v3`；审查线程不得修改业务代码，仅提交修复清单并复验。

## 六维结论

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | 绑定、三来源、状态投影、恢复、取消、失败/重试、严格 accept、API 安全投影均有实现与 fixture/test |
| 逻辑正确性 | 通过 | 48 项定向测试；覆盖幂等重放、上下文漂移、orphan running 恢复、completed replay 自愈和 generic 绕过拒绝 |
| 边界情况 | 通过（有界） | 缺失/跨项目/旧 entry、指纹漂移、篡改输出、并发单 attempt、retry 部分写入历史保留均 fail-closed |
| 代码质量 | 通过 | Ruff 相关实现/测试文件通过；`git diff --check` 通过；复用既有 AppRunner/Repository/Task projection |
| 测试覆盖 | 通过（有界） | 定向 48 passed/12 warnings；Stage 377 passed/12 warnings；全仓回归在 508/590 的既有后续测试长等待，未作为 Gate 证据 |
| 实际运行结果 | 通过（隔离边界） | TestClient execute→accept、local restart/reconcile、cancel/retry、并发和 production local-only guard 均实跑通过；无 provider/browser/platform side effect |

## 修复闭环

审查期间已修复并复验：

1. 禁止 `accept_fake` 绕过严格 imported review，隔离路径改用 `accept_local_outputs`；
2. 为 local generated outputs 增加确定性 fingerprint 与 exact-output accept guard；
3. running AppRun 重启恢复为 `APP_EXECUTOR_INTERRUPTED` 并变为 retryable failure；
4. 增加安全 execute API，并让 accept API 按 local/imported source 选择专用路径；
5. 绑定 `context_snapshot_id` 并拒绝幂等 replay drift；
6. needs_review/completed replay 自愈缺失 fingerprint 或 session step6；
7. retry 部分写入仅清理当前 attempt 新建 artifact，保留旧历史 artifact。

## 最终结论

`implementation_pass_with_boundary`，P0/P1=0，允许主线程推进 AC-5 的下一批；本批不关闭 PG-I。

后置 P2/边界：跨进程锁/CAS、sidecar 多 worker 一致性、真实 provider/浏览器/平台动作、桌面入口灰度，以及
legacy session 与 artifact/package handoff 的跨来源 fingerprint/`publish_package_ref` 收口。
