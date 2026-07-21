# AC-5 数字人口播 implementation batch 1（2026-07-20）

状态：`implementation_in_progress`；当前唯一入口为 `APP-IPB/AC-5 implementation`。

## 批次入口

- `AC-5-entry-review-2026-07-20.md`：`entry_passed_with_boundary`，P0/P1=0。
- AC-5 Entry 聚合：246 passed、12 个既有 Pydantic 弃用警告；Ruff/diff clean。

## 本批次目标

先建立可回滚、可复验的 adapter 骨架，不一次性重写口播生产链路：

1. 创建/恢复 binding：`project_id + session_id + app_run_id + source_revision`，旧 session 未绑定时必须显式认领，跨项目/歧义 fail-closed。
2. 来源校验：空白、copywriting selected variant、selected_title exactly-one；只读同项目 ArtifactVersion，不改变旧 session 内容事实。
3. AppRun/Task 投影：将 session step/notice 与 `TaskStatus`、AppRun 状态按 Entry contract 映射；waiting 状态不成功；取消/重复/重启不制造第二 session。
4. 使用隔离 fake workflow/本地 session store 做最小运行时 E2E；不调用真实 provider、不生成真实最终视频、不修改既有 `IpBroadcastWorkflow` 核心实现。
5. 建立 adapter 失败/恢复/幂等事件与测试证据，为下一批 ArtifactVersion 登记和桌面入口接线提供事实。

## 允许修改范围

- `pixelle_video/app_center/**`：adapter binding、输入/映射模型、fake executor、repository 关联记录；
- `api/routers/app_center.py` 与 app-center schemas：最小创建/恢复/状态读取 API；
- AC-5 contract/fixture/tests/QA evidence；必要的 Task projection 增量。

## 禁止范围

- 不修改 `pixelle_video/services/ip_broadcast_workflow.py` 的既有步骤实现，不删除/隐藏 `StudioApp` 旧入口；
- 不实现真实 provider/RunningHub/TTS/数字人媒体生成，不登记最终 video/cover/publish_copy ArtifactVersion（留下一批）；
- 不修改 PublishRun/PublishPackage 事实源，不执行抖音扫码、授权、上传、字段回读或最终发布；
- 不新增模型配置源、管理员/RBAC/套餐/支付/多租户或第二浏览器 runtime；
- `digitalHumanInAppCenter` 默认关闭，所有新 API 必须显式 fail-closed。

## 本批次验收

- binding 创建/显式 legacy claim/跨项目拒绝/恢复选择/source revision 固定；
- AppRun `draft → queued → running → needs_review/failed/cancelled` 与 Task 投影一致；waiting_for_login/waiting_for_human/needs_attention/IP-learning topic confirmation 均不 completed；
- 相同 idempotency key 返回已有 active binding；取消、重试、重启保持 session_id 不变且旧历史保留；
- fake workflow E2E 只证明 adapter 生命周期，不得宣称真实口播/数字人产物或平台能力通过；
- 定向测试、既有口播回归、全量相关聚合、Ruff、diff 和独立六维审查均通过后才进入 batch 2。

## 实施结果（待独立复审）

- 已实现：`pixelle_video/app_center/ip_broadcast_adapter.py` 与 `IpBroadcastBindingStore`；不修改既有 `IpBroadcastSessionStore` 步骤实现。
- 已覆盖：三种来源的同项目 ArtifactVersion 校验、selected variant/title 约束、source revision 固定、旧 session 显式认领、跨项目/来源变更拒绝、active idempotent replay、重启 reconcile、cancel/retry、waiting 状态不成功、可选 Generic Task 脱敏投影。
- 本地 fake E2E：仅登记无 provider 的 video/cover/publish_copy 业务 Artifact（`needs_review`→显式 accept→`completed`），不代表真实数字人或最终视频能力。
- 证据：`uv run pytest -q tests/app_center_ip_broadcast_adapter_test.py` = **17 passed**；Stage 相关聚合（`tests/app_center_*_test.py tests/ip_broadcast_*_test.py tests/desktop_ip_learning_confirmation_test.py tests/coord0_contract_test.py`）= **350 passed、12 warnings**；Entry+IPB 子集为 263 passed；Ruff 与 `git diff --check` 通过。
- 当前 Gate：仍为 `PG-I/implementation_in_progress`，等待 `/root/pg_a_closure_reviewer_v3` 六维复验；真实 provider、媒体/ArtifactVersion 可信文件规范、桌面入口、平台/发布动作均保持后置。
