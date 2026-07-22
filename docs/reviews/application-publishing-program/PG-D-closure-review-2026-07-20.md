# PG-D 完整 Gate 复审 — AC-3 文案与爆款标题

状态：`passed_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`；六维复验通过，P0/P1=0。

结论：`passed_with_boundary`

本文件按《应用中心与桌面自动发布整体协调实施方案》及 AC-D Gate 逐条对照当前证据。它只申请 PG-D，不启动 AC-4 图文、数字人或任何发布平台 Stage。

## AC-D 逐条对照

| AC-D 要求 | 当前证据 | 结论 |
| --- | --- | --- |
| 覆盖火锅、美容、民宿、洗衣店、培训、零售 6 类 fixture | [`AC-3-fixture-batch-3-2026-07-20.md`](AC-3-fixture-batch-3-2026-07-20.md)、`tests/app_center_fixture_quality_test.py`；六类均通过结构化 schema/事实白名单/validator | passed |
| 缺失价格/地址不得编造 | `tests/app_center_structured_apps_test.py` 的价格/地址事实拒绝与安全诊断；`UNSUPPORTED_PRICE_FACT`/`UNSUPPORTED_ADDRESS_FACT` | passed |
| 标题去重、长度、禁用词确定性规则 | `tests/app_center_structured_apps_test.py`、`tests/app_center_fixture_quality_test.py`；标题长度/归一化去重/禁用词/重复诊断 | passed |
| 超时、非法 JSON、空返回、部分字段缺失有明确恢复 | [`AC-3-error-matrix-batch-4-2026-07-20.md`](AC-3-error-matrix-batch-4-2026-07-20.md)、`tests/app_center_error_matrix_test.py`、`tests/app_center_core_test.py`；稳定错误码、唯一 repair、失败持久化、输入保留、无 Artifact | passed_with_boundary |
| 缺配置、鉴权、限流、超时、provider 失败映射稳定错误码 | 错误矩阵批次 4：`LLM_CONFIGURATION_MISSING`、`LLM_AUTH_FAILED`、`LLM_RATE_LIMITED`、`LLM_TIMEOUT`、`LLM_PROVIDER_FAILED`、`STRUCTURED_OUTPUT_INVALID`；无盲重试 | passed |
| 共享 `local-default`，配置变更后无需重启生效 | [`AC-3-config-hot-reload-batch-11-2026-07-20.md`](AC-3-config-hot-reload-batch-11-2026-07-20.md)、`test_config_llm_port_reads_model_config_change_without_reconstruction`；同一 port 读取新 model_ref，prompt 不含 key | passed_with_boundary |
| 文案→选择版本→标题→保存项目端到端 | [`AC-3-real-handoff-e2e-2026-07-20.md`](AC-3-real-handoff-e2e-2026-07-20.md)；真实 provider、两个 ArtifactVersion、同项目 source version、typed handoff、5 个标题 | passed_with_boundary |
| 10 个目标用户或内部模拟任务中至少 8 个无需解释完成首条文案 | [`AC-3-user-completion-simulated-batch-15-2026-07-20.md`](AC-3-user-completion-simulated-batch-15-2026-07-20.md)；浏览器层 10/10 completed、10/10 help=0/intervention=false、每场景 8 actions | passed_with_boundary |

## PG-D 三条闭环要求

1. 文案到标题 handoff 可恢复、可版本化：真实 handoff E2E 已保存 ArtifactVersion；批次 12 证明 terminal failure 后再次 run 可恢复，source artifact/version 隔离。
2. 非法 prompt/output 不污染项目：批次 10 证明 structured AppRunner 失败持久化、无 Artifact、输入保留、稳定 diagnostic；批次 6/7/8 证明诊断、派生字段修复和 fail-closed validator。
3. 应用中心内核由真实 structured LLM 验证：[`AC-3-real-provider-smoke-2026-07-20.md`](AC-3-real-provider-smoke-2026-07-20.md) 与真实 handoff E2E 均使用 `local-default` openai-compatible provider；不只依赖 FakeLLMPort。

## 运行与质量证据

- Python 全量回归：`uv run pytest -q`，457 passed、12 个既有 warning。
- AppRunner 并发/恢复：批次 12 定向 2 passed；运行 Attempt 有 provider/model/timestamps/duration metadata。
- 运行期观测：批次 13 定向 3 passed；成功、失败、取消路径写入非负 `duration_ms`。
- 前端：批次 15 使用 Python Playwright fallback（应用内 Browser 运行时此前报 `Cannot redefine property: process`）；JSON/截图/script SHA 已核对，意外 console error=0，已知 antd warning 20。
- `contentApps` 默认关闭，canonical flag env 为 `PIXELLE_APP_CENTER_CONTENT_APPS`，见 `docs/contracts/app-center/feature-flag-matrix.json` 与 Registry contract。

## 边界与不误报

- 10/10 是 AC-D 明确允许的“内部模拟任务”分支，不是十名真实用户研究；它只证明首路径完成度，不证明真实用户满意度。
- 真实 provider/handoff 样本有限，不据此宣称长期内容质量稳定；provider 现场错误矩阵仍以确定性 adapter matrix 为主。
- 当前不验证图文、数字人、管理员/RBAC、套餐/支付、发布平台或最终发布；这些严格留在后续 Stage。
- 已知 Ant Design deprecation warnings 是现有技术债，不是本批次新增业务错误。

## 申请审查结论

独立严格审查线程已按六维复核本矩阵、所有引用证据、运行结果、内部模拟边界和台账状态，结论为 P0/P1=0。因此 PG-D 标记为 `passed_with_boundary`，APP-TEXT/AC-3 可归档。下一 Stage 仍需按台账显式 Entry，不得因 PG-D 通过自动启动 AC-4 或发布链路。

保留边界：内部模拟不是十名真实用户研究；真实 provider 样本和错误现场有限；未知 GET 请求仍允许页面壳层继续（未知写请求已阻断）；空返回/部分字段缺失尚未逐例拆成独立自动化场景，但已有统一 schema fail-closed、一次 repair、稳定错误码和失败持久化证据；现有 Ant Design deprecation warnings 继续登记为技术债。以上均为 P2/边界，不阻塞 PG-D。
