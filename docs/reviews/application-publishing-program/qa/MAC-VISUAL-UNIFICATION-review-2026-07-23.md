# Mac 发布中心 V2 视觉统一独立复审（2026-07-23）

## 结论

`implementation_pass_with_boundary`；P0=0、P1=0、实质性 P2=0。

## 六维验证

- 需求完整性：按应用中心基准覆盖页面容器、标题层级、Tab、Tag、按钮、状态卡片和账号分组卡片。
- 逻辑正确性：本批仅新增视觉 class/CSS；人工确认边界与最终发布 Guard 保持不变。
- 边界情况：1280×800、1440×900 均无溢出或错位；未验证平台仍保持回退提示。
- 代码质量：`npm run build`、`git diff --check` 通过；仅有既有 chunk size warning。
- 测试覆盖：Vitest 10 files/55 tests、Coord-0 18 passed、JSON parse passed。
- 实际运行：发布运行/发布账号两 Tab 可切换；四张截图存在且 SHA-256 与 QA JSON 匹配。

## 用户反馈修正

复验发现选中 Tab 同时叠加了浏览器默认 focus outline，造成“双层边框”观感；已移除发布中心 Tab 的默认 outline，并重新生成四张截图与 SHA-256。修正后选中态仅保留一层紫色胶囊边框，与应用中心示例一致。

## 保留边界

未执行 Tauri 打包视觉验收；视频号空平台入口、旧版账号管理页和口播工作台不在本批范围。工作树中先前 PUB-2 的 `createPublishRunV2/startRun` 逻辑与本批纯视觉变更并存，提交时应拆分基线，避免证据歧义。
