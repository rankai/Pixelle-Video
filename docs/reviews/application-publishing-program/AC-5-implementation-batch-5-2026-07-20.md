# AC-5 数字人口播 implementation batch 5（2026-07-20）

状态：`implementation_in_progress`；Entry 已独立复审通过，当前唯一入口为 `APP-IPB/AC-5 implementation batch 5`。

## 批次入口

- AC-5 Entry 与 batch 1、batch 2、batch 3、batch 4 均已独立复审为 `entry_passed_with_boundary` 或 `implementation_pass_with_boundary`，P0/P1=0。
- batch 4 已建立可信 imported outputs、fingerprint、review attempt 和专用人工 accept；本批不重复实现这些安全边界。
- `PG-I` 仍未关闭；生产 feature flag 默认关闭，真实 provider、浏览器、抖音和最终发布继续暂停。

## 本批次目标

将现有口播流程在本地/隔离执行模式下聚合到 AppRun，而不重写旧 workflow：

1. 建立 `IpBroadcastAppAdapter` 的受控 executor/bridge，使空白项目、文案来源、标题来源都能生成同一份结构化 AppRun 输入，并复用既有 session/task 事实源。
2. 建立 session → Task → AppRun 状态映射和确定性恢复：重启后回到原 session 的正确口播步骤，不创建新 session、不把 `waiting_user`/`needs_review` 映射成成功。
3. 为取消、失败、重试建立幂等边界：重试产生新 attempt，保留旧 session/ArtifactVersion 历史，不重复导入视频/封面/publish_copy，不生成孤儿项目。
4. 为本地/隔离 executor 提供最小测试 seam 和任务投影；不得在本批打开 `digitalHumanInAppCenter` 或触发真实数字人 provider。
5. 将 batch 4 的显式 accept 作为唯一完成路径；executor、generic transition、旧入口均不得绕过 review/fingerprint/output binding。

## 允许修改范围

- `pixelle_video/app_center/ip_broadcast_adapter.py`：受控 executor/bridge、session/task/run 聚合、恢复/取消/重试 helper；复用 batch 4 的 artifact/accept helper；
- 必要的 `pixelle_video/app_center/runner.py`、`task_projection.py` 或 repository 原子查询，仅限 AppRun/Task 生命周期投影与 attempt 幂等；
- `api/routers/ip_broadcast_app.py`、`api/schemas/app_center.py`：最小 execute/status/reconcile 入口，必须返回既有安全投影；
- `docs/contracts/app-center/**`、`tests/app_center_ip_broadcast_*_test.py`、本批证据与独立复审文档。

## 禁止范围

- 不调用 LLM、TTS、RunningHub、数字人 provider、浏览器、抖音或其他平台；不扫码、不授权、不上传、不发布；
- 不修改旧 `IpBroadcastWorkflow` 核心步骤、StudioApp 旧入口、PublishRun/PublishPackage、发布账号、模型配置或桌面导航；
- 不打开 `digitalHumanInAppCenter`，不新增管理员/RBAC/套餐/支付/多租户控制面；
- 不把本地 fake/isolated executor 证据写成真实 provider 成功，不把登记/执行写成最终人工发布完成；
- 不绕过台账直接进入 PUB-INTEGRATION/PUB-4。

## Entry 契约与负例

实现前必须冻结并测试：

- 三种来源 exactly-one、project/context/source revision 和 binding 一致；
- executor 只能创建/更新同一 AppRun/session，重复 idempotency key 不新建 session；
- `draft → queued → running → needs_review` 的映射以及 `waiting_user`/`failed`/`cancelled` 投影；
- 取消中断与重试新 attempt，旧 attempt、session、ArtifactVersion 和 task history 保留；
- executor 失败、重启、重复执行、并发 execute、缺 session/binding、跨项目和旧入口调用均 fail-closed；
- `accept_legacy_outputs` 是唯一 `needs_review → completed` 路径，输出 ID/fingerprint/review attempt 不完整时拒绝；
- flag-off 与旧 `/ip-broadcast/sessions/**` 回归不受影响，API 响应不泄露输入、session state、凭证或绝对路径。

## 批次验收

- 本地/隔离 executor 能从三种来源创建确定性 AppRun，并将旧 session/task 状态安全投影；
- 重启、取消、失败、重试和并发场景不产生重复 session、重复 imported outputs 或孤儿项目；
- 只有专用人工 accept 能完成 AppRun，generic API/transition/旧入口均不能绕过；
- batch 定向、Stage 聚合、Ruff、`git diff --check` 和独立六维复审通过后，才能判断 PG-I 是否仍需后续 live/desktop batch；真实 provider/平台证据仍不在本批；
- 若需要真实 provider、第三方授权、平台上传或最终发布，立即暂停并把人工动作登记为后续 Gate，不在本批自行执行。

## 当前状态

- Entry 复审：`entry_passed_with_boundary`，P0/P1=0；Entry contract 4 passed/4 warnings；Entry 聚合 246 passed/12 warnings；Ruff/diff clean。
- 尚未实现本批 executor/bridge；当前只完成机器可读契约与失败 fixture。
- 下一步：在保持 flag 默认关闭、无 provider/browser/platform 动作的前提下，实现本地/隔离 executor bridge 与 session/task/run 聚合；完成后交独立六维 implementation 复审。
