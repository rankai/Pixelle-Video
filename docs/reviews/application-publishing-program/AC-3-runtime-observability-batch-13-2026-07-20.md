# AC-3 runtime observability batch 13 — Attempt duration metadata

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0。

并发/恢复验证发现 `RunAttempt.duration_ms` 领域字段此前未被 AppRunner 写入。本批次补齐窄范围运行期观测：AppRunner 在成功、结构化失败和取消竞速路径上，以 monotonic clock 计算并持久化非负 `duration_ms`；started/completed timestamps、model_ref、provider_class 保持原有记录。

验证内容：

- 两个并发 structured AppRun 的 Attempt 均有 started_at、completed_at、非空 duration_ms、model_ref/provider_class。
- 失败后恢复的两次 Attempt 均保持状态、provider metadata 和 duration 字段；失败阶段无产物，恢复阶段有版本化产物。
- 未注册 executor、AppLLMPort 错误和通用异常路径复用同一耗时计算，不改变稳定错误码。

验证证据：

- 定向并发/恢复/失败测试 3 passed。
- 全量 `uv run pytest -q`：457 passed、12 条既有 warning。
- `uv run ruff check pixelle_video/app_center/runner.py tests/app_center_core_test.py`、`git diff --check`：通过。

边界：本批次只补 AppRunner 进程内 Attempt 观测，不等价真实 provider latency/usage、崩溃重启后的 duration 恢复、集中式 metrics/tracing 或用户完成度；PG-D 仍未完成。

终审结论：Attempt duration 观测批次通过边界；PG-D 仍未完成。
