# APP-RESULT-HISTORY-2 文本记录块实施与可视化验证

- Stage：`APP-RESULT-HISTORY-2/TEXT_RECORD_BLOCKS`
- Gate：`PG-ARH-C`
- 日期：2026-07-30
- 结论：待独立六维复审

## 1. 实施范围

- 新增共享 `ProjectGenerationHistory`，默认展示“当前应用”，允许用户主动切换“全部成果”。
- 一次 `AppRun` 投影为一个带生成时间的记录块，不拆散成技术产物清单。
- 爆款标题在同一记录块中直接展示本次全部候选；门店营销文案直接显示正文，无需打开详情弹窗。
- 每个文本候选仅保留就近的“复制、编辑、采用”轻量操作；采用状态在当前会话内保持。
- 再次生成以新的记录块追加到顶部；旧记录通过游标加载。
- 切换项目、应用或结果范围时丢弃过期请求，不允许旧响应污染当前视图。
- 结果范围选择保存在 `sessionStorage`，但仍受当前项目边界约束。

## 2. 自动化验证

- 共享组件覆盖：完整候选、复制、编辑、采用、重复生成、当前应用/全部成果、空态、加载失败、游标加载、过期响应隔离。
- 工作台接线覆盖：爆款标题与门店营销文案均使用共享记录流，项目切换不会串数据。
- 桌面全量：20 个测试文件、148 个测试通过。
- 后端 Entry/投影定向：39 个测试通过。
- TypeScript + Vite production build 通过。
- Ruff check、Ruff format check、`git diff --check` 通过。
- 构建仅保留既有的大 chunk 警告，不影响本 Stage 功能正确性。

独立复审首轮发现并闭环 1 个 P1：编辑保存失败时原实现会关闭弹窗并丢失输入。现已让操作函数返回成功状态，仅在保存成功时关闭；失败或已有操作占用时保留弹窗和用户文字，并新增失败回归测试。

## 3. 真实可视化验证

| 场景 | 结果 | 证据 |
| --- | --- | --- |
| 1440×900 桌面视口 | 通过；单批次 5 条标题在一个记录块内直接可见，无技术字段 | `evidence/app-result-history-2026-07-30/title-history-1440.png` |
| 1280×720 桌面视口 | 通过；左右工作区不溢出，操作不形成按钮墙 | `evidence/app-result-history-2026-07-30/title-history-1280.png` |
| 900×720 窄桌面视口 | 通过；输入区与结果区改为纵向流，记录块完整 | `evidence/app-result-history-2026-07-30/title-history-900.png` |
| 900×720 全部成果 | 通过；混合应用记录保留来源标签，默认不增加当前应用密度 | `evidence/app-result-history-2026-07-30/title-history-900-results.png` |
| 390×844 CSS 移动宽度 | 通过；无水平滚动，候选与操作按单列重排 | `evidence/app-result-history-2026-07-30/title-history-390.png` |
| 等效 200% 缩放 | 通过；640 CSS px 宽度下 `scrollWidth <= innerWidth` | `evidence/app-result-history-2026-07-30/title-history-200pct.png` |
| 焦点态 | 通过；按钮有清晰可见的焦点轮廓 | `evidence/app-result-history-2026-07-30/title-keyboard-focus-copy.png` |

键盘语义检查：

- 单条标题内部 DOM/Tab 顺序固定为“复制 → 编辑 → 采用”。
- 三个控件均为原生 `button`、`tabIndex=0`、非禁用状态；已采用按钮切换为禁用状态。
- 当前 Browser CUA 对 `Tab` 未推进系统焦点，因此没有把自动化运行时限制误记为浏览器真实 Tab 证据；焦点可见性由真实聚焦截图与原生控件顺序共同验证。

## 4. 边界

- 本 Stage 只验收文本记录块，不把图文/数字人的媒体预览实现当作 `PG-ARH-C` 通过依据。
- 真实历史内容的营销质量属于产出质量评审，不由记录流 UI 通过自动推导。
- 未点击任何平台最终发布按钮，未触发 Provider。
