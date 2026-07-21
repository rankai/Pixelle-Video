# AC-3 error matrix batch 4 — deterministic LLM boundary mapping

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0。

本批次只验证应用中心 LLM 端口的稳定错误边界，使用本地异常注入，不调用真实 provider，不做盲目重试。

已覆盖：

- 未配置模型：`LLM_CONFIGURATION_MISSING`，且 service 调用次数为 0。
- 鉴权失败（401/unauthorized）：`LLM_AUTH_FAILED`。
- 限流（429/rate limit）：`LLM_RATE_LIMITED`。
- provider 返回非法 JSON/schema/parse 错误：`STRUCTURED_OUTPUT_INVALID`。
- 其他 provider 故障：`LLM_PROVIDER_FAILED`。
- 超时：`LLM_TIMEOUT`，且单次调用不重试。
- provider 异常只保留稳定用户消息和异常类型诊断，不回传原始异常文本。

验证证据：

- `uv run pytest -q tests/app_center_error_matrix_test.py`：6 passed。
- `uv run ruff check tests/app_center_error_matrix_test.py`、`git diff --check`：通过。
- 独立复跑全量 `uv run pytest -q`：452 passed、12 条既有 warning。

边界：这是确定性的适配器错误矩阵，不等价于对真实 provider 逐一制造 401/429/超时；真实 provider 已完成一次成功 marketing-copy smoke 和一次真实文案→标题 handoff，但 PG-D 仍需完整 Gate 复核及必要的质量抽样。P2：可后续补 ConfigAppLLMPort 的 RUN_CANCELLED/实际等待超时直接断言，以及 AppRunner failed/no-Artifact/input-preserved 集成矩阵；不阻塞本批次。

终审结论：错误矩阵批次通过边界；PG-D 仍未关闭，不进入图文、数字人或发布平台。
