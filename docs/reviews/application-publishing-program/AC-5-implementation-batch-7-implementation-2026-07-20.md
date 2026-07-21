# AC-5 数字人口播应用化 implementation batch 7（桌面新入口与隔离灰度）

状态：`implementation_pass_with_boundary`；实现、定向测试、local gray evidence 与独立六维复验已完成，当前唯一入口为 `APP-IPB/AC-5 implementation batch 7`。

前置 Entry：[`AC-5-implementation-batch-7-entry-review-2026-07-20.md`](AC-5-implementation-batch-7-entry-review-2026-07-20.md)，独立复审 `entry_passed_with_boundary`、P0/P1=0。

## 1. 本批目标

在不改变旧 StudioApp 口播 workflow、PublishRun/PublishPackage、模型配置事实源和任何外部平台动作的前提下，完成：

1. 应用中心数字人口播新路由 `/apps/digital-human-video` 的双 flag 门控；旧 `/ip` 保持可达。
2. 空白项目、文案 ArtifactVersion、selected_title ArtifactVersion 三来源的桌面输入与 `/api/app-center/ip-broadcast/runs` API 接线。
3. AppRun/legacy session/projection 的安全状态展示、cancel/retry/explicit accept 交互；waiting/needs_review 不得误显示成功。
4. app_run/session/source_revision/context_snapshot 的重启恢复；重启不重复 POST、session、attempt、execute 或 accept。
5. 测试专用 local isolated executor gray-cycle：三来源创建、运行停在 `needs_review`、显式 accept、零 provider/platform/final-publish 外部动作，并归档可审计证据。

## 2. 允许修改范围

- `desktop/src/features/app-center/**`：新 workspace、路由、卡片双 flag/readiness 门控、状态/错误/来源 UI 与测试。
- `desktop/src/StudioApp.tsx`、`desktop/src/AppShell.tsx`：最小新路由接线；旧 `/ip` 逻辑保留。
- `desktop/src/api.ts`、`desktop/src/featureFlags.ts`：类型安全 API 与默认关闭桌面 rollout flag。
- `desktop/src/styles.css`：新 workspace 最小样式。
- `tests/app_center_ip_broadcast_desktop_entry_contract_test.py`：仅契约测试增量；本批新增 desktop/API E2E 测试可放 `desktop/src/features/app-center/**`。
- `docs/reviews/application-publishing-program/qa/**` 与本批实现/审查文档。

## 3. 明确禁止

- 不调用真实 LLM/TTS/RunningHub/数字人 provider，不打开 Playwright/浏览器，不扫码、不授权、不上传、不点击抖音最终发布。
- 不在生产默认值中开启 `PIXELLE_APP_CENTER_DIGITAL_HUMAN` 或 `VITE_APP_CENTER_DIGITAL_HUMAN`。
- 不删除、重命名或自动跳转旧 `/ip`，不重写 `IpBroadcastWorkflow`。
- 不改变 AppCenter/PublishRun/PublishPackage/模型配置事实源，不引入管理员/RBAC/套餐/支付/多租户。

## 4. 实现顺序

1. 先补 desktop flag/API 类型与新 route 的纯组件测试。
2. 再实现 Registry card 的双门控和新 workspace；仅通过 API 读取/写入 AppRun binding，不复用旧 session local keys。
3. 接入三来源最小表单与 run create/status/execute/cancel/retry/accept；execute 只允许测试环境显式 local-isolated seam，生产 adapter 的 `APP_EXECUTOR_LOCAL_ONLY` 必须继续 fail-closed。
4. 实现持久化指针与重启 reconcile；测试相同 run/session/source revision 不重复创建。
5. 运行定向 Python/API/desktop 测试、desktop build、Ruff、diff check；生成一次 local gray-cycle JSON/截图或 DOM snapshot SHA 证据。
6. 更新本文件与台账，交独立线程六维 implementation 复验；有修复清单则循环，未 `implementation_pass_with_boundary` 不得进入下一批。

## 5. 本批验收矩阵

| 验收项 | 必须成立 |
| --- | --- |
| flag-off | 新卡片不可操作、旧 `/ip` 可达、无新 API write |
| flag-on + backend ready | 新卡片进入新 route；三来源字段按契约提交 |
| readiness | backend disabled/not_ready 时卡片不可操作且显示边界 |
| projection | safe fields only；waiting/needs_review 非 completed；secret/path 不显示 |
| restart | 同 project/run/session/source revision 恢复；POST/session/execute/accept 增量为 0 |
| local gray | 三来源各一轮、停在 needs_review、显式 accept；provider/platform/final publish 计数为 0 |
| compatibility | 旧口播页面/创建/恢复回归通过；Publish V2/API/模型配置回归不受影响 |

## 6. 当前证据状态

- Entry contract：3 passed；独立 Entry review：`entry_passed_with_boundary`。
- 桌面定向测试：`npm run test -- --run` — **6 files / 32 tests passed**。
- Desktop build：`npm run build` — passed；保留既有 chunk size warning。
- 后端/API/adapter/Entry/gray 聚合：**52 passed、12 warnings**；warnings 为既有 Pydantic V2 弃用警告。
- Local gray-cycle：[`qa/AC-5-batch-7-local-gray-cycle-2026-07-20.json`](qa/AC-5-batch-7-local-gray-cycle-2026-07-20.json)，三来源、重启同 run/session、needs_review→显式 accept→completed、provider/platform/final-publish 计数均为 0；QA JSON 已包含契约要求的 flag、project/run/session/source revision、重启前后绑定、artifact IDs 与外部动作计数，并由 Entry contract test 校验。
- 安全恢复增量：pending 提交持久化并携带 `source_artifact_id`，重启可恢复非首个来源产物并复用同一幂等键；AppRun 指针校验 project/session/source revision/context snapshot；切换项目会清理旧 run/pointer，切换来源产物会使旧 pending 幂等键失效；应用中心卡片的可操作投影同时满足 backend readiness 与桌面灰度 flag。
- Ruff 与 `git diff --check`：passed。
- 全量回归：本批不作为 Gate；若出现历史长等待，记录实际结果，不伪造通过。

独立复审：[`AC-5-implementation-batch-7-implementation-review-2026-07-20.md`](AC-5-implementation-batch-7-implementation-review-2026-07-20.md)，P0=0、P1=0；P2/边界为真实 provider/browser/抖音授权/上传/最终发布与连续生产灰度未执行。
