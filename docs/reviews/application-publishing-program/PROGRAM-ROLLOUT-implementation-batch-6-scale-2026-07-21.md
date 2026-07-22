# PROGRAM-ROLLOUT implementation batch 6：有界规模检查（2026-07-21）

## 批次结论

当前结论为 `implementation_pass_with_boundary`；独立六维复审已通过，P0=0、P1=0、实质性 P2=0；本批不关闭 PG-L。

## 实现与范围

- 新增 `scripts/program_rollout_scale_smoke.py`，只使用临时 SQLite 数据库和现有 `AppCenterRepository`。
- 通过仓储公开操作创建 100 个 active `ContentProject`，每个创建 10 个 active `Artifact`，合计 1,000 个素材。
- 通过 `list_projects()` 与逐项目 `list_artifacts()` 回读，并用只读 SQL 计数交叉核对。
- 未启动 API、sidecar、浏览器、WebView 或任何第三方平台；未触碰用户现有应用中心数据库。
- 新增 `tests/program_rollout_scale_contract_test.py`，覆盖本地边界、目标数量和完整回读分布。

## 运行证据

证据文件：[`qa/PROGRAM-ROLLOUT-scale-2026-07-21.json`](qa/PROGRAM-ROLLOUT-scale-2026-07-21.json)；独立复审：[`PROGRAM-ROLLOUT-implementation-batch-6-scale-review-2026-07-21.md`](PROGRAM-ROLLOUT-implementation-batch-6-scale-review-2026-07-21.md)

- `status=passed_local_bounded`
- `projects_created/read=100/100`
- `artifacts_created/read=1000/1000`
- 每个项目素材数均为 10；active SQL 行数为 100/1000
- 最新独立复跑创建耗时 `1058.107 ms`，回读耗时 `59.423 ms`
- `api_started=false`、`browser_actions=0`、`external_actions=0`
- 独立复跑前后全局 `data/app_center.sqlite` 的 projects/artifacts 数量、mtime 与 size 不变；用户数据库未写入。
- 定向测试：`2 passed`
- 应用中心聚合测试：`28 passed`（含 4 个既有 Pydantic warning）
- 桌面生产构建：`npm run build` 通过
- Ruff：通过

## 边界与下一步

本批是本机临时 SQLite 的有界正确性与数量检查，不等价于生产数据库压测、云端多租户规模、原生 WebView 性能或 Windows 构建。PG-L 仍需真实 7 天观察窗、产品负责人签字、Windows 构建（或正式 deferred 记录）、真实平台双向回滚与真实 WebView SLA 证据。
