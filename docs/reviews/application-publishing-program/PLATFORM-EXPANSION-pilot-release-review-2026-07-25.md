# PLATFORM-EXPANSION 三平台 Pilot 发布状态独立六维复审

- 日期：2026-07-25
- 审查线程：`/root/platform_expansion_foundation_reviewer`
- 变更请求：`CR-PLATFORM-PILOT-001`
- 结论：`passed_with_boundary`
- P0：0；P1：0；实质性 P2：0

## 复审范围

本次复审覆盖快手、视频号（`video_channel`）和小红书从 `unverified` 到与抖音同级的 `pilot`/人工发布前状态收口，以及一次性 SQLite migration、发布任务 gate、三平台既有真实 Playwright 证据、回滚和最终发布安全边界。未重复第三方上传、扫码或最终发布操作。

## 六维结论

1. **需求完整性**：三平台均登记为 `pilot`，允许受控创建 `PublishRun` 并停在人工确认前；默认 Publish V2 rollout、最终发布自动点击均保持关闭。
2. **逻辑正确性**：seed 与一次性 migration 只提升当前 `unverified` 状态；显式 revoke 后不会在重启时重复覆盖；账号、profile、登录态保持不变。缺失 `publish_platform_release` 行现在 fail-closed 投影为 `unverified`，并拒绝创建非抖音 `PublishRun`。
3. **边界情况**：快手标题不支持、话题文本回退、blob 封面；视频号/小红书无稳定远端媒体 ID、未保存草稿重启进入 `STATE_AMBIGUOUS` 且不重复上传；小红书话题与本地 blob 封面边界均保留。
4. **代码质量**：release state 事实源、repository projection、run gate 与 SQL seed/migration 职责清晰；无凭证、cookie、profile 路径进入证据或契约。
5. **测试覆盖**：缺失状态、promotion/revoke、三平台 pilot contract/fixture、run gate、FinalActionGuard 与历史 unverified 边界均有回归；定向与聚合测试见下方验证依据。
6. **实际运行结果**：复用三份既有一次性 headful Playwright live evidence；快手、视频号、小红书分别保持 `draft_ready`/有界阻塞事实、视频注入各 1 次、重启后上传 0、最终发布点击 0；没有重复第三方动作。

## 验证依据

- `uv run pytest -q tests/coord0_contract_test.py tests/publish_account_repository_test.py tests/publish_run_service_test.py tests/platform_expansion_release_boundary_test.py`：49 passed。
- 聚合发布/平台/桌面回归：187 passed，保留 12 个既有 Pydantic 弃用警告。
- Desktop 发布中心定向：3 files / 14 tests passed；`npm run build` passed。
- `uv run ruff check`、JSON parse、`git diff --check`：passed。
- 机器证据：[`qa/PLATFORM-EXPANSION-pilot-release-2026-07-25.json`](qa/PLATFORM-EXPANSION-pilot-release-2026-07-25.json)。
- 平台原始证据：[`qa/PG-M-kuaishou-live-gate-2026-07-22.json`](qa/PG-M-kuaishou-live-gate-2026-07-22.json)、[`qa/PG-M-shipinhao-live-gate-fix-2026-07-22.json`](qa/PG-M-shipinhao-live-gate-fix-2026-07-22.json)、[`qa/PG-M-xiaohongshu-live-gate-2026-07-22.json`](qa/PG-M-xiaohongshu-live-gate-2026-07-22.json)。

## 未完成事项

`pilot` 不等于平台正式发布或自动发布稳定性完成。最终发布仍需人工点击；平台特定字段/媒体持久化和重启恢复边界保持；默认 Publish V2 rollout、Windows 用户设备安装、PG-L 产品签字、真实双向 rollback/WebView SLA 仍不在本批范围。
