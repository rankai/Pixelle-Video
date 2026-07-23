# PLATFORM-EXPANSION Entry（2026-07-22）

## 目的

按 `CR-PLATFORM-ORDER-001`，先于 Windows 外部安装闭环实现快手、视频号、小红书的发布前适配。这里的“完成”只指：平台入口、登录/挑战状态、素材填充、字段回读、人工停手和安全证据闭环；不包含最终发布按钮点击。

## 允许范围

- 复用 `PublishAccount`、`PublishPackage`、`PublishRun`、现有 Playwright runtime 和 `HumanConfirmedPublisher` 事实源。
- 为快手、视频号、小红书增加独立的 platform profile、入口 URL、状态识别、字段 selector、媒体/封面回读和 adapter version。
- 在 fixture/合约测试和可见 headful live smoke 中验证单次视频注入、标题/描述/话题/封面回读。
- 保留 `human_confirmation_required=true`、`allow_final_publish=false` 和 `final_publish_click_count=0`。
- 三个平台的 adapter 可以在隔离 runtime/fixture 中实现和验证，但 `platform_release_state=unverified` 时 UI 与 V2 API 均只提供复制/下载回退，不启动真实浏览器；只有独立 live gate 将平台账号登记为 `pilot` 后，才允许受控填充。

## 禁止范围

- 不实现、不暴露、不调用最终发布动作；`FinalActionGuard` 必须拒绝任何 final-submit 语义。
- 不自动扫码、验证码、第三方授权或绕过风控；遇到这些状态进入 `waiting_user`/`needs_attention` 并暂停。
- 不修改 PG-L 的 Windows、产品签字、真实 rollback 或 WebView 结论。
- 不修改平台默认 release state，不开启 Publish V2 默认 rollout，不建设管理员/RBAC/套餐/支付。
- 不引入第二浏览器运行时、第二模型配置源或新的凭证存储。

## Entry 验收矩阵

| 检查项 | 证据要求 |
| --- | --- |
| 三个平台注册 | platform profile、entry URL、adapter version、label 与 API 列表一致 |
| 登录/挑战状态 | signed-in、signed-out、captcha/unknown、window-closed 均有 fixture/状态分支 |
| 视频 | 单次 set-input-files、媒体 metadata/preview 回读；失败不得重试注入 |
| 文案 | 标题、描述逐字段填充与语义回读；不能用页面全文匹配冒充成功 |
| 话题 | 有平台实体 ID 时必须回读实体；不支持实体时显式记录 fallback boundary |
| 封面 | 仅使用图片 input/平台封面控件；有 receipt 才算成功，否则记录 boundary |
| 人工停手 | Guard armed、final click=0、`waiting_for_human` 或 `needs_attention` 可恢复 |
| 安全 | API/事件不含 cookie、QR、凭证、profile path、signed URL、原始页面内容 |

### 发布开放边界

`PublishRunService.create_run` 与 Publish Center 同时执行 release gate：快手、视频号、小红书在未通过独立 live gate 前拒绝创建真实 run（`PLATFORM_RELEASE_NOT_READY`），账号页明确显示“待独立 live gate；当前仅支持复制素材回退”。这不是平台实现失败，而是刻意保留的默认关闭与外部证据边界。

## 当前证据快照（2026-07-22）

- 三个平台的 profile/factory/统一停手执行器已落地；脱敏 synthetic DOM manifest、失败矩阵和事件安全回归已纳入测试。
- 一次只读 headful 入口探针记录在 [`PLATFORM-EXPANSION-live-entry-probe-2026-07-22.json`](qa/PLATFORM-EXPANSION-live-entry-probe-2026-07-22.json)：快手和小红书落在登录页；视频号导航被浏览器安全策略阻止；三者均未上传、未填充、未点击发布，release state 仍为 `unverified`。
- 后续快手探针仅打开一次登录入口，读取到手机号/密码表单后停止；未输入凭证，页面保留人工接管，不能视为已登录或 live gate 通过。
- synthetic DOM 夹具明确标注“不是 live evidence”，不能替代真实平台的登录复用、媒体 receipt、字段回读、重启恢复和 rollback。
- 当前定向测试已覆盖 adapter 失败矩阵和 final action guard；平台 Entry 仍不得标记通过。

## 实现批次与独立复审（2026-07-22）

- 适配实现、release gate、失败矩阵、合约/fixture 和安全事件回归已完成；视频号 `video_channel` alias checkpoint 绑定及挑战浮层优先级问题已修复。
- 独立六维复审见 [`PLATFORM-EXPANSION-implementation-review-2026-07-22.md`](PLATFORM-EXPANSION-implementation-review-2026-07-22.md)，P0/P1/P2 均为 0。
- 代码/测试 Entry 可通过，但真实平台 live gate 仍未通过；三平台 release state 保持 `unverified`，不得恢复 Windows。

## 通过条件

Entry 合约、三平台 adapter 失败矩阵、共同安全回归和独立六维审查通过后，按“快手 → 视频号 → 小红书”逐平台实现。三平台实现批次完成后，恢复 `PROGRAM-ROLLOUT` 的 Windows 外部闭环；不把本 Entry 解释为平台正式发布或默认灰度。

关联：[`platform-expansion-entry.contract.json`](../../contracts/publishing/platform-expansion-entry.contract.json)、[`CR-PLATFORM-ORDER-001`](../2026-07-18-application-center-publishing-program-progress.md#5-change-request)。
