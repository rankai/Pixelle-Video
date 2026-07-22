# ADR-010 桌面 AppShell 与 HashRouter

- 状态：accepted for COORD-0
- 决策：AppShell 统一导航，应用中心使用 `/#/apps`，项目使用 `/#/projects/:projectId`，发布使用唯一 `/#/publish`；业务页面不再在 `StudioApp.tsx` 追加分支。
- 迁移：APP-SHELL 先增加路由外壳和旧入口兼容映射，再迁移页面；未迁移页面保留可返回路径。
- 安全：路由只负责接线，不直接执行 LLM、媒体或浏览器动作；feature flag 缺省关闭。
- 回滚：关闭新路由 flags，保留旧入口和 URL 映射。
