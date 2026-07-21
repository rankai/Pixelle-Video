# AC-3 concurrency/recovery batch 12 — structured AppRun isolation

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0。

本批次补齐确定性并发与恢复证据，使用 FakeLLMPort 和临时 SQLite，不调用真实 provider。

验证内容：

- 两个同项目 `builtin.marketing-copy` AppRun 并发执行，各自进入 `needs_review`，各有一个 Artifact，FakeLLMPort 请求数为 2，Attempt 状态不串线。
- 一个 AppRun 在唯一 repair 后最终 `STRUCTURED_OUTPUT_INVALID`；再次调用 `AppRunner.run` 触发既有失败恢复路径，下一次有效响应后进入 `needs_review`，两次 Attempt 状态为 `[failed, needs_review]`，只有一个成功 Artifact，provider 请求总数为 3。
- 并发/恢复均保持同一项目输入和版本隔离；没有修改发布平台或外部账户状态。

验证证据：

- 新增两个 core tests：并发隔离与失败后恢复，均通过。
- `uv run pytest -q tests/app_center_core_test.py::test_structured_app_runs_are_isolated_under_concurrent_execution tests/app_center_core_test.py::test_structured_app_run_recovers_after_terminal_invalid_output`：2 passed。
- 全量 `uv run pytest -q`：457 passed、12 条既有 warning。
- 复核补充断言 Artifact `source_app_run_id`、版本 schema/content、失败阶段无产物和 input 保留；定向复跑通过。
- `uv run ruff check tests/app_center_core_test.py`、`git diff --check`：通过。

边界：这是 fake/deterministic AppRunner 运行时证据，不等价真实 provider 并发限流、进程崩溃恢复或线上观测；用户完成度与运行期观测仍待后续 Gate 证据，PG-D 不提前关闭。

终审结论：并发/恢复批次通过边界；PG-D 仍未完成。
