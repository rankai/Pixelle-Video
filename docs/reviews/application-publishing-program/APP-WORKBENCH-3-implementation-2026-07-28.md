# APP-WORKBENCH-3 文案与标题实现记录

## 结论

`APP-WORKBENCH-3` 已按边界完成，`PG-AW-D=passed_with_boundary`。

门店营销文案与爆款标题已经从通用 JSON 输入/结果升级为项目化工作台：左侧使用项目事实、本次卖点、目标、风格和来源，右侧使用可选择、可编辑、可反馈、可版本化的结构化结果卡；文案选中版本可通过固定来源版本的 typed handoff 进入标题应用。

## 已交付

### 服务端

- 新增受信 `StylePresetRegistry`，用户端只返回名称、说明和样例，prompt rules 与 forbidden patterns 不下发；
- 门店营销文案和爆款标题同时保留 1.0.0，并增加 1.1.0 输入 schema；
- 自定义风格参考只作为本次 Run 的表达参考，明确 `facts_imported=false`；
- Prompt 将项目事实、用户输入和受信风格规则分层，防止参考文案变成业务事实；
- 新增安全 `app_events`，支持选择、复制、编辑、喜欢、不喜欢和 handoff 事件，且不保存完整文案、模型密钥或浏览器数据；
- 新增用户编辑/选择结果的 ArtifactVersion 创建 API；
- typed handoff 使用 `mapping_version=2`，固定来源 `artifact_version_id` 并保持重复点击幂等；
- 修复历史数据库中 1.0.0 manifest 的兼容迁移和按 Run 固定应用版本执行的问题。

### 桌面端

- 新增共享 `StylePresetPicker`；
- 文案支持产品/服务、本次目标、卖点、营销利益点、风格样例和自定义参考；
- 标题支持固定文案版本、自定义主题、关键词、目标、数量和标题风格；
- 页面刷新或项目切换后恢复最近一次 v2 输入、风格和固定来源；
- 文案以版本卡展示创作角度、完整文案、字数、预计口播时长、缺失事实和风险；
- 标题以候选卡展示风格、字符数、规则检查和风险；
- 选择、复制、编辑、保存、喜欢、不喜欢和设为主结果均使用结构化操作；
- 结构化结果不再暴露裸 JSON 编辑器，未知旧 Artifact 才保留兼容编辑入口；
- 共享应用路由成为单一事实源，修复文案交给标题后错误返回应用中心的问题；
- 文案/标题桌面比例调整为约 36% / 64%，窄屏继续使用“配置 / 结果”Tab。

## 真实受控验证

建立项目 `project_b57435d1b41548eda1b3a64d5c69bf77`，固定 ContextSnapshot v2 `context_85e268fb14cd4ea1b013573424ad1baa`，使用当前系统设置中的同一套 Doubao/Ark Responses API 配置执行两个互不重复的目的性用例：

1. 门店营销文案 Run `run_24b3563bf7294a44b9caad98178069d6` 一次成功，生成 Artifact `artifact_5c297ab232a34647b5185e4f7eabe1b4`；
2. 选中第二版并生成 ArtifactVersion `artifact_version_53e670421fc74d689eb605b8608b5748`；
3. typed handoff `handoff_1d125eb4d63f40b3a65f0dd0b66fca9b` 固定该版本进入爆款标题，重复点击没有产生第二条 handoff；
4. 爆款标题 Run `run_541c38f2177645d8be3cb95e42155428` 一次成功，生成 5 条互不重复、16–17 字的候选；
5. 选中第二条并生成 `selected_title` Artifact `artifact_eba7e0512dbe4231bcc1e82251200d2d`、ArtifactVersion `artifact_version_0afe7bce836c45aeb0136e8dd12e2b8d`；
6. result.selected 事件正确绑定选中标题，而不是原始 `title_set`。

两次调用分别验证文案和标题，不是失败后的盲目重复；未调用 RunningHub 或任何发布平台。

## 验证结果

- 后端文案/标题与 API 定向：14 passed；
- 后端应用中心聚合：174 passed，12 个既有 Pydantic 弃用警告；
- Desktop：15 files / 93 passed；
- Desktop production build：passed；
- Ruff：passed；
- `git diff --check`：passed；
- 现有 `data/app_center.sqlite` 迁移：passed；
- 1440×900 真实左右工作台与 390×844 配置/结果切换：passed；
- 与用户提供参考图并排对照：输入集中在左、结果集中在右，结构一致但保留 Pixelle tokens、项目和 Artifact 语义。

完整证据见 [`qa/APP-WORKBENCH-3-implementation-2026-07-28.json`](qa/APP-WORKBENCH-3-implementation-2026-07-28.json)。

## 保留边界

- 文案和标题真实结果状态为 `needs_review`，不把模型输出自动视为已确认；
- 长期模型质量、更多行业 fixture 和风格偏好推荐不在本 Gate 内；
- `PIXELLE_APP_WORKBENCH_TEXT_V2` 与总工作台 flag 继续默认关闭；
- 抖音图文分页/重渲染留给 APP-WORKBENCH-4；
- 数字人交互重构留给 APP-WORKBENCH-5；
- RunningHub、发布平台和最终发布点击均为 0；
- PROGRAM-ROLLOUT/PG-L 的 Windows 实机、产品签字及 rollback/WebView SLA 保持暂停。
