# PUB-4 implementation batch 4 独立六维复审（2026-07-21）

结论：`implementation_pass_with_boundary`；P0=0；P1=0。

审查线程：`/root/pg_a_closure_reviewer_v3`（不修改代码）。

## 六维验证

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | `ADAPTER_UNAVAILABLE` 时提供安全 `#/ip` 回退；canonical package/artifact query 支持 refresh/remount/restart simulation 与 leave-return；resolver runtime 三态验证；外部动作全 0。 |
| 逻辑正确性 | 通过 | HashRouter 只允许 package/artifact/run query，未知字段 fail-closed；PublishCenter fallback 不声称已发布；resolver unique=200、stale/ambiguous=409。 |
| 边界与安全 | 通过（有界） | fallback 不暴露绝对路径、cookie、token、secret；不创建新 package/run；不宣称真实 Tauri restart、跨进程 CAS、真实平台或 final publish。 |
| 代码质量 | 通过 | TypeScript build、scoped Ruff、`git diff --check` 通过；仅保留既有 chunk size warning。 |
| 测试覆盖 | 通过（有界） | Python 聚合 20 passed/12 个既有 Pydantic warning；Vitest 7 files/44 passed；覆盖 leave→`#/apps`→原 package 返回、remount/restart、fallback、resolver 三态。 |
| 实际运行结果 | 通过（本地有界） | QA JSON 为 `passed_local_bounded`；resolver TestClient 返回 200/409/409；外部动作 browser/authorization/upload/publish_run_create/final_publish 全 0。 |

## 后置边界

- 本批 local AppShell remount/restart simulation 不等价真实打包 Tauri restart/leave-return；
- fallback 只验证安全入口/路由，真实旧工作区 copy/download/preview E2E 留后续；
- 跨进程 CAS/锁清理、真实 adapter/平台/final publish 与 PG-J Gate 仍未关闭。

## 复审后回归增量

主线程在本复审后补充了 `PublishWorkspace.test.tsx` 的 adapter failure copy/download fallback 断言；未改变生产逻辑。增量全量前端回归为 **8 files / 45 tests passed**，`npm run build`、scoped Ruff 与 `git diff --check` 仍通过。该增量已纳入 PUB-4 / PG-J closure evidence。
