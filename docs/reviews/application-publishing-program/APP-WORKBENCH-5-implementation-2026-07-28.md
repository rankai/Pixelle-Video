# APP-WORKBENCH-5 实施记录（数字人口播工作台体验闭环）

日期：2026-07-28
阶段：`APP-WORKBENCH-5`
状态：实现完成，等待独立六维复审

## 本批次交付

1. **失败安全边界**
   - V2 运行在 `failed` 状态不能直接 execute。
   - Provider 与 local 隔离执行器都要求先提交根因绑定的 retry plan；单次重试仍受次数上限约束。
   - 前端失败态只显示受控重试入口，不再显示可绕过计划的“开始生成”。
2. **双模式工作台**
   - 保留图片数字人为默认模式，视频数字人为稳定但非默认模式。
   - 运行状态区增加六步状态：项目/来源、素材、TTS、数字人、字幕与后期、结果交付。
   - 未确认 pending 提交期间切换模式会 fail-closed；必须恢复、清理或新建运行后才能切换。
3. **结果交付**
   - 结果面板展示最终视频、封面、发布文案、口播稿四类 Artifact。
   - 增加封面预览、发布文案/口播稿可读内容和复制入口。
   - legacy artifact endpoint 能解析 V2 repository artifact ID，避免封面、文案和口播稿下载 404。
4. **输入与恢复**
   - 卖点字段随本次运行固定并写入 session 审计上下文。
   - 增加“新建运行”，保留历史 Artifact，同时清理本地运行/pending 指针。
   - 本地指针恢复补齐字幕开关和卖点字段。
5. **布局与视觉**
   - 继续复用应用工作台现有 tokens 和双栏组件。
   - 宽屏容器由 1640 调整为 `min(calc(100% - 48px), 1840px)`，保持最小 24px 边距，减少大屏两侧空白；移动端断点与双栏比例保持不变。

## 验证记录

- Desktop：`npm test -- --run` → 15 files / 95 tests passed。
- Desktop：`npm run build` → passed；仅有既有 chunk size warning。
- Backend：IP broadcast API/adapter、digital-human dual-mode recovery/quality/server → 81 tests passed；新增 artifact-ID endpoint、failed retry-plan guard、selling-points persistence 覆盖后共 27 个新增相关测试通过；保留 12 条既有 Pydantic deprecation warnings。
- Static quality：`uv run ruff check ...`、`git diff --check` → passed。
- Browser smoke（in-app browser，1280px viewport）：应用工作台可加载；DOM 观测 `overflow=false`，shell width 937px、x=276px、right=1213px；两栏和结果区可见，未出现横向滚动。

## 明确边界

- 本批次不自动点击任何平台的最终发布按钮。
- V2 已取消运行不提供“重试”按钮，统一通过“新建运行”重建；这是为了避免取消时仍存在的 Provider 任务被旧入口复用。
- Provider 真实 RunningHub 任务不在本批次重复触发；真实平台调用仍需受控开关和人工确认。
- 视觉质量（字幕、抠像、口型、背景）沿用已验证的 `readable_v2` 与双模式质量门，不把“结果已生成”误标为平台发布完成。

## 下一步 Gate

等待独立审查线程从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六维复验；修复清单闭环后，才更新 `PG-AW-F` 并进入下一台账阶段。
