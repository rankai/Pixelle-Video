# PUB-4 implementation batch 3 Entry（2026-07-20）

状态：`entry_passed_with_boundary`；batch 2 已 `implementation_pass_with_boundary`，PG-J 尚未关闭。

## 本批目标

收缩旧 `/ip` Step 6 的重复发布编排，使其只交接到统一 `/publish` 事实源；补齐 artifact resolver 的后端契约/OpenAPI 登记；在 adapter 不可用时提供只读 trusted artifact copy/download fallback。仍不触发真实平台动作。

## 允许范围

- `StudioApp`/旧 `PublishWorkspace` 第 6 步只构造 package/artifact handoff 并导航 `/publish`，不得再调用旧 `preparePlatformPublish`。
- resolver endpoint 的 schema、OpenAPI operation id、404/stale/多候选 deterministic 规则与 API contract test。
- fallback 只返回 artifact key/受控下载或复制动作，不返回绝对路径、cookie、token、profile/session 内容；失败保持 package/run 可审计。
- flag-off/V1 回退测试、窄窗口/键盘可达性回归、desktop build、Ruff、diff 和独立证据。

## 禁止范围

- 不打开浏览器、抖音、第三方授权、扫码、上传或最终发布；不创建真实 PublishRun。
- 不清理旧 profile/session、不破坏性迁移、不引入第二模型源或管理后台/RBAC/套餐/支付/多租户。
- 不删除旧 `/ip` 页面；只收缩 Step 6 的重复发布职责并保留兼容回退。

## 必须验证的负例

- 旧 Step 6 不得调用 `preparePlatformPublish` 或创建第二 package/run。
- resolver 缺失 artifact、invalidated package、多候选不确定时必须 fail-closed。
- fallback 不得泄露绝对路径、secret、cookie、token、profile/session 数据。
- flag-off 保持旧发布页可达且不请求 V2。
- 键盘/窄窗口不形成死路，最终发布状态不得伪造成功。

## 退出条件

- resolver/backend/OpenAPI/legacy-step/fallback 契约和定向测试通过。
- 独立六维审查确认 `entry_passed_with_boundary`、P0/P1=0 后才进入实现。
- 本 Entry 不代表 PG-J、真实平台/provider 或最终发布完成。

## 独立六维复审

审查线程：`/root/pg_a_closure_reviewer_v3`（不修改代码）。

- 需求/契约：通过；旧 Step 6 收缩、resolver/OpenAPI、fallback 脱敏和外部动作边界已冻结。
- 逻辑：通过；resolver 缺失 404、失效 409、多候选 409，禁止静默选择候选。
- 边界：通过；9 个负例覆盖旧重复编排、resolver 错误、fallback 脱敏、flag-off、键盘/窄窗。
- 代码/测试：通过；契约测试 2 passed，Ruff 与 diff check clean。
- 实际运行：仅契约/fixture/OpenAPI 静态验证，无浏览器/平台动作。

结论：`entry_passed_with_boundary`，P0=0、P1=0。旧 Step 6 实际收缩、fallback 运行时和 resolver TestClient 留 batch 3 implementation。
