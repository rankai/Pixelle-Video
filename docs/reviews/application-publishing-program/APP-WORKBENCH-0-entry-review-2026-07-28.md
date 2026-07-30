# APP-WORKBENCH-0 六维 Entry 自审

- 审查对象：`CR-APP-WORKBENCH-001` 的 Entry 契约、fixture、基线、测试和证据
- 审查方式：只读逐项复核 + 定向自动化回归
- 结论：`passed_with_boundary`
- 严重问题：P0 `0`、P1 `0`
- 已修复问题：P2 `1`

## 1. 需求完整性

通过。Entry 已覆盖四个首期应用、项目长期上下文、单次运行输入、风格预设/自定义参考、结果状态、ArtifactVersion、typed handoff、feature flag、兼容、迁移、回滚和 12 张真实页面基线。

边界清楚：本阶段没有把 UI、Provider、数据库迁移或真实平台动作误报为完成。

## 2. 逻辑正确性

通过。

- 项目事实、运行输入、结果版本和跨应用来源各有唯一所有者。
- ContextSnapshot、AppRun input、ArtifactVersion 和 style version 都采用不可变或追加语义。
- style preset 和 custom reference 互斥；自定义参考不能导入事实。
- 图文和数字人必须固定上游 ArtifactVersion，不读取“最新内容”造成漂移。
- 源版本更新只通知，不会热更新正在执行或已完成的下游运行。
- 失败状态不允许伪 Artifact，未知任务进度不允许伪百分比。

## 3. 边界情况

通过。fixture/test 覆盖未知字段、凭证/Provider 越权、未固定资产 revision、不支持 schema、风格来源冲突、缺失上游 Artifact、数字人不支持工作台风格覆盖、跨项目 handoff、源版本更新和 feature flag 默认关闭。

快速切换项目和重复提交分别由 stale-response guard 与幂等创建约束冻结，避免旧请求污染当前项目或重复消耗 Provider。

## 4. 代码与契约质量

通过。Schema 使用 JSON Schema 2020-12，`additionalProperties=false` 作为 fail-closed 默认；fixture 与 machine-readable contract 相互引用，测试直接验证 schema、关键语义和文件哈希。

已修复 P2：内置浏览器实际导出 JPEG，但初版清单字段名为 `png_pixels`。已统一为 `.jpg`、JPEG magic/format 校验和中性 `image_pixels` 字段，避免证据类型与命名不一致。

## 5. 测试覆盖

通过。

- Entry contract：10 passed
- 应用中心/文案/标题/图文/数字人相关回归：83 passed
- Ruff：passed
- 8 个 JSON：parsed
- diff check：passed

12 个 Pydantic 弃用警告来自既有代码，不是本 Entry 引入；后续可单列技术债，不阻塞 PG-AW-A。

## 6. 实际运行与视觉基线

通过 Entry 范围内的实际运行验证。Codex 内置浏览器打开当前四应用真实路由，分别在 1440×900、1280×800、900×760 保存基线；DOM 视口、应用身份、后端连接和目录可用性均完成回读。截图本身未被解释为新版 UI 验收，它们只作为 APP-WORKBENCH-1 以后同视口前后对照的基线。

## 7. 结论

`PG-AW-A` 可关闭为 `passed_with_boundary`，允许 `current_substage` 切换到 `APP-WORKBENCH-1`。下一阶段只实现共享左右工作台壳层、统一状态区和窄屏模式，必须继续复用现有 tokens、路由、数据和执行器；不得提前实现四应用业务 v2、调用真实 Provider 或改变最终发布人工确认边界。
