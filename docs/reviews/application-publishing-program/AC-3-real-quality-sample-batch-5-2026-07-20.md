# AC-3 real quality sample batch 5 — six store fixtures

状态：`quality_sample_partial`

独立终审：待 `/root/pg_a_closure_reviewer_v3` 复核。

本批次是一次有边界的真实 `builtin.marketing-copy` 质量抽样：每个 fixture 使用独立临时 SQLite 项目，复用现有 `local-default` 配置；每个类别最多执行 executor 规定的一次 repair，不创建正式 ArtifactVersion，不调用抖音或其他发布能力。

| fixture | 结果 | provider calls | 结构化摘要 |
| --- | --- | ---: | --- |
| hotpot | passed | 1 | 3 variants；word counts 35/34/35；estimated seconds 9/9/9；missing facts 3；risk flags 1 |
| beauty | failed | 2 | 唯一 repair 后仍为 `STRUCTURED_OUTPUT_INVALID` |
| homestay | passed | 1 | 3 variants；word counts 41/50/46；estimated seconds 11/13/12；missing facts 2；risk flags 1 |
| laundry | passed | 1 | 3 variants；word counts 62/63/65；estimated seconds 16/16/17；missing facts 4；risk flags 1 |
| training | passed | 2 | 3 variants；word counts 64/56/55；estimated seconds 16/14/14；missing facts 2；risk flags 1 |
| retail | failed | 2 | 唯一 repair 后仍为 `STRUCTURED_OUTPUT_INVALID` |

运行总计：6 类、9 次 provider 调用；4/6 类通过，2/6 类在一次 repair 后稳定失败。脚本只输出 provider class/model 日志和脱敏结构化摘要，未输出 API key；临时目录随进程结束清理。

边界与处置：

- 两个失败类别没有进行第二轮盲目重试；本次运行没有保留最终 validator 的具体业务文本，不能臆断失败原因。下一步先补充可安全持久化的确定性失败诊断/fixture 级审查，再决定是否针对失败类别各执行一次复验。
- 本批次证明真实模型在四类 fixture 上可通过当前结构化契约，但不能宣称六类真实质量通过，也不能关闭 PG-D。
- provider 的真实 401/429/timeout 现场仍由确定性错误矩阵覆盖，未为制造错误而重复调用外部服务。

验证证据：

- 运行时间约 2026-07-20 03:24–03:31（Asia/Shanghai）；每类独立临时项目，未产生正式 ArtifactVersion 或外部写操作。
- 失败类别均在最多一次 repair 后结束；无第三次调用。

终审结论：等待独立严格审查；保持 APP-TEXT/AC-3，PG-D 不得通过。
