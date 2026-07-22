# AC-3 config hot-reload batch 11 — AppLLMPort dynamic model source

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0。

本批次补齐“配置变更后无需重启即可对下一次调用生效”的确定性证据。使用同一个已构造的 `ConfigAppLLMPort` 和本地 RecordingService，先后替换 `config_manager.config.llm.model`，不重建 port、不调用真实 provider。

验证内容：

- 第一次调用读取 `local-default:first-model`；配置变更后第二次调用读取 `local-default:second-model`。
- 两次 prompt 均不包含 API key，仍通过同一 AppLLMPort；没有第二模型事实源。
- 该测试证明现有动态配置读取边界，不宣称真实 provider 热切换、并发 reload 或桌面端重启行为已完成。

验证证据：

- `uv run pytest -q tests/app_center_error_matrix_test.py`：7 passed。
- 全量 `uv run pytest -q`：455 passed、12 条既有 warning。
- `uv run ruff check tests/app_center_error_matrix_test.py`、`git diff --check`：通过。

边界：PG-D 仍缺并发/恢复和运行期观测，以及目标用户完成度；不进入图文、数字人或发布平台。

终审结论：动态配置读取批次通过边界；PG-D 仍未完成。
