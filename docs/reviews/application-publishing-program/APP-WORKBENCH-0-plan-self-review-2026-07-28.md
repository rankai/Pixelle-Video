# APP-WORKBENCH-0 应用工作台优化方案六维自审

- 日期：2026-07-28
- Change Request：`CR-APP-WORKBENCH-001`
- 审查对象：`docs/superpowers/specs/2026-07-28-application-workbench-experience-optimization-implementation-plan.md`
- 方案 SHA-256：`ca54be8bb010e180fc324e77b43fe3e492b2bc68f8758998a5d98d65c973e9be`
- 审查结论：`passed_for_entry_with_boundary`
- P0：0
- P1：0
- 已修复 P2：3

## 1. 需求完整性

结论：通过。

方案已覆盖用户明确要求的四个层面：

1. 功能：项目业务资料、风格样例、四应用输入能力、结果编辑和版本化；
2. UI 布局：桌面左右工作台、窄窗口配置/结果 Tab、sticky 主动作；
3. 结果展示：空、运行、失败、待审、已保存，以及文案、标题、图文、数字人的领域结果组件；
4. 结果传递：固定来源版本的 `ArtifactHandoff`、发布中心 handoff、来源更新提示和幂等。

同时逐一覆盖门店营销文案、爆款标题、抖音图文、数字人双模式，并保留当前模型管理、FastAPI/Python、SQLite、资产库和最终发布人工确认边界。

## 2. 逻辑正确性

结论：通过。

- `ContentProject` 保存长期业务对象，`ContextSnapshot` 固定某次运行所用事实；
- `AppRun` 是生成执行入口，`ArtifactVersion` 是可编辑结果版本，`ArtifactHandoff` 是跨应用唯一传递方式；
- 风格只影响表达，不得增加项目外事实；
- 用户编辑不覆盖历史结果，而是新增版本；
- 目标应用接收固定来源版本，来源后续更新只提示，不隐式改写目标草稿；
- 数字人复用现有双模式执行链路，不因 UI 重构重复创建真实 Provider task；
- 最终发布自动点击继续为 0。

## 3. 边界情况

结论：通过，三项初审问题已在方案中修复。

| 初审问题 | 严重度 | 修订 |
| --- | --- | --- |
| “我的风格”若在本期持久化，会引入授权、治理和跨项目污染范围 | P2 | 本期仅允许单次 AppRun 的自定义参考；不建设持久化个人风格库或市场 |
| 长任务若显示估算百分比，容易形成虚假进度 | P2 | 只展示真实状态、已完成步骤和 Provider 已知阶段；未知进度不伪造百分比 |
| 快速切换项目时旧异步请求可能覆盖新项目输入 | P2 | 要求使用 `AbortController`、request sequence 或等价机制，并纳入前端测试 |

方案还明确覆盖无项目、资料缺失、模型未配置、素材丢失、旧 v1 项目/Run、重复点击、Provider 失败、重启恢复、窄窗口和数字人已提交 task 等情况。

## 4. 代码质量与可实施性

结论：通过。

- 统一 `AppWorkbenchShell` 与领域结果组件，避免继续膨胀 `StudioApp`；
- 复用现有 tokens、主题、AppLLMPort、Repository、Runner、Artifact 和 Handoff；
- 不新增第二套模型配置、第二数据库事实源或新浏览器运行时；
- 分 Stage 实施，每个 Gate 限定允许范围和回滚；
- feature flag 允许回到旧工作区，运行中的 AppRun 和已生成 Artifact 不被删除；
- 数据演进使用版本化 ContextSnapshot/input schema，不破坏旧记录。

## 5. 测试覆盖

结论：通过。

计划覆盖：

- 后端契约、迁移、事实隔离、风格 Registry、ArtifactVersion 并发和 handoff 幂等；
- 前端布局、项目切换、Select/disabled/sticky 状态、结果编辑和双模式素材选择；
- 1440×900、1280×800、900×760、390×760 四档真实渲染；
- 一次有目的的文案、标题真实 Provider smoke；
- 本地图文渲染与 ZIP；
- 数字人优先复用既有真实质量证据，契约不变时不重复付费调用；
- production build、重启恢复和 UI flag rollback。

每个真实测试均要求先写清目的和预期，不允许无分析连续重试。

## 6. 实际运行与交付证据

结论：`plan_only_passed_with_boundary`。

本轮确认：

- 参考视频和截图已完成结构性审查；
- 当前产品信息架构、现有 tokens、四应用和数字人双模式边界已纳入方案；
- Windows hotfix 已由 Hosted Runner 完成 NSIS 安装、两轮启动/关闭/重开、sidecar health 和端口释放；
- 新安装器与 sidecar SHA-256 已在 macOS 下载后再次核对；
- 本轮没有调用 LLM、RunningHub、发布平台，也没有改业务 UI 或默认 feature flag。

边界：

- 本审查只放行 `APP-WORKBENCH-0` Entry，不代表应用工作台已经实现；
- 用户明确表示不测试本次 Windows 安装包，因此真实用户 Windows 设备验收仍不关闭；
- 产品负责人签字、真实平台 rollback 和原生 WebView SLA 继续保留在 `PROGRAM-ROLLOUT/PG-L`。

## 7. Gate 结论

`PG-AW-A` 当前可进入 `entry_in_progress`，但尚未通过。Luna 只允许交付契约、fixture、基线、Entry tests、回滚和证据，不得在 Entry Gate 通过前修改业务 UI 或执行真实 Provider。
