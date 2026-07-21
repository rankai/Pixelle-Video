# AC-3 real provider live smoke — 2026-07-20

状态：`marketing_provider_passed_with_boundary`（前两笔失败、第三笔通过）

范围：仅在临时 SQLite 项目中执行三笔 `builtin.marketing-copy`，均复用现有 `config.yaml` 的 `local-default` 配置；不触发桌面发布、抖音或任何外部写操作。

脱敏配置摘要：

- provider class：`openai_compatible`
- base URL host：`ark.cn-beijing.volces.com`
- model ref：`local-default:doubao-seed-2-0-pro-260215`
- API key：未输出、未写入证据

运行证据：

- 2026-07-20 02:43:50 发起一次 AppRun；provider 首次返回后触发系统规定的唯一一次 structured repair。
- 02:45:02 repair 返回，`StructuredLLMExecutor` 最终以 `STRUCTURED_OUTPUT_INVALID` 失败，确定性错误为 `marketing output must contain exactly 3 variants`。
- 没有 ArtifactVersion 成功写入；临时数据库在运行目录外，未改变项目数据。
- 没有盲目重试；下一次调用必须先完成 prompt/repair 约束修复并重新评审。

结论与下一步：当前 provider 鉴权、网络和 Pydantic structured parse 已有真实运行证据，但两笔业务 schema 约束均未通过。应用级输出契约、可信规则区段和 repair 原因回传已在第二笔后补齐；Unicode code point/ceil 公式规则也已修复，待审查后最多执行一笔新的受控 smoke。本证据不得被解释为 PG-D 通过。

## 第二笔受控 smoke（应用契约修复后）

- 02:51:03 发起新的临时项目和幂等键；可信 `PIXELLE_RULES` 已生效。
- provider 原始输出可解析且包含 3 个 variants；唯一 repair 后仍因 `word_count or estimated_seconds formula mismatch` 被确定性拒绝。
- 02:52:39 结束，无 ArtifactVersion 成功写入；没有继续重试。
- Unicode code point 与 `ceil(word_count/4)` 的可信规则已完成并经审查；第三笔 smoke 已执行并通过。

## 第三笔最终受控 smoke（规则修复后）

- 02:54:40 发起最后一笔临时项目；使用现有 `local-default` Doubao 配置，仅调用一次 provider，未触发 repair。
- 02:55:33 成功返回：`provider_class=openai_compatible`、`model_ref=local-default:doubao-seed-2-0-pro-260215`、`artifact_type=copywriting`、`variant_count=3`、`validation_facts=true`、`word_counts=[47,52,50]`；按通过的确定性公式对应 `estimated_seconds=[12,13,13]`。
- 本笔仍只验证 executor 输出，未写入正式项目 ArtifactVersion，未触发发布；真实 ArtifactVersion 保存和文案→标题 handoff 留在下一笔 E2E。

当前结论：marketing-copy 真实 provider smoke `passed_with_boundary`；标题真实 provider 与跨 AppRun handoff 尚未通过，不得据此标记 PG-D 完整 Gate。
