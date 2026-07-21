# PROGRAM-ROLLOUT implementation batch 7：API/UI 有界规模检查（2026-07-21）

## 结论

`implementation_pass_with_boundary` 候选，等待独立六维复审；本批不关闭 PG-L。

## 实现与范围

- 新增 `scripts/program_rollout_scale_api_ui_smoke.py`，在临时 SQLite 中创建 100 个项目和 1,000 个 `copywriting` 素材。
- 启动隔离 FastAPI 与 Vite 开发服务，通过真实 HTTP API 回读 100 个项目和 100 个项目的 1,000 个素材。
- 使用 Playwright headless 打开真实 React `/apps/digital-human-video` 路由 10 次；每次确认项目下拉 100 个项目、切换“已有文案”后来源素材下拉 10 个素材。
- 临时 API/UI 端口均释放；全局 `data/app_center.sqlite` 数量、mtime、size 前后不变，写入 0。
- 只发生本地 UI harness 的 20 次浏览器交互；没有第三方平台、账号、上传、发布或 provider 动作。

## 运行证据

证据文件：[`qa/PROGRAM-ROLLOUT-scale-api-ui-2026-07-21.json`](qa/PROGRAM-ROLLOUT-scale-api-ui-2026-07-21.json)

- `status=passed_local_bounded`
- 最新修复后独立复跑 API 项目列表 10 样本 p95：`11.593 ms`
- 最新修复后独立复跑 API 全量素材回读：`100` 个项目、`1,000` 个素材，`108.078 ms`
- 最新修复后独立复跑 UI 路由 10 样本 p95：`500.992 ms`
- UI 每次项目选项 `100`、素材选项 `10`
- `external_actions=0`、`final_publish_clicks=0`、`global_app_center_db_mutations=0`
- 对 `data/app_center.sqlite`、`data/desktop_tasks.sqlite`、`data/publishing/publishing.sqlite3` 和 `data/ip_broadcast_sessions` 做前后 hash/stat 快照：`user_data_unchanged=true`、`user_data_mutations=0`
- API/UI 端口经过进程退出后真实 socket bind 探针确认释放：均为 true
- 定向合同测试与既有 rollout 合同测试：`11 passed`
- 桌面生产构建：`npm run build` 通过（保留既有 bundle size warning）
- Ruff、`git diff --check`：通过

## 边界

这是本机临时 SQLite、FastAPI、Vite 和 headless React 的有界规模验证，不等价生产数据库压测、原生 Tauri WebView SLA、Windows 构建或云端多租户规模。PG-L 仍需真实 7 天观察窗、产品负责人签字、Windows follow-up、真实平台双向 rollback 和原生 WebView/生产环境证据。
