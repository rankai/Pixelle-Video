# PUB-4 / PG-J closure implementation（2026-07-21）

状态：`implementation_pass_with_boundary`；PG-J closure Entry 已 `entry_passed_with_boundary`，独立 implementation review 已通过，等待主线程更新 PG-J Gate。

## 本轮交付

- 复用并重新核对本地 Tauri/sidecar 两轮启动、health、停止和端口释放证据；
- 以 canonical `#/publish?package_id=...` 做 leave-return 与 remount/restart handoff 证据；
- 以 `ADAPTER_UNAVAILABLE` 模拟 adapter failure，证明旧生产工作区仍提供复制/预览/下载且不暴露路径；
- 运行 resolver unique/stale/ambiguous TestClient 三态；
- 归档无假发布状态、外部动作计数和脱敏 QA/log。

## 本轮结果

- 重新构建 sidecar 后，真实本地 `npm run tauri:dev` 完成两轮启动/停止；每轮均观察到 Tauri 进程、sidecar 进程和 `/health`=200，停止后 8100 端口关闭。重建前的旧 sidecar 因历史二进制不含 `waiting_for_login` 枚举而退出，未删除或重写任务数据库；重建后使用同一现有数据库启动通过。
- AppShell 的 refresh/remount/restart 与 leave-return 测试保留同一 canonical `package_id`/`artifact_id`/`run_id`，并验证从通用 `/publish` 菜单返回时恢复最后 handoff，不持久化本地绝对路径；该证据是确定性 WebView 状态模拟，不冒充原生 WebView 黑盒录制。
- 旧生产工作区在 `ADAPTER_UNAVAILABLE` 下复制、预览和下载均有可用断言；PublishWorkspace 测试断言视频/封面 DOM 使用解析出的 blob URL，PublishCenter/PublishWorkspace 测试均断言不出现“已发布”假状态。
- resolver TestClient 三态为 unique=200、stale=409 `PUBLISH_PACKAGE_STALE`、ambiguous=409 `PUBLISH_PACKAGE_AMBIGUOUS`；所有外部动作计数为 0。

完整 QA：[`PUB-4-PG-J-closure-2026-07-21.json`](qa/PUB-4-PG-J-closure-2026-07-21.json)。

## 定向验证

- `uv run pytest -q tests/publish_v2_api_test.py tests/publish_integration_entry_contract_test.py tests/publish_integration_batch_2_entry_contract_test.py tests/publish_integration_batch_3_entry_contract_test.py tests/publish_integration_batch_4_entry_contract_test.py tests/publish_batch3_implementation_test.py tests/publish_batch4_implementation_test.py tests/publish_pg_j_closure_entry_contract_test.py`：22 passed，12 个既有 Pydantic 弃用警告；
- `uv run pytest -q tests/desktop_build_config_test.py tests/desktop_sidecar_test.py tests/publish_pg_j_closure_entry_contract_test.py tests/publish_batch4_implementation_test.py`：19 passed；
- `npm run test -- --run`：8 files / 45 tests passed；
- `npm run build`：passed，保留既有 chunk size warning；
- `uv run ruff check ...` 与 `git diff --check`：passed；
- `uv run python desktop/scripts/build_sidecar.py`：passed，重建 arm64 sidecar。

## 硬边界

- 不打开抖音或其他平台，不扫码、授权、上传、创建真实 PublishRun 或最终发布；
- 不宣称跨进程 CAS/锁清理，不删除 profile/session，不做破坏性迁移；
- 本地 Tauri/sidecar 证据只证明桌面生命周期与 sidecar 健康，不等价真实平台发布成功；原生 WebView 黑盒 handoff、跨进程 CAS/锁清理、真实平台动作和最终人工发布仍明确后置为 P2/后续证据增强。

## 待复审

独立复审：[`PUB-4-PG-J-closure-review-2026-07-21.md`](PUB-4-PG-J-closure-review-2026-07-21.md)，结论 `implementation_pass_with_boundary`、P0/P1=0；主线程可据此更新 PG-J Gate，但不得把边界证据升级为原生 WebView 黑盒或真实平台成功。
