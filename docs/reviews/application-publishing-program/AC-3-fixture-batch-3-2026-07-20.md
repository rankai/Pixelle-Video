# AC-3 fixture batch 3 — six-category deterministic quality baseline

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P1=0。

已完成：

- 加载 `app-text-entry.json` 中火锅、美容、民宿、洗衣店、培训、零售六类门店 fixture。
- 每类 fixture 均通过 marketing-copy 输入 schema、共享事实白名单和结构化输出 validator；验证 `validation_facts.input.store_type` 绑定类别。
- 补齐标题重复归一化和禁用词两个负例，均在唯一 repair 后稳定返回 `STRUCTURED_OUTPUT_INVALID`。

验证证据：

- `uv run pytest -q tests/app_center_fixture_quality_test.py tests/app_center_structured_apps_test.py`：19 passed。
- `uv run ruff check .`、`git diff --check`：通过。

边界：本批次是隔离 deterministic/fake provider 的六类契约基线，不等价于六类真实模型质量对比；真实错误矩阵（超时、鉴权、限流、配置、空响应、非法 JSON）和 PG-D 完整 Gate 仍待后续批次。

终审结论：六类 fixture 结构化契约通过边界，继续 APP-TEXT 后续现场验证。
