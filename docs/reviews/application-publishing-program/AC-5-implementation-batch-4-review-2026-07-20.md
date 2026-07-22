# AC-5 数字人口播 implementation batch 4 独立六维复审（2026-07-20）

结论：`implementation_pass_with_boundary`；P0/P1 = 0。

## 复审范围

- legacy output fingerprint、review attempt 原子创建、人工 accept/reconcile 与重启恢复；
- `video`、`cover`、`publish_copy` 三类 imported ArtifactVersion 的完整绑定与 fail-closed；
- FastAPI 专用 accept 安全投影，以及 generic complete、complete-review、transition 的 completion bypass 防护；
- trusted roots、file ref/publish copy schema、MIME/magic、大小、SHA、fd/fstat TOCTOU、archived 状态和补偿；
- AC-5 定向、Stage 聚合、Ruff、diff 与实际运行边界；provider、浏览器、平台和最终发布不得发生。

## 六维结果

| 维度 | 结果 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | passed | 只有同一 project/app/version/session binding、`needs_review` AppRun、完整 imported outputs、review attempt 和 fingerprint 一致时才可 accept；登记不自动完成；通用完成入口拒绝数字人。 |
| 逻辑正确性 | passed | `ensure_review_attempt` 使用 `BEGIN IMMEDIATE` 原子创建/冲突检测；import 失败精确清理本次 artifacts/attempt；accept 绑定 output IDs、fingerprint、attempt、session 第 6 步，重启/replay 幂等。 |
| 边界情况 | passed_with_boundary | 缺 attempt、partial/mixed/non-imported、fingerprint drift、archived artifact、路径越权、绝对路径、symlink、MIME/magic/size/SHA/file_key、publish copy 字段异常和 TOCTOU 均 fail-closed；跨进程锁/CAS、锁清理和崩溃后的 partial 清扫留 P2。 |
| 代码质量 | passed | adapter/repository/API 职责边界清晰；generic completion 不返回完整数字人 AppRunResponse；Ruff 与 `git diff --check` 通过；未改旧 workflow、PublishRun/PublishPackage、provider 或生产 flag 默认值。 |
| 测试覆盖 | passed | AC-5 batch4 定向 **38 passed**；Stage 聚合 **367 passed、12 warnings**；覆盖并发、TOCTOU、补偿、重启、attempt 冲突、篡改 file ref、archived、API 安全投影和三类 generic completion bypass。 |
| 实际运行结果 | passed_with_boundary | 仅在本地 SQLite、临时 trusted root、fixture/隔离 API 中运行；没有调用 LLM/TTS/数字人 provider、浏览器、抖音授权、上传或最终发布。12 个 Pydantic 弃用警告为既有技术债，不阻断本批。 |

## P2 留存边界

1. 当前锁和 binding store 主要是单进程 `RLock`/JSON；多进程或多 worker 需迁移到 SQLite `BEGIN IMMEDIATE`、文件锁或等价 CAS，并治理锁表清理。
2. 生产化前补充进程崩溃发生在三 artifact 写入中间时的恢复清扫，以及跨进程 accept 竞争的幂等验证。

## Gate 建议

- 本批：`implementation_pass_with_boundary`，允许进入 AC-5 下一批；
- Stage `PG-I`：仍未关闭，必须完成实际 executor/桌面入口接线及后续 Gate 边界复验；
- 本结论不等价于真实数字人 provider、抖音授权、视频上传、字段回读或最终发布成功。

复审线程：`/root/pg_a_closure_reviewer_v3`。
