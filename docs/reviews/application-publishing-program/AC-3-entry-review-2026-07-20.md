# AC-3 Entry Review — 文案与爆款标题

状态：`passed_with_boundary`

本 Entry 只冻结结构化输入/输出、事实边界和失败矩阵，不接入真实 LLM、provider、应用 UI 或发布链路。

已冻结：

- 两个应用均复用 `AppLLMPort` 与现有 `local-default` 模型配置；不新增 provider/model/key 配置源。
- 文案输出固定为 3 个可编辑 variant；标题输出是 5–10 个候选，标题长度、规范化去重和禁用词由确定性 validator 负责。
- 缺失价格、地址、功效、日期等事实必须进入 `missing_facts/risk_flags`，模型不得补造。
- 非法 JSON、空输出、字段缺失、配置/鉴权/限流/超时/provider 错误均保留输入与项目，映射稳定错误码。
- 结构化输出遇到非法 JSON、必填字段缺失或 schema mismatch 时最多自动修复 1 次；修复仍失败则保留原始输入并按原错误码终止，不进行无限重试或静默降级。
- 确定性规则已冻结：标题/禁用词比较先做 Unicode NFKC + casefold + 去 Unicode 空白/标点；标题长度按 Unicode code point（emoji 序列按 code point 计）；禁用词使用 v1 词表子串匹配；去重率按 `unique_normalized_count/requested_count` 计算；文案角度使用利益/好奇/冲突/数字/场景/身份枚举且不能全部相同。
- 文案编辑后重新计算 Unicode code point 字数与 `ceil(word_count/4)` 估算时长，不沿用旧值。
- 六类门店 fixture 和负例 fixture 已登记；fixture 不含真实客户数据。

Entry 证据：

- [`app-text-entry-contract.json`](../../contracts/app-center/app-text-entry-contract.json)
- [`fixtures/app-text-entry.json`](../../contracts/app-center/fixtures/app-text-entry.json)
- `tests/app_text_entry_contract_test.py`

放行条件：已满足。独立严格审查线程确认契约无 P1，允许进入 AC-3 implementation；本结论不代表真实 provider、UI、E2E 或完整 PG-D 已完成。

严格复审结论（`/root/pg_a_closure_reviewer_v3`）：`PG-D Entry passed_with_boundary`。

验证依据：定向 contract+coordination 21 passed；全量 Python 421 passed、12 个既有 Pydantic 弃用警告；Vitest 3 files/5 tests；desktop build、Ruff、git diff --check 均通过。
