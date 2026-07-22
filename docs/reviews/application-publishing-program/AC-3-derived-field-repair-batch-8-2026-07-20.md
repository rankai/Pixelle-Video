# AC-3 derived-field repair batch 8 — local deterministic recalculation

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0。

针对 batch 7 中 beauty 两次出现的 `MARKETING_DERIVED_FIELDS`，增加窄范围本地修复：结构化响应已通过 Pydantic 解析后，由代码从可信 `full_text` 重算 Unicode code-point `word_count` 与 `ceil(word_count/4)` 的 `estimated_seconds`，再交给原 validator。底层 `validate_marketing_output` 直接调用时仍拒绝错误派生值，保持契约测试对错误输出的 fail-closed 语义。

已实现：

- `normalize_marketing_derived_fields()` 只修改派生计数，不修改 hook/body/cta、事实、风险或标题内容。
- 若 `full_text` 不包含三段组成字段，原有 `MARKETING_FULL_TEXT` 校验仍失败；本地修复不是放宽内容/事实边界。
- 不增加 provider 重试，不新增模型配置源，不改变稳定错误码。

验证证据：

- 新增 provider 错误派生值的本地重算回归；定向结构化/fixture/error matrix：26 passed。
- 全量 `uv run pytest -q`：453 passed、12 条既有 warning。
- `uv run ruff check ...`、`git diff --check`：通过。

边界：尚未重新调用 beauty provider。复核通过后，最多对 beauty 做一次有明确目的的最终验证；若仍失败则停止重试并保留边界，不关闭 PG-D。

终审结论：修复批次通过边界；允许一次 beauty 最终验证，PG-D 仍未完成。
