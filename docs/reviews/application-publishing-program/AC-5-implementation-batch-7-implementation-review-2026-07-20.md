# AC-5 数字人口播应用化 implementation batch 7 独立六维复审（2026-07-20）

## 复审范围

- 桌面双 flag 与 Registry/readiness/actionable 投影；旧 `/ip` 保留与新 `/apps/digital-human-video` 路由。
- 空白项目、copywriting ArtifactVersion、selected_title ArtifactVersion 三来源 UI/API 接线。
- AppRun/session/source revision/context snapshot 指针恢复、pending 幂等键与来源产物绑定、项目/来源切换安全清理。
- local isolated executor gray-cycle、needs_review→显式 accept→completed 状态闭环和无外部动作证据。
- 排除真实 LLM/TTS/数字人 provider、浏览器、抖音扫码/授权/上传/最终发布、连续生产灰度及管理员控制面。
- 审查线程：`/root/pg_a_closure_reviewer_v3`，不修改业务代码。

## 六维验证

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | 双 flag、旧/新路由、三来源、状态投影、重启恢复、pending 幂等与 local gray 均已落地；QA JSON 补齐契约要求的 flag/binding/artifact 字段 |
| 逻辑正确性 | 通过 | backend/readiness/actionable gate；project/session/source revision/context snapshot 校验；非首来源产物恢复；项目切换与显式 accept 均有测试 |
| 边界情况 | 通过 | flag-off、backend-disabled、绑定漂移、pending 来源缺失 fail-closed、waiting/needs_review 非终态、无外部动作均有验证 |
| 代码质量 | 通过 | TypeScript/build 通过；Ruff clean；`git diff --check` clean；复用既有 API/Registry/模型配置事实源 |
| 测试覆盖 | 通过（有界） | Vitest 6 files/32 tests；Python 定向聚合 52 passed/12 个既有 Pydantic 弃用警告；Entry/gray/API/adapter/artifact/handoff 均覆盖 |
| 实际运行结果 | 通过（本地隔离） | 三来源均完成 `needs_review → explicit accept → completed`；provider/browser/platform/final publish 计数均为 0；QA snapshot marker 已归档 |

## 修复清单与复验

1. 明确 backend feature flag 与桌面 rollout flag 的双门控和映射，避免仅凭桌面 flag 显示可用。
2. AppRun 指针增加 route/session/source revision/context snapshot 校验，绑定漂移时 fail-closed。
3. pending 提交保存 `source_artifact_id`，恢复非首个来源产物；来源不存在、项目/来源切换时清理旧 pending 幂等键。
4. 保留 pending 的 source version/variant，避免重启后改变提交 payload；应用中心卡片以 `actionable` 作为按钮/状态投影。
5. QA gray-cycle JSON 增加 `flag_values`、`project_id`、`app_run_id`、`session_id`、`source_revision`、`before_after_restart`、`source_mode`、`artifact_ids` 与外部动作计数，并由契约测试校验。

## 结论

独立审查线程最终确认 `implementation_pass_with_boundary`，P0=0、P1=0。允许关闭 batch 7；不代表 PG-I/APP-IPB 已关闭，也不代表真实 provider、浏览器、抖音授权/上传/最终发布或连续生产灰度通过。保留 P2/边界：local gray 是隔离 executor 与声明式 snapshot marker，另有既有 chunk size warning 和 Pydantic 弃用警告。
