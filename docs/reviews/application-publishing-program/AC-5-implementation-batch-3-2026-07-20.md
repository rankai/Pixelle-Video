# AC-5 数字人口播 implementation batch 3（2026-07-20）

状态：`implementation_pass_with_boundary`；当前批次已完成独立复审，下一批仍须由台账入口显式开启。

## 批次入口

- batch 1、batch 2 独立复审均为 `implementation_pass_with_boundary`，P0/P1=0。
- 最新 Stage 相关聚合：352 passed、12 个既有弃用警告；adapter+API 19 passed；Ruff/diff clean。
- `PG-I` 仍未关闭；本批继续保持生产 flag 默认关闭和真实外部动作暂停。

## 本批次目标

将既有 legacy session 中已完成且可验证的本地媒体/发布文案，以安全、可回滚的 ArtifactVersion 事实登记到 AppRun；只读旧事实，不触发任何新生成：

1. 从同一绑定 session 读取 `final_video`/`digital_human_video`、`cover`、`publish_package`/标题文案；未找到或未完成时 fail-closed，不创建半成品 ArtifactVersion。
2. 对文件执行 trusted-root、绝对路径、symlink escape、存在性、MIME、大小和 SHA-256 校验；仅允许受信根下的临时测试/应用输出文件。
3. 登记 `video`、`cover`、`publish_copy` Artifact 与版本，写入 `source_app_run_id`、project、version、file_refs；重复登记返回同一版本，不覆盖旧历史。
4. 仅允许 AppRun 处于 `needs_review` 且 legacy session 输出完整时执行；完成状态必须由后续人工 review/runner 明确接受，不能因登记自动发布或完成。

## 允许修改范围

- `pixelle_video/app_center/ip_broadcast_adapter.py`：安全路径/哈希/ArtifactVersion 登记和幂等 helper；
- `tests/app_center_ip_broadcast_artifact_test.py`、AC-5 contracts/evidence；必要的 repository 只读查询增量。

## 禁止范围

- 不调用 LLM、TTS、RunningHub、数字人 provider、浏览器或抖音；不生成/上传/发布媒体；
- 不修改旧 `IpBroadcastWorkflow` 步骤、StudioApp、PublishRun/PublishPackage、账号或模型配置；
- 不打开 `digitalHumanInAppCenter`，不接桌面新入口，不新增管理后台/RBAC/多租户。

## 批次验收

- 合法临时媒体可以登记为三类 ArtifactVersion，文件 ref 字段完整且哈希可复验；
- 缺失、越权、symlink、MIME/大小/SHA 不匹配、重复/混合项目均 fail-closed；旧版本与旧 Artifact 历史保留；
- API/adapter flag-off、旧 workflow 和 Stage 相关聚合回归通过，并交独立六维复审后才进入下一批；
- 证据只能证明本地 ArtifactVersion 事实登记，不得宣称真实数字人视频/平台发布通过。

## 实施结果（待独立复审）

- 已实现：`IpBroadcastAppAdapter.register_legacy_outputs`；只接受绑定到同一项目、处于 `needs_review` 的 AppRun，复用既有 session 的视频/封面/发布文案事实。
- 已覆盖：默认 data/output/temp 与注入 custom trusted root；绝对路径、存在性、symlink escape、MIME、容器签名、大小、SHA-256、fd/fstat + 路径元数据 TOCTOU、发布文案必要字段；三类 ArtifactVersion 使用现有 `imported` source、`source_app_run_id`、项目归属和 file refs；按 AppRun 串行幂等、精确补偿；重复完整登记返回同一版本，部分/混合登记 fail-closed。
- 未改变：旧 `IpBroadcastWorkflow`、PublishRun/PublishPackage、provider、浏览器、抖音授权/上传/发布、AppRun 完成状态、生产 feature flag 默认值。
- 证据：`tests/app_center_ip_broadcast_artifact_test.py` = **8 passed**；AC-5 Entry + batch3 定向 = **12 passed**；Stage 相关聚合 = **360 passed、12 warnings**；Ruff 与 `git diff --check` 通过。
- 独立复审：[`AC-5-implementation-batch-3-review-2026-07-20.md`](AC-5-implementation-batch-3-review-2026-07-20.md)，结论 `implementation_pass_with_boundary`，P0/P1=0；真实 provider、平台、桌面入口和最终发布保持后置。
- 当前 Gate：`PG-I/implementation_pass_with_boundary`；本批不等价于 AC-5/PG-I Stage 关闭，后续批次必须继续从台账 current_stage 入口串行开启。
