# AC-3 failure diagnostics batch 6 — safe structured validator reasons

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0。

本批次处理真实质量抽样暴露的 P2：结构化输出失败后只记录 `STRUCTURED_OUTPUT_INVALID` 不足以审计失败类别。新增的诊断值均由代码拥有、无模型原文和无 provider 异常文本，不改变对外稳定错误码。

已覆盖的安全诊断码包括：

- marketing：`MARKETING_VARIANT_COUNT`、`MARKETING_VARIANT_ANGLES`、`MARKETING_FULL_TEXT`、`MARKETING_DERIVED_FIELDS`、`MARKETING_BANNED_TERM`、`UNSUPPORTED_PRICE_FACT`、`UNSUPPORTED_ADDRESS_FACT` 等。
- titles：`TITLE_CANDIDATE_COUNT`、`TITLE_OBJECTIVE`、`TITLE_LENGTH`、`TITLE_BANNED_MATCHES`、`TITLE_BANNED_TERM`、`TITLE_DUPLICATE`、`TITLE_DEDUP_RATIO` 等。

验证证据：

- `uv run pytest -q tests/app_center_structured_apps_test.py tests/app_center_fixture_quality_test.py tests/app_center_error_matrix_test.py`：25 passed。
- 已断言 variant 数量、价格/地址事实和标题重复的安全诊断码；`uv run ruff check ...`、`git diff --check`：通过。
- 独立复跑全量 `uv run pytest -q`：452 passed、12 条既有 warning。

边界：本批次只增加可审计的代码级诊断标签；尚未重新调用 beauty/retail provider。复核通过后，最多各对两个失败类别执行一次有明确目的的复验，并记录诊断码；PG-D 仍未完成。

终审结论：诊断批次通过边界；允许按计划对 beauty/retail 各复验一次，PG-D 仍未完成。
