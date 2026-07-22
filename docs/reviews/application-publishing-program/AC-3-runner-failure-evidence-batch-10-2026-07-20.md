# AC-3 runner failure evidence batch 10 — structured error persistence

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0。

本批次补齐 PG-D 入口契约要求中“结构化输出失败后 AppRun/Attempt 保留失败证据、无 ArtifactVersion、输入不丢失”的确定性集成覆盖。使用 FakeLLMPort 注入空 variants，不调用真实 provider。

验证内容：

- `AppRunner` 将最终 `STRUCTURED_OUTPUT_INVALID` 写入 AppRun 和 RunAttempt。
- 代码拥有的 `MARKETING_VARIANT_COUNT` 进入 `diagnostic`，未写入模型/provider 原文。
- 失败后 `output_artifact_ids` 为空，项目下没有 ArtifactVersion/Artifact，原始 input_payload 完整保留。
- 既有唯一 repair 仍由结构化 executor 执行，不扩展为无限重试。

验证证据：

- 新增 `test_structured_executor_failure_preserves_input_and_writes_no_artifact`；定向 core/structured/fixture/error：50 passed。
- 全量 `uv run pytest -q`：454 passed、12 条既有 warning。
- `uv run ruff check ...`、`git diff --check`：通过。
- 集成断言补齐 Attempt 数量/state、唯一 repair 请求数和 error_message 安全性；单测复跑通过。

边界：本批次是 deterministic runner integration，不等价于真实 provider 失败现场、并发恢复或运行期观测；PG-D 仍未完成。

终审结论：Runner 失败持久化批次通过边界；PG-D 仍未完成。
