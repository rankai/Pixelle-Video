# COORD-0 前端测试工具决策

- 决策状态：`landed_for_pg_b`
- COORD-0 阶段不引入依赖；APP-SHELL/PG-B 已按本决策落地并修改 `desktop/package.json` 与 lockfile。
- APP-SHELL（PG-B）进入前引入 Vitest + React Testing Library，并在同一 Stage 提交最小脚本 `npm run test -- --run`、一个路由 smoke 和一个 registry 渲染 smoke。
- `npm run build` 和 `npm run test -- --run` 均为 PG-B 桌面端门禁；在依赖落地前的 `not_available` 仅是 COORD-0 历史状态，不能覆盖本阶段已通过的运行记录。
- 依赖引入的回滚：删除 Vitest/RTL 依赖、配置和新增测试文件，不触碰 Python API 或旧发布链路；构建门禁仍须通过。
- 选择理由：Vitest 与现有 Vite/TypeScript 构建一致，RTL 适合验证 HashRouter、feature flag 默认关闭和应用卡片 readiness；不在 COORD-0 扩大变更面。

## 运行记录

| 命令 | 当前状态 | 证据 |
| --- | --- | --- |
| `cd desktop && npm run build` | `passed` | COORD-0 baseline |
| `cd desktop && npm run test -- --run` | `passed` | Vitest 4.1.10；2 个测试文件、3 个测试通过：HashRouter route smoke + ApplicationCenter registry rendering/readiness smoke |
