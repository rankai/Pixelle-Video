# AC-3 failure diagnostics recheck batch 7 — beauty / retail

状态：`quality_sample_partial`

独立终审：待 `/root/pg_a_closure_reviewer_v3` 复核。

这是诊断码落地后的唯一一次定向复验：只针对前一批次的 beauty 与 retail 各运行一次，仍使用隔离临时 SQLite；每类最多执行 executor 规定的一次 repair，不创建正式 ArtifactVersion、不触发发布。

| fixture | 结果 | provider calls | 安全诊断 |
| --- | --- | ---: | --- |
| beauty | failed | 2 | `STRUCTURED_OUTPUT_INVALID` / `MARKETING_DERIVED_FIELDS`；安全消息为 `word_count or estimated_seconds formula mismatch` |
| retail | passed | 1 | 3 variants；missing facts 2；risk flags 1 |

运行证据：

- 2026-07-20 03:36–03:39（Asia/Shanghai）；共 3 次 provider 调用，无第三次重试。
- beauty 的失败原因已被代码拥有的诊断码审计；未输出模型原文、API key 或 provider 异常文本。
- retail 在前一批次失败后，本次单次调用通过，说明前次失败不应被解释为稳定类别失败。
- 两个临时项目均未写入正式 ArtifactVersion 或任何外部发布系统。

结论与边界：

- 当前真实质量证据为：hotpot/homestay/laundry/training 通过，retail 至少一次通过，beauty 两次抽样均在一次 repair 后失败，且最新失败归因于派生字段公式。
- beauty 不再继续重试；后续如要处理，应优先优化模型可信规则/本地修复策略并经审查后再测，不把 provider 重试当修复。
- 单一输入、少量抽样不能代表完整质量稳定性；PG-D 仍未完成，不进入图文、数字人或发布平台。

终审结论：等待独立严格复核；保持 APP-TEXT/AC-3。
