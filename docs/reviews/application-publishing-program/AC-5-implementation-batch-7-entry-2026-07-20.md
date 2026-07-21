# AC-5 数字人口播应用化 implementation batch 7 Entry（2026-07-20）

状态：`entry_passed_with_boundary`；当前唯一入口已放行至 `APP-IPB/AC-5 implementation batch 7`。

本批次只冻结桌面端新入口、状态投影、重启恢复和本地隔离灰度证据边界。未通过独立 Entry 复审前，不得修改桌面业务实现。

## 1. 上位约束

- 唯一工作入口：`docs/reviews/2026-07-18-application-center-publishing-program-progress.md` 的 `current_stage=APP-IPB`。
- 领域要求：[`AC-5-entry-2026-07-20.md`](AC-5-entry-2026-07-20.md)、[`AC-5-implementation-batch-6-implementation-review-2026-07-20.md`](AC-5-implementation-batch-6-implementation-review-2026-07-20.md)。
- 本批 Entry 契约：[`ip-broadcast-desktop-entry.contract.json`](../../contracts/app-center/ip-broadcast-desktop-entry.contract.json)。
- 本批 fixture：[`ip-broadcast-desktop-entry-fixtures.json`](../../contracts/app-center/fixtures/ip-broadcast-desktop-entry-fixtures.json)。

## 2. 本批目标

1. 冻结 `digitalHumanInAppCenter` 后端 flag 与 `VITE_APP_CENTER_DIGITAL_HUMAN` 桌面灰度 flag 的双重门槛；默认均为关闭。
2. 冻结新应用路由 `/apps/digital-human-video` 与旧 `/ip` 路由的所有权；flag 关闭时旧入口必须原样可达，新入口不得自动创建 session/run。
3. 冻结 `/api/apps` Registry 到应用卡片的安全投影：只有桌面 flag 开启、manifest enabled 且 readiness=ready 时才可操作；前端不得覆盖后端 readiness。
4. 冻结空白项目、`copywriting`、`selected_title` 三种来源到 `/api/app-center/ip-broadcast/runs` 的输入形状，以及 `AppRun/legacy session/projection` 的安全响应形状。
5. 冻结重启恢复：先读持久化 `app_run_id`，同 project GET 恢复；不得因为重启重复 POST、创建第二 session、自动执行或自动 accept。
6. 冻结一次本地隔离 gray-cycle 的证据字段：三种来源、flag-off/flag-on、重启复用、状态停在 `needs_review`、显式 accept、零 provider/platform/final-publish 外部动作。

## 3. Entry 冻结表

| 领域 | 冻结规则 |
| --- | --- |
| 路由 | 新应用使用 `/apps/digital-human-video`；旧 StudioApp `/ip` 不删除、不重命名、不隐式跳转 |
| flag | `digitalHumanInAppCenter=false` 或 `VITE_APP_CENTER_DIGITAL_HUMAN=false` 时新卡片不可操作；生产默认不变 |
| readiness | `GET /api/apps` 是唯一可用性事实源；桌面只能显示/收敛，不能把 disabled/not_ready 改成 ready |
| 来源 | `blank_project` 无来源版本；`copywriting` 恰好一个 copywriting 版本并有 variant index；`selected_title` 恰好一个 selected_title 版本；来源版本必须属于 project |
| API | create/resume 必须带 project、idempotency、source_mode 与对应来源；response 只投影安全字段，不返回原始 session state、绝对路径或 secret |
| 状态 | waiting/needs_review/needs_attention 不得映射为 completed；accept 是唯一显式完成路径 |
| 重启 | 同一 `project_id + app_run_id + session_id + source_revision` 复用；GET 失败才清理本地指针并允许重新开始 |
| 隔离执行 | 本批仅允许 `enforce_feature_flag=False` 的 local isolated executor fixture；不能触达真实 LLM/TTS/数字人 provider、浏览器、抖音或 PublishRun |
| 证据 | 每个事件带 flag、project/run/session/source_revision、前后状态、artifact ids、外部动作计数和截图/DOM SHA；证据不得把 local gray 当生产灰度或真实发布 |

## 4. 允许范围（Entry 通过后）

- `desktop/src/features/app-center/**`：路由、卡片双 flag 门控、数字人隔离工作区和状态投影；保留旧 `/ip`。
- `desktop/src/StudioApp.tsx`：最小路由/旧入口接线，不重写旧 workflow。
- `desktop/src/api.ts`：新 app-run create/get/execute/cancel/retry/accept 的类型安全 API 方法；不携带 secret/path。
- `desktop/src/featureFlags.ts`：新增桌面 rollout flag，默认 false。
- `desktop` 前端测试、API/契约 fixture、QA 证据和本批审查文档。
- 为本地隔离 gray-cycle 注入测试 seam；生产 flag、provider、浏览器和平台 adapter 不得被打开。

## 5. 禁止范围与人工暂停点

- 不删除或隐藏旧一级口播入口，不修改旧 `IpBroadcastWorkflow` 核心步骤。
- 不改变 AppCenter/PublishRun/PublishPackage 事实源，不迁移 SQLite，不新增第二模型配置源。
- 不触发真实 LLM/TTS/RunningHub/数字人 provider、Playwright 浏览器、抖音二维码/第三方授权、真实上传、最终发布或任何账号/内容外部写入。
- 不建设管理员、RBAC、套餐、支付、多租户或远程控制面。
- 如测试误触真实授权/发布、需要扫码、验证码或人工确认，立即暂停并通知用户；不得自动重试。

## 6. Entry 退出条件

- 契约、fixture 和三项 contract tests 通过；`git diff --check` 和 Ruff 通过。
- 独立严格审查线程按需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六维复验，并确认 P0/P1=0。
- 复审结论为 `entry_passed_with_boundary` 后，才允许进入本批 implementation；若有修复清单，修复后必须复验。

## 7. Entry 复审结果

- 独立审查：[`AC-5-implementation-batch-7-entry-review-2026-07-20.md`](AC-5-implementation-batch-7-entry-review-2026-07-20.md)。
- 结论：`entry_passed_with_boundary`，P0/P1=0。
- 运行证据：3 个 contract tests passed；Ruff、`git diff --check` clean。
- P2：真实桌面路由/运行时重启 E2E、本地灰度录像与连续生产灰度后置；不阻塞 implementation 开始。

## 8. 本批不代表完成的事项

本 Entry 不代表桌面业务已实现，不代表真实 provider、浏览器、抖音授权/上传/最终发布、连续生产灰度一个周期或 PG-I/PG-J/PG-K 已通过。PG-I 仍必须在 APP-IPB 完成 AC-F 的实现、证据和独立 Gate 后才可关闭。
