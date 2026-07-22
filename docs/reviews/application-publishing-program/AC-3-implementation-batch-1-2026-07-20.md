# AC-3 Implementation Batch 1 — structured text apps

状态：`implementation_pass_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P1=0。

本批次在 `PG-D Entry passed_with_boundary` 之后执行，接入两个结构化文本应用；不进入抖音图文、数字人口播、发布平台或管理后台。

已实现：

- `StructuredLLMExecutor` 统一复用 `AppLLMPort` 与 `local-default` 配置，不新增 provider/model/key 配置源。
- `builtin.marketing-copy`：固定 3 个 variant，事实缺失/风险字段保留，字数与估算时长确定性校验。
- `builtin.viral-titles`：5–10 个候选、exactly-one source、Unicode code point 长度、规范化去重、禁用词和一次补生成。
- 非法结构化输出最多修复 1 次；修复失败稳定映射 `STRUCTURED_OUTPUT_INVALID`，输入与项目保留。
- 事实边界由领域 prompt builder 和确定性 high-risk fact validator 双重约束；价格、地址、日期、功效未在 input/context 提供时 fail closed。
- 真实来源为同项目 ArtifactVersion 时，执行器解析来源内容后再生成标题；跨项目或不存在来源 fail closed。
- ArtifactVersion content/file_refs 复用敏感字段拒绝规则；标题来源必须是同项目 schema v1 `copywriting`。
- `validation_facts` 作为内部校验证据随结构化产物保存；仍复用 ArtifactVersion 敏感字段拒绝规则，不保存 provider key/secret。
- 旧版/导入的非结构化 `copywriting` 仍可读取以保持兼容，但在交给爆款标题的 typed handoff 入口会 fail closed，不允许绕过 schema validator。
- `edited` 版本若未携带正文，继承当前版本结构化内容后再校验；任何编辑都会确定性重算字数、时长或标题长度。
- `edited` 版本不能覆盖当前版本的 `validation_facts`；事实证据固定继承，新增价格/地址/日期/功效会被拒绝。
- 文案→标题 handoff 在 repository 层强制来源 `schema_version=1`，不依赖执行器晚到校验。
- AppRunner 记录实际 `model_ref/provider_class/input_units/output_units`；成功产物写入 `ArtifactVersion`。
- FastAPI execute 路由由 fake-only 改为注册的 structured executor；测试通过注入 FakeLLMPort 隔离外部 provider。
- 桌面端从应用目录选择文案/标题应用，收集契约所需输入，展示产物版本，支持保存 `edited` 版本和“交给爆款标题”基础 handoff 操作。

验证证据：

- `uv run pytest -q`：438 passed，12 个既有 Pydantic 弃用警告。
- `tests/app_center_structured_apps_test.py`：10 passed；`tests/app_center_api_test.py`：2 个 API 场景通过；核心安全/交接测试同步通过（定向核心/结构化/API 36 passed）。
- `npm run test -- --run`：3 files / 6 tests passed。
- `npm run build`、`uv run ruff check .`、`git diff --check` 通过。

边界/未完成：

- FakeLLMPort 仍仅用于自动化测试；真实 marketing-copy/title provider smoke 与一组 handoff E2E 已通过边界，但六类 fixture 的质量对比、超时/鉴权/限流现场矩阵仍待本 Stage 后续批次。
- 编辑内容当前以结构化 JSON 版本保存；更细粒度 variant/candidate 编辑控件仍待下一批次。
- 当前 UI 的“交给爆款标题”已接入创建目标 AppRun + handoff 基础链路；真实 provider handoff E2E 已在临时项目中通过，但创建运行与 handoff 仍未合并为跨请求事务。
- PG-D 完整 Gate 不得因本批次通过而提前标记完成。

终审结论：本批次的结构化执行、事实安全边界、ArtifactVersion 版本化、编辑校验、typed handoff 和桌面基础交互已通过；真实 provider/runtime 证据仍按 APP-TEXT 队列后续批次执行。
