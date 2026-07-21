# AC-5 数字人口播 implementation batch 4（2026-07-20）

状态：`implementation_pass_with_boundary`；当前批次已完成独立复审，下一批仍须由台账入口显式开启。

## 批次入口

- batch 1、batch 2、batch 3 独立复审均为 `implementation_pass_with_boundary`，P0/P1=0。
- batch 3 已完成既有 legacy session 输出的可信 ArtifactVersion 登记；本批只补齐登记后的 review/accept 与来源指纹收敛，不重新生成或上传媒体。
- `PG-I` 仍未关闭；本批继续保持生产 flag 默认关闭和真实外部动作暂停。

## 本批次目标

1. 为 batch 3 的三类 `imported` ArtifactVersion 建立确定性的 legacy-output fingerprint：同一视频/封面 SHA 与 canonical publish copy 在重启、重试和 replay 中保持一致；不把绝对路径或 provider 字段纳入指纹。
2. 增加显式人工 review/accept 边界：只有同一绑定 AppRun、状态为 `needs_review`、三类 imported outputs 完整且最新 attempt 可审阅时，才允许人工确认进入 `completed`；登记本身不得完成 AppRun。
3. accept/reconcile 重启后保持 session、AppRun、attempt、ArtifactVersion 和 Task 投影一致；重复 accept 幂等，缺 attempt/partial/mixed/fingerprint drift 均 fail-closed。
4. 暴露最小安全 accept API/契约（如需），只返回现有安全投影；不增加 provider、浏览器、抖音授权/上传/最终发布动作。

## 允许修改范围

- `pixelle_video/app_center/ip_broadcast_adapter.py`：legacy output fingerprint、reviewable attempt、显式 accept/reconcile 安全 helper；
- `pixelle_video/app_center/repository.py`：仅为 attempt/指纹一致性所需的原子查询或精确更新；
- `api/routers/ip_broadcast_app.py`、`api/schemas/app_center.py`：最小人工 accept 边界（不自动调用 provider）；
- `docs/contracts/app-center/**`、`tests/app_center_ip_broadcast_*_test.py`、本批 evidence/review。

## 禁止范围

- 不调用 LLM、TTS、RunningHub、数字人 provider、浏览器或抖音；不扫码、不授权、不上传、不发布；
- 不修改旧 `IpBroadcastWorkflow`、StudioApp、PublishRun/PublishPackage、账号、模型配置或桌面 UI；
- 不打开 `digitalHumanInAppCenter`，不新增管理员/RBAC/套餐/支付/多租户控制面；
- 不把人工 accept 误写成真实视频生成或平台发布完成。

## 批次验收

- 合法 batch 3 输出可得到稳定 legacy-output fingerprint，重启后 fingerprint 不变；路径、provider、绝对路径不进入指纹；
- import 创建的 attempt 为 `needs_review`，人工 accept 只在完整 imported outputs + needs_review AppRun 下允许；accept 后 attempt/AppRun/Task 状态一致且不重复；
- 缺 attempt、partial/mixed outputs、fingerprint drift、错误状态和跨项目 binding 均 fail-closed；旧 session 与旧 Artifact 历史保留；
- API 响应不泄露完整 session state、输入、密钥或绝对路径；旧 `/ip-broadcast/sessions/**` 行为不变；
- batch 定向、AC-5/Stage 聚合、Ruff、diff 和独立六维复审通过后，才能决定 PG-I 是否仍需后续 batch；真实 provider/平台证据仍不在本批。

## 实施结果（待独立复审）

- 已实现：legacy output fingerprint（video/cover SHA + canonical publish copy，不含 session/path/provider）、`needs_review` review attempt、显式 `accept_legacy_outputs` 和 `/api/app-center/ip-broadcast/runs/{id}/accept` 安全边界。
- 已覆盖：登记时创建可审阅 attempt；重启/replay 复用同一 fingerprint；缺 attempt、fingerprint drift、partial/mixed、非法状态 fail-closed；accept 只将同一绑定完整 imported outputs 的 AppRun/attempt 置为 `completed`，重复 accept 幂等，session 第 6 步同步为 done；accept 前重新校验受信 file_ref/publish_copy schema、磁盘路径、MIME、大小、SHA 和 archived 状态；通用 complete/complete-review/transition 对数字人统一拒绝，必须走专用安全 accept 投影。
- 未改变：旧 workflow、PublishRun/PublishPackage、provider、浏览器、抖音授权/上传/发布、生产 feature flag 默认值和桌面 UI。
- 证据：AC-5 batch4 定向（artifact/API/entry/adapter）**37 passed**；Stage 相关聚合 **366 passed、12 warnings**；Ruff 与 `git diff --check` 通过。
- 独立复审：[`AC-5-implementation-batch-4-review-2026-07-20.md`](AC-5-implementation-batch-4-review-2026-07-20.md)，结论 `implementation_pass_with_boundary`，P0/P1=0；P2 保留跨进程锁/CAS、锁清理和崩溃 partial 清扫。
- 当前 Gate：`PG-I/implementation_pass_with_boundary`；本批不等价于 AC-5/PG-I Stage 关闭，真实 provider、平台、桌面入口和最终发布保持后置。
