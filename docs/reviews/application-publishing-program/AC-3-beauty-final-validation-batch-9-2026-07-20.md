# AC-3 beauty final validation batch 9 — derived-field repair confirmation

状态：`quality_sample_passed_with_boundary`

独立终审：待 `/root/pg_a_closure_reviewer_v3` 复核。

在 batch 8 的本地派生字段修复通过审查后，仅对此前两次失败的 beauty fixture 做一次最终真实 provider 验证。运行使用独立临时 SQLite，最多一次 provider 调用，不创建正式 ArtifactVersion，不触发抖音或其他发布动作。

脱敏证据：

- 时间：2026-07-20 03:44–03:45（Asia/Shanghai）。
- provider calls：1；无 repair、无第三次调用。
- 结果：`passed`；3 variants；word counts `41/50/53`；estimated seconds `11/13/14`；missing facts `4`；risk flags `1`。
- API key、模型原文和临时项目路径未写入证据；临时目录随进程清理。

结论与边界：

- beauty 在本地派生字段修复后通过一次真实 structured LLM 验证，说明前次 `MARKETING_DERIVED_FIELDS` 失败已被窄范围修复覆盖。
- 六类 fixture 现均至少有一次真实 provider 通过证据，但每类样本仍很少，不能代表长期质量稳定性，也不能代替完整 PG-D 的并发/恢复、端到端 Gate 和运行期观测。
- 不再对 beauty 继续重试；若后续出现新的真实失败，应先更新规则/测试并重新审查。

终审结论：等待独立严格复核；保持 APP-TEXT/AC-3，PG-D 不提前关闭。
