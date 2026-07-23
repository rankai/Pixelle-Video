# Mac 应用中心与发布账号管理可视化评测（2026-07-23）

状态：`partial_pass_with_findings`

本批只评测当前前端在 macOS 开发环境的实际渲染，并补充 API 正常、未就绪、空结果和错误回退截图。运行环境为 FastAPI + Vite + Codex in-app browser/Playwright；由于当前机器 `cargo` 不在 PATH，`tauri build --bundles app` 未能执行，因此本批不把开发模式证据冒充打包 Tauri 验收。

## 已验证

- 应用中心在 1280×800、1440×900 均能呈现 4 个 Registry 卡片，正常态显示“可用/可进入新流程”，打开流程按钮可用。
- 应用中心关闭 readiness/feature flag 时，4 个卡片显示“未开启”，查看规划按钮保持禁用，没有误导性可用状态。
- 应用中心 API 不可用时，显示全局连接提示、目录不可用提示、重试/关闭动作和空结果回退。
- 默认 V2 发布中心账号分区显示抖音已登录/试点、快手未连接/未验证、小红书未连接/未验证；刷新状态按钮可用，人工确认边界可见。
- 发布 API 不可用时，显示连接错误、发布中心数据暂时不可用和安全回退，不伪造已发布状态。
- 旧版账号管理回退组件显示抖音、视频号、快手、小红书四个平台，能够看到添加账号、检测登录、清理登录态、归档等管理动作。

## 视觉/交互发现

### 1. V2 账号分区没有显示空平台

当前 V2 账号摘要按已有账号分组渲染，因此暂无账号的视频号不会显示。后端平台能力接口仍返回视频号，但用户在默认 V2 页看不到“视频号/添加账号”入口。

这不是本批新增的实现改动，但应在后续 UI 决策中明确：V2 是否承载完整账号管理；如果承载，应按平台能力渲染空平台卡片，或明确跳转到账号管理页。

### 2. 旧版四平台管理卡片在紧凑视口下拥挤

旧版 `PublishAccountsView` 的账号行复用了外层 `.publish-account-card` 三列布局，导致账号名称多行折断、操作按钮拥挤；1280×800 下下方平台卡片需要滚动才能看到。1440×900 能看到四个平台，但内层账号卡仍显得过窄。

建议后续修复时拆分外层平台卡与内层账号行 class，并让账号操作区独立换行；这属于 UI 修复，不应在本批证据中标记为已完成。

## 自动化结果

- `npm run test -- --run --reporter=dot`：10 个文件、55 项通过。
- `uv run pytest -q tests/publish_account_repository_test.py tests/publish_profile_manager_test.py tests/publish_account_service_test.py tests/publish_account_api_test.py tests/app_center_registry_test.py`：25 项通过，12 个既有 Pydantic 弃用警告。
- `npm run build`：通过；仅有既有 Vite chunk-size warning。

完整截图与 SHA-256 见 [`qa/mac-visual-2026-07-23.json`](qa/mac-visual-2026-07-23.json) 和 [`qa/mac-visual-2026-07-23/`](qa/mac-visual-2026-07-23/)。

## Gate 结论

`Mac 开发模式视觉证据：passed_with_boundary`  
`Mac 打包 Tauri 视觉验收：not_run_boundary`  
`发布账号管理视觉：partial_pass，需要处理上述两个 UI 边界`

独立严格审查线程 `/root/platform_expansion_foundation_reviewer` 已完成六维复审：`P0=0`、`P1=0`、实质性 `P2=2`。两个 P2 正是上面记录的 V2 视频号空平台入口和旧版账号卡片布局问题；不阻断开发模式证据，但在修复/决策前不能宣称视觉完整通过。

本批不改变整体台账的 Windows `PROGRAM-ROLLOUT/PG-L` 等待状态，也不执行平台最终发布。
