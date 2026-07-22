# AC-5 数字人口播 implementation batch 3 独立六维复审（2026-07-20）

结论：`implementation_pass_with_boundary`；P0/P1 = 0。

## 复审范围

- `IpBroadcastAppAdapter.register_legacy_outputs` 及 trusted-root/fd 读取边界；
- 三类 `video`、`cover`、`publish_copy` ArtifactVersion 登记、来源和幂等；
- 精确补偿、同 AppRun 并发、TOCTOU、部分/混合登记和 needs_review 状态门禁；
- AC-5 adapter/API/artifact/entry 定向测试、Stage 聚合、Ruff、diff；
- provider、浏览器、上传、抖音、最终发布和 AppRun 完成转移不得发生。

## 六维结果

| 维度 | 结果 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | passed | 只读既有 session 输出；同项目绑定、`needs_review` 门禁；trusted root、绝对路径、symlink、MIME、容器 magic、大小、SHA-256；三类 ArtifactVersion 与 `imported` source；没有 provider/browser/platform side effect |
| 逻辑正确性 | passed | 同 AppRun 进程内 RLock 串行；完整登记返回原版本；partial/mixed/non-imported 冲突 fail-closed；异常仅删除本次 artifact IDs；fd/fstat + 路径元数据拦截 TOCTOU |
| 边界情况 | passed_with_boundary | 缺失/空文件、越权、symlink、MIME/签名/大小、发布文案必要字段和重复登记均有稳定错误；多进程锁、锁清理和全量分支扩展留 P2 |
| 代码质量 | passed | 适配器/仓储补偿边界清晰；Ruff 与 `git diff --check` 通过；未改旧 workflow、PublishRun/PublishPackage 或 feature flag 默认值 |
| 测试覆盖 | passed | 独立复审定向 adapter/API/artifact/entry 30 passed；新增同 AppRun 并发幂等、fd/fstat+路径元数据 TOCTOU、精确补偿测试；Stage 聚合 359 passed、12 个既有警告 |
| 实际运行结果 | passed_with_boundary | 本地临时文件可登记并复验 hash/ref/version；未触发真实 provider、浏览器、平台、授权、上传、最终发布或完成转移 |

## P2 留存边界

1. 当前锁是单进程全局锁；未来多进程/多 worker 需要 SQLite `BEGIN IMMEDIATE` 或文件锁，并增加锁表清理。
2. 生产化前补齐跨进程竞态、所有 missing/empty/MIME/size/quicktime/JSON package 分支和更大媒体样本。

## Gate 建议

- 本批：`implementation_pass_with_boundary`，可进入 AC-5 下一批；
- Stage `PG-I`：仍未关闭，必须完成后续真实执行/桌面接线及其边界复验后才可归档；
- 本结论不等价于真实数字人 provider、抖音授权、上传或发布通过。

复审线程：`/root/pg_a_closure_reviewer_v3`。
