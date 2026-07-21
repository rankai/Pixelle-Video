# PUB-4 发布中心与生产链路整合 implementation batch 4（2026-07-21）

状态：`implementation_pass_with_boundary`；batch 4 Entry 已 `entry_passed_with_boundary`，并经独立六维复审。复审记录见 [`PUB-4-implementation-batch-4-review-2026-07-21.md`](PUB-4-implementation-batch-4-review-2026-07-21.md)；PG-J 尚未关闭。

## 实现内容

- `PublishCenterView` 在适配器/预检数据不可用时显示安全回退入口，回到旧生产工作区继续复制文案、预览或下载素材；不显示本地路径、cookie、token 或“已发布”状态。
- `HashRouter` 增加 canonical publish handoff 的 refresh/remount/restart simulation 测试，验证 package/artifact query 持久化和恢复，不创建新的 package/run。
- Publish V2 resolver 增加真实 TestClient runtime 验证：唯一候选 200，失效 409 `PUBLISH_PACKAGE_STALE`，多候选 409 `PUBLISH_PACKAGE_AMBIGUOUS`。
- 生成本地有界 QA JSON，明确所有 browser/authorization/upload/run/final_publish 外部动作计数为 0。

## 定向验证

- `uv run pytest -q tests/publish_v2_api_test.py tests/publish_integration_entry_contract_test.py tests/publish_integration_batch_2_entry_contract_test.py tests/publish_integration_batch_3_entry_contract_test.py tests/publish_integration_batch_4_entry_contract_test.py tests/publish_batch3_implementation_test.py tests/publish_batch4_implementation_test.py`：**20 passed**、12 个既有 Pydantic 弃用警告；
- `npm run test -- --run`：8 files / 45 tests passed；
- `npm run build`：passed，保留既有 chunk size warning；
- `uv run ruff check tests/publish_v2_api_test.py`、`git diff --check`：passed；
- QA：[`PUB-4-batch-4-local-runtime-2026-07-21.json`](qa/PUB-4-batch-4-local-runtime-2026-07-21.json)。
- 外部动作：0；未打开浏览器、未扫码/授权、未上传、未创建 PublishRun、未最终发布。

## 独立六维复审

见 [`PUB-4-implementation-batch-4-review-2026-07-21.md`](PUB-4-implementation-batch-4-review-2026-07-21.md)，结论 `implementation_pass_with_boundary`，P0/P1=0。

## 后置边界

本批只证明本地 AppShell remount/restart simulation、TestClient resolver 和安全 fallback。真实打包 Tauri restart/leave-return、跨进程 CAS/锁清理、真实平台 adapter 与最终发布仍不在本批宣称范围；完成后仍需独立六维复审，不关闭 PG-J。
