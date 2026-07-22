# AC-3 editor batch 2 — fine-grained structured editing

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P1=0。

本批次在真实 provider handoff E2E 通过边界后执行，仅补 CreationWorkspace 的结构化编辑体验，不进入图文、数字人或发布平台。

已实现：

- 文案 ArtifactVersion 展开三版 variant 编辑器：开头、正文、行动号召可分别修改。
- 修改任一组成字段时，UI 即时重算 `full_text`、Unicode code-point `word_count` 和 `ceil(word_count/4)` 的 `estimated_seconds`。
- 标题 ArtifactVersion 展开 candidate 编辑器：逐条修改标题并即时重算 Unicode code-point `length`。
- 保存仍统一走 `appendArtifactVersion(..., source="edited")`；后端继续固定继承 `validation_facts` 并执行 schema/fact/handoff 校验。
- 增加测试环境 `afterEach(cleanup)`，避免 React DOM/异步 reload 状态污染相邻测试。

验证证据：

- `npm run test -- --run`：3 files / 9 tests passed。
- 补充 emoji 回归：前端使用 `Array.from(value).length`，与后端 Unicode code-point 规则一致。
- `npm run build`：通过，仅保留既有 >500KB chunk warning。
- `uv run ruff check .`、`git diff --check`：通过。

边界/未完成：

- 当前 editor 仍是本地结构化编辑器，不包含逐字段服务端 patch/并发编辑冲突 UI。
- 六类门店 fixture 的真实质量对比、真实错误矩阵和 PG-D 完整 Gate 仍未完成。

终审结论：细粒度编辑批次通过边界；PG-D 总 Gate 仍保持未完成。
