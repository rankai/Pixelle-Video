# PUB-4 / PG-J closure implementation 独立六维复审（2026-07-21）

结论：`implementation_pass_with_boundary`；P0=0；P1=0；无修复清单。

审查线程：`/root/pg_a_closure_reviewer_v3`（只读，不修改代码）。

## 六维验证

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过（有界） | Tauri/sidecar 两轮生命周期、canonical handoff refresh/remount/restart/leave-return、通用 `/publish` 菜单返回、fallback、resolver 三态、无假发布和 external_actions=0 均有证据。 |
| 逻辑正确性 | 通过 | `LAST_PUBLISH_HANDOFF_STORAGE_KEY` 与允许 query 白名单独立保存；未知 query fail-closed；resolver unique=200、stale/ambiguous=409；fallback 不创建新 package/run。 |
| 边界与安全 | 通过（有界） | fallback 测试断言复制、视频/封面预览 blob URL、下载、无绝对路径；人工确认边界保留；未打开平台、未授权、未上传、未创建 PublishRun、未最终发布。 |
| 代码质量 | 通过 | TypeScript build、scoped Ruff、`git diff --check` 通过；仅既有 Vite chunk warning 与 Pydantic 弃用 warning。 |
| 测试覆盖 | 通过（有界） | 独立复验 Vitest 8 files/45、Python scoped 53 passed/12 existing warnings、coordination contract 18 passed；preview DOM 与 generic menu recovery 修复后重新验证。 |
| 实际运行结果 | 通过（本地有界） | 重建 sidecar SHA `c1bf9cce23318427dcac102eed42ab07c3c6661676ef33a929704690283987d0`；Tauri/sidecar 两轮 health=200、停止后端口关闭；无残留进程。 |

## 复审结论与边界

- 本地生命周期与 AppShell handoff 是组合证据，足以支撑本地 bounded implementation；不等价原生 WebView 黑盒重启/返回因果验证。
- 历史 sidecar 二进制因缺少 `waiting_for_login` 枚举读取同一现有 DB 时崩溃；未删除数据库，重建当前 sidecar 后同库两轮启动通过，保留为 P2 启动兼容性边界。
- 跨进程 CAS/锁清理、真实平台 adapter/provider、最终人工发布和原生 WebView 黑盒仍后置；不得把本 Gate 解释为真实平台发布成功。
- 全仓 Python 回归曾暴露既有 AC-4 图文失效原因断言（`CAROUSEL_ARTIFACT_VERSION_REPLACED` 与当前 `ARTIFACT_VERSION_REPLACED` 不一致），且完整套件在其他历史测试处停滞；该问题不属于 PUB-4 closure 变更，已作为全局回归边界登记，不影响本 Stage scoped Gate。

## 独立复验命令

- `npm run test -- --run`：8 files / 45 tests passed；
- `npm run build`：passed；
- `uv run pytest -q`（PUB-4/PJ-J/desktop/coordination scoped aggregate）：53 passed，12 个既有 Pydantic warning；
- `uv run ruff check`（本 Stage Python scope）与 `git diff --check`：passed。
