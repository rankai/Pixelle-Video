# APP-WORKBENCH-3 六维自审

## 审查结论

结论：`implementation_pass_with_boundary`。

- P0：0
- P1：0
- 已修复 P2：6
- 非阻断边界：真实结果仍需用户审核；长期风格质量与行业覆盖不属于本 Gate

## 1. 需求完整性

通过。StylePresetRegistry、文案/标题输入 v2、风格/自定义参考、结构化结果卡、编辑/选择/反馈、ArtifactVersion 和文案到标题 typed handoff 均已交付。项目仍是业务事实源，模型管理仍是唯一 Provider 配置源。

## 2. 逻辑正确性

通过。受信风格规则与用户输入分层；自定义参考不导入事实；Run 固定应用版本和 ContextSnapshot；选择结果产生新 ArtifactVersion；handoff 固定来源版本并幂等；AppEvent 不改变 Artifact。

## 3. 边界情况

通过。自动化覆盖无效 style、风格跨应用、非法自定义参考、缺失事实、标题数量/长度/去重/禁用词、事件 kind/payload、跨项目编辑、重复 handoff 和历史 v1 manifest 兼容。真实页面验证了刷新恢复和窄屏结果切换。

## 4. 代码质量

通过。风格定义集中于 `style_presets.py`，应用路由集中于 `applicationRoutes.ts`，结构化 v2 归一化集中于 `structured_apps.py`；没有在前端复制 prompt 或 Provider key。后端聚合、前端全量、build、Ruff 和 diff check 均通过。

## 5. 用户操作体验

通过。桌面保持约 36/64 左右布局；输入和结果同时可见；技术 Run/Artifact ID 不作为默认结果文案；缺失事实和风险显示具体原因；结构化结果不再要求用户编辑 JSON；窄屏可以在配置和真实结果之间切换。参考图与实装图已并排检查。

## 6. 实际运行结果

通过。当前系统设置中的 Doubao/Ark Responses API 分别完成一次文案和一次标题的目的性调用；文案三版、标题五条、选中版本、事件、刷新恢复和 typed handoff 均留下真实 SQLite/API/浏览器证据。RunningHub、发布平台和最终发布点击为 0。

## 审查中发现并修复的问题

1. 旧数据库 1.0.0 manifest 曾因 seed 内容变化触发 checksum 漂移，已保持历史 manifest 字节兼容并追加 1.1.0；
2. 执行路由曾用 Registry 默认版本比较 Run，导致 1.1.0 运行被误判，已按 `run.app_version` 解析；
3. 文案 handoff 曾跳回 `/apps`，已建立应用路由单一事实源并跳到 `/apps/viral-titles`；
4. 选中标题事件曾绑定原始 `title_set`，已改为绑定新的 `selected_title` ArtifactVersion；
5. 结构化结果曾暴露裸 JSON 与 Artifact ID，已改为面向用户的结构化保存和结果文案；
6. 页面刷新后卖点、关键词、风格和固定来源曾丢失，已按最近一次 v2 Run 恢复。

## Gate 建议

允许关闭 `PG-AW-D` 并进入 `APP-WORKBENCH-4`。下一阶段只允许优化抖音图文的来源、素材、风格、页数、模板、分页计划、局部编辑/重渲染、下载和发布中心 handoff；不得提前重构数字人工作台，不得打开发布平台。
