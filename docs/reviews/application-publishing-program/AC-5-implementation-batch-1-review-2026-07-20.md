# AC-5 数字人口播 implementation batch 1 独立六维复审（2026-07-20）

状态：`implementation_pass_with_boundary`

评审线程：`/root/pg_a_closure_reviewer_v3`（只读审查，未修改代码）

## 结论

- P0：0
- P1：0（复审发现的 5 项 P1 已修复并复验）
- 结论：`implementation_pass_with_boundary`
- 允许：继续 AC-5 内的下一实施批次；不允许将本批结果解释为 PG-I/真实数字人通过。

## 六维复验摘要

1. 需求完整性：覆盖 blank/copywriting/selected_title 三来源、同项目 ArtifactVersion、source revision、legacy session 显式认领、project/session/AppRun binding、幂等 active replay、重启 reconcile、cancel/retry、waiting/topic/attention 投影、可选 Generic Task 投影和本地 fake 输出登记。
2. 逻辑正确性：Task overlay 以 legacy session 投影覆盖 Generic Task；queued/running/failed AppRun 优先于 stale transient marker；retry 清理旧 error/running/waiting 标记并保留 session 与历史 Artifact；显式 legacy claim 只固定 source-relevant snapshot，正常运行产物推进不会阻断 resume；payload project_id 不一致 fail-closed。
3. 边界情况：跨项目、混合来源、无效 variant/title、未知/缺失 session、未显式 claim、source revision/state drift、重复 active run、取消幂等、flag/readiness 未就绪、retry/accept 的 flag-off 均拒绝；waiting_for_login/waiting_for_human/needs_attention/topic confirmation 不得完成。
4. 代码质量：新增 adapter 与原子 binding store，复用既有 AppCenterRepository、IpBroadcastSessionStore、AppRunner、Task projection 和 Registry；未修改旧 workflow 步骤、PublishRun、模型配置源、浏览器运行时或平台 selector；Ruff 与 `git diff --check` 通过。
5. 测试覆盖：adapter 定向 `17 passed`；相关聚合（app-center、既有 IP broadcast、desktop confirmation、coord0）`350 passed`、12 个既有 Pydantic 弃用警告；覆盖正负来源、绑定/重启/漂移、Task waiting overlay、retry cleanup、flag-off 生命周期和 fake-only E2E。
6. 实际运行结果：仅本地隔离 SQLite/session/binding store 与 deterministic fake executor；没有调用 LLM/TTS/RunningHub/数字人 provider、浏览器、扫码、第三方授权、真实媒体文件或最终发布。

## P2/后续边界

- 真实生产 API/旧 workflow executor 尚未接入；本批 fake-only 不代表数字人视频通过。
- 并发幂等竞态可能留下新建的孤儿 legacy session；binding JSON store 仍需后续严格 schema/file-lock hardening。
- retry/fake attempt 的 task_id 关联、失败后旧输出清理、最终 ArtifactVersion trusted file refs 留下一批。
- 来源输入仍有部分字符串 coercion，后续 API schema 需改为严格类型校验。
- `cancel`/`reconcile` 保持只读/清理可用；create/execute/retry/accept 在 flag/readiness 未就绪时 fail-closed。

## Gate 边界

本结论只关闭 AC-5 implementation batch 1，不关闭 PG-I；下一批仍须依照台账控制卡实现、测试、证据和独立复审。真实 provider、最终视频/封面/publish_copy ArtifactVersion 可信文件登记、桌面新入口、第三方授权和平台动作继续后置。
