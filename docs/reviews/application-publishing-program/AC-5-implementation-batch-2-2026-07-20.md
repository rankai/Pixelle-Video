# AC-5 数字人口播 implementation batch 2（2026-07-20）

状态：`implementation_in_progress`；当前唯一入口为 `APP-IPB/AC-5 implementation batch 2`。

## 批次入口

- batch 1 独立复审：`implementation_pass_with_boundary`，P0/P1=0。
- 证据：adapter 17 passed；Stage 相关聚合 350 passed、12 个既有 Pydantic 弃用警告；Ruff/diff clean。
- 本批不改变 `PG-I` 的 Stage 未关闭状态。

## 本批次目标

在不启用生产数字人能力的前提下，将已审查的 adapter 变成可审计、可被桌面/后端消费的 API 边界：

1. 新增严格的 IP Broadcast AppRun create/resume、reconcile/status、cancel、retry API；create/execute/retry/accept 受 Registry flag + readiness fail-closed 保护。
2. API 响应只暴露 AppRun/binding/projection/step status/notice 的安全投影，不返回 provider 凭据、绝对文件路径或完整旧 session state。
3. 保持既有 `/ip-broadcast/sessions/**` 旧入口和真实 workflow API 不变；新 API 不执行 provider、浏览器、媒体生成、平台授权或最终发布。
4. 为 API 负例补齐 project mismatch、flag/readiness disabled、missing session、unbound claim、idempotency、cancel/retry 状态边界；以临时 SQLite/session/binding store 做测试。

## 允许修改范围

- `pixelle_video/app_center/ip_broadcast_adapter.py`：仅为 API 适配所需的安全投影/依赖注入增量；
- `api/schemas/app_center.py` 或独立 AC-5 schema；`api/routers/**` 与 `api/app.py` 的新边界路由；
- `tests/app_center_ip_broadcast_api_test.py`、AC-5 batch evidence/ledger。

## 禁止范围

- 不实现真实 `IpBroadcastWorkflow` provider/RunningHub/TTS/数字人 executor，不生成最终视频/封面/发布素材 ArtifactVersion；
- 不修改旧 `/ip-broadcast` 路由行为、StudioApp 入口、PublishRun/PublishPackage、账号/模型配置事实源；
- 不打开 `digitalHumanInAppCenter`，不执行扫码、第三方授权、浏览器、真实媒体、抖音上传或最终发布；
- 不新增桌面页面、管理员/RBAC/套餐/支付/多租户或第二浏览器 runtime。

## 批次验收

- flag/readiness 关闭时新建/重试/完成均返回稳定 fail-closed 错误；只读 reconcile 与 cancel 仍安全；
- API 不能通过响应泄露 `state` 中的绝对路径/凭据字段；
- API 与 adapter 共享同一 AppCenter SQLite、binding store 和 legacy session store，重启后可按 session/project 恢复；
- 既有 IP broadcast 与全量相关回归通过，并交独立六维复审后才进入 batch 3（真实 executor/ArtifactVersion 仍须另行边界审查）。

## 实施结果（待独立复审）

- 已实现：`api/routers/ip_broadcast_app.py` 与 AC-5 request/response schema；路由挂载在 `/api/app-center/ip-broadcast/**`。
- 已覆盖：create/resume、GET status/reconcile、cancel、retry；生产 adapter 逐请求读取 Registry flag/readiness；API 响应只包含 AppRun/binding/projection/step status、脱敏 notice 和 artifact key，不回显旧 session state 或 input payload。
- 证据：`tests/app_center_ip_broadcast_api_test.py` = **2 passed**；Stage 相关聚合 = **352 passed、12 warnings**；Ruff 与 `git diff --check` 通过。
- 当前 Gate：仍为 `PG-I/implementation_pass_with_boundary`（batch 1 已通过；batch 2 等待独立复审）；真实 provider、媒体、桌面和平台动作保持后置。
