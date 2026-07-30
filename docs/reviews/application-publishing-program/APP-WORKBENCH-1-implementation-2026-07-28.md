# APP-WORKBENCH-1 共享左右工作台实现

- Stage：`APP-WORKBENCH-1`
- Gate：`PG-AW-B`
- 结论：`implementation_pass_with_boundary`
- 日期：2026-07-28

## 1. 实现结果

新增共享 `AppWorkbenchShell`，并以默认关闭的 `VITE_APP_WORKBENCH_V2` 接入门店营销文案、爆款标题、抖音图文和数字人口播四个路由。

桌面宽度下：

- 左侧固定为项目、来源和本次输入；
- 右侧固定为当前应用运行与结果；
- 结果头统一显示 `等待开始/正在处理/需要处理/等待确认/已保存`；
- 不知道真实进度时不显示估算百分比；
- 主操作区保持在输入区域，结果与输入不再上下串行堆叠。

窄窗口下：

- 900 与 390 宽度降级为“创作配置/生成结果”两个胶囊 Tab；
- 默认显示输入，点击或使用左右方向键、Home/End 可切换结果；
- 非活动面板保留状态但不显示，不会卸载运行状态；
- 复用应用中心的 `--app-*` tokens，没有新增独立色板。

## 2. 兼容与回滚

- `VITE_APP_WORKBENCH_V2` 默认 `false`。
- 同时接受机器契约别名 `PIXELLE_APP_WORKBENCH_V2`；两者冲突时 fail closed。
- flag 关闭后四应用继续渲染原单列容器。
- 本阶段没有更改 AppRun、Artifact、ContextSnapshot、API payload 或 executor。
- 新工作台只在结果区展示当前应用运行，避免其他应用运行与当前状态标签矛盾；旧容器继续保持原运行列表行为。
- 运行中任务、历史结果和本地文件不因 UI flag 切换被取消或删除。

## 3. 视觉与操作验证

Codex 内置浏览器对四路由执行 1440×900、1280×800、900×760、390×844 共 16 个最终状态截图，并额外保存 900 宽文案结果 Tab 与 390 宽数字人结果 Tab：

- 四路由均出现且只出现一个共享工作台壳层；
- 1440/1280 输入和结果同时可见；
- 900/390 显示 Tab，默认输入可见、结果隐藏；
- 切换结果后输入隐藏、结果可见，`aria-selected` 正确；
- 未发现横向滚动；
- disabled 主按钮统一为灰底 `rgb(238, 241, 246)`、灰字 `rgb(138, 148, 166)`，文字清楚可见；
- 当前基线与最终实现已在相同 1440×900 视口并排复核。

截图、像素和 SHA-256 见 [`qa/APP-WORKBENCH-1-implementation-2026-07-28.json`](qa/APP-WORKBENCH-1-implementation-2026-07-28.json)。

## 4. 测试

- Desktop Vitest：13 files / 82 passed
- 工作台定向 Vitest：4 files / 38 passed
- TypeScript + Vite production build：passed
- `git diff --check`：passed
- 真实 LLM/RunningHub/平台变更动作：0
- 最终发布点击：0

## 5. 边界

本阶段完成的是共享壳层，不代表项目上下文 v2、风格库、四应用专属输入/结果或跨应用交付已经完成。四应用仍复用现有 API 和 executor；这些领域能力必须按 APP-WORKBENCH-2 至 APP-WORKBENCH-6 串行实现。
