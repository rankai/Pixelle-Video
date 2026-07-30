# APP-WORKBENCH-6 Entry：交付与跨应用

日期：2026-07-28
Change Request：`CR-APP-WORKBENCH-001`
上位入口：`docs/reviews/2026-07-18-application-center-publishing-program-progress.md`
方案来源：`docs/superpowers/specs/2026-07-28-application-workbench-experience-optimization-implementation-plan.md` §10.7

## 1. Entry 结论

`PG-AW-F` 已通过，允许进入 `APP-WORKBENCH-6`。本阶段只实现应用结果之间的版本固定、交付和下一步导航，不进入 APP-WORKBENCH-7 灰度或视觉终审。

## 2. 冻结的交付矩阵

| 来源 | 目标 | 交付事实 | 目标行为 |
| --- | --- | --- | --- |
| 门店营销文案 | 爆款标题 | 选定的 `ArtifactVersion` | 创建/复用目标 draft，带入来源版本，目标页显示来源摘要 |
| 门店营销文案 | 抖音图文 | 选定的 `ArtifactVersion` | 打开图文工作台并固定来源版本 |
| 门店营销文案 | 数字人口播 | 选定的 `ArtifactVersion` | 打开数字人工作台并固定来源版本 |
| 爆款标题 | 抖音图文 | `selected_title` 的 `ArtifactVersion` | 打开图文工作台并固定来源版本 |
| 爆款标题 | 数字人口播 | `selected_title` 的 `ArtifactVersion` | 打开数字人工作台并固定来源版本 |
| 抖音图文 | 发布中心 | `PublishPackage` | 只导航到发布中心，按 package 载入，不触发平台或最终发布 |
| 数字人口播 | 发布中心 | 视频、封面、文案等 ArtifactVersion | 只创建/选择 PublishPackage 并导航到发布中心，最终点击保持人工 |

## 3. 不变量与边界

- 交接请求必须携带 `project_id`、`source_artifact_id`、`source_artifact_version_id`、目标应用版本和映射版本；来源版本创建后不可被上游热更新。
- 重复点击同一来源版本、同一目标应用版本和同一目标 draft 必须复用同一个 handoff 或 draft，不得重复创建运行或 Provider task。
- 来源版本被替换、归档或不属于当前项目时，目标工作台安全停手并提示“来源已更新/不可用”，不得静默切换到最新版本。
- 目标 draft 只展示带入内容，用户仍需确认输入后才可生成；交接本身不调用 LLM、RunningHub、媒体 Provider 或第三方平台。
- 发布中心只接收当前固定 `PublishPackage`；不接受旧版本、未完成包或本地绝对路径；最终发布点击必须为 0。
- 数字人图片/视频模式、stable 非默认策略、发布中心人工确认策略均保持不变。

## 4. 允许与禁止

允许修改：共享 ArtifactActions/VersionSwitcher/HandoffActions、跨应用 handoff API/fixture、四应用结果动作、目标 draft 来源展示、版本历史/下一步建议、对应测试和证据文档。

禁止修改：Provider/平台 selector 重写、模型配置与密钥管理、数字人默认模式、真实第三方平台登录/发布、最终发布自动点击、APP-WORKBENCH-7 灰度或收口。

## 5. 实现前验证项

1. 现有 ArtifactHandoff 已以 `source_artifact_version_id` 幂等且同项目校验。
2. 图文已有 `PublishPackage` 交付路径；需要将数字人结果接入同一 package 入口。
3. 目标工作台已支持 `initialSourceArtifactVersionId`，但标题→图文/数字人、文案→数字人和版本更新提示需统一为可复用动作。
4. 任何版本切换都只改变本次 draft 的来源指针，不修改已运行的 AppRun.input_payload。

## 6. Gate `PG-AW-G`

实现与复审需证明：来源版本固定可回读；目标 draft 显示带入内容；重复点击幂等；来源更新有提示；发布中心收到正确 package；最终发布点击为 0；独立六维复审在需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖和实际运行结果六项均无 P0/P1。
