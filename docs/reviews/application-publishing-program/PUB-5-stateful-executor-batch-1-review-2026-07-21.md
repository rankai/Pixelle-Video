# PUB-5 Stateful Executor Batch 1 独立六维复审（2026-07-21）

- 审查者：独立严格审查线程 `/root/pg_a_closure_reviewer_v3`
- 结论：`implementation_pass_with_boundary`
- P0：0
- P1：0（实现批次）

## 六维结果

1. 需求完整性：覆盖五阶段协议、schema v2、连续前缀、身份/媒体/远端媒体 identity、typed blocker、真实话题实体、封面 accepted URL、FinalActionGuard 和 RunService/API binding。
2. 逻辑正确性：初始/中途认证失效清空旧前缀；可读媒体不匹配不 fallback；空 file input 仅在远端媒体 ID 对账成功时恢复；话题 entity ID、封面 canonical URL/task-space 均复核。复审发现并修复了一个 P1：同一 editor URL 的路由迁移只有在稳定 `task_space_id` 相同且 host/path 属于已知编辑器空间时才兼容；cover receipt 同时要求 ID 相同与 task-space 名称 canonical 等价，否则 fail-closed。
3. 边界情况：无稳定远端 identity 时 typed fail-closed；不重复上传；最终发布 click/count 始终为 0；不记录 profile path、cookie 或签名 URL。
4. 代码质量：scoped Ruff 与 `git diff --check` 通过。
5. 测试覆盖：修复后 `uv run pytest -q tests/publish_*.py` 为 123 passed、12 个既有 Pydantic 弃用警告；新增跨 task-space ID、同 ID 异 host/path 的 cover 负例、跨 ID editor-route checkpoint 负例、身份阻塞恢复迁移、最新 state-version 事件追加和 restart recovery boundary 测试。
6. 实际运行：真实抖音 headful bounded attempt 3 已观察并持久化一次视频上传及完整 `inspect → upload → wait → mutate → verify` 前缀；话题 entity 数为 2、封面 HTTPS CDN receipt 存在、最终 publish click/count=0。一次 stale state-version 竞态被记录并修复；随后通过受约束的 DB/service reconciliation 收口到 `waiting_for_human / await_human_publish`。独立复审期间暴露的 restart recovery P1 也已修复，修复后 sidecar 重启回读仍保持 `waiting_for_human`，没有浏览器重跑、二次上传或最终发布。因此 PG-K `passed_with_boundary`，不等价于已发布。

## Gate 处理

PG-K 可记为 `passed_with_boundary`：同一 run 的完整 verify checkpoint 和 guarded DB/service 收口均有证据；最终发布仍为人工门，不能自动点击。扫码、挑战、第三方授权、状态不确定、最终发布按钮均为暂停点。

## 第二轮独立复审与最终 Gate（2026-07-21）

- 独立审查线程复验六维结果：需求完整性、逻辑正确性、边界、代码质量、测试覆盖、实际运行均通过；P0/P1=0。
- `uv run pytest -q tests/publish_*_test.py`：123 passed，12 个既有 Pydantic warnings；Ruff、`git diff --check`、QA JSON 解析通过。
- 源 DB 最终回读：`waiting_for_human / await_human_publish / v49`，最后事件 `verified_checkpoint_reconciled@49`；checkpoint 完整、topic=2、cover=1、Guard armed、最终点击=0。
- sidecar 真实重启后保持上述状态，没有重复上传、浏览器重跑或最终发布。
- 最终结论：`PG-K=passed_with_boundary`；最终发布仍需人工确认，不能标记为平台已发布。
