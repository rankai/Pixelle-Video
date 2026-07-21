# AC-5 数字人口播 implementation batch 6 实现记录（2026-07-20）

状态：`implementation_pass_with_boundary`；Entry 已通过 `entry_passed_with_boundary`，实现已完成独立六维复审。

## 实现目标

- 将 legacy session 与新 `ArtifactVersion` 输出统一到同一 canonical package handoff identity；
- 复用既有 PublishPackage V2 / PublishCoreRepository / `publish_package_ref` 事实源，不创建第二套发布包；
- 同一内容/版本重放不重复创建 video artifact、package 或 active ref；新内容版本使旧 package/ref 失效；
- 验证旧 session 显式恢复到同一 AppRun，以及 blank/copywriting/selected_title 三来源隔离 handoff；
- 仅本地/隔离 fixture 与 TestClient/Repository E2E，不调用 provider、浏览器或平台。

## 允许修改文件

- `pixelle_video/services/publish/package_service.py`：canonical package fingerprint、legacy/artifact snapshot 收敛、
  ref 幂等/失效边界；
- `pixelle_video/services/publish/core_repository.py`：仅为 package idempotency/失效状态所需的精确查询；
- `pixelle_video/app_center/ip_broadcast_adapter.py`：仅在 handoff 所需的 accepted output/source projection 接线；
- `api/routers/publish_v2.py` 或 `api/routers/ip_broadcast_app.py`：必要的安全 handoff projection，不新增真实动作；
- `tests/app_center_ip_broadcast_*_test.py`、`tests/publish_package_service_test.py`、`tests/publish_v2_api_test.py`；
- 本批 contract/fixture/evidence/review 文档。

## 禁止修改

- `IpBroadcastWorkflow` 核心步骤、StudioApp/桌面 UI、PublishRun 状态机、账号/模型配置；
- `digitalHumanInAppCenter` 默认值、真实 LLM/TTS/数字人 provider、Playwright/EgoLite、抖音授权/上传/发布；
- 管理后台、RBAC、套餐、支付、多租户和任何新的模型事实源。

## 实现验收

1. canonical package fingerprint 只由 contract 指定的 project/schema/video SHA/cover SHA/canonical copy 构成；
2. legacy 与 artifact source 仅审计字段不同，同内容 package fingerprint 相同；
3. 同一 package replay 返回同 package/fingerprint，同一 ref replay 不新增 active ref；
4. 新 ArtifactVersion/内容指纹生成新 package，并同时失效旧 package 与旧 ref；
5. legacy session 显式 claim/restart/old-entry duplicate 保持同一 AppRun、Task、ArtifactVersion，跨项目/drift fail-closed；
6. blank/copywriting/selected_title 三来源在隔离 executor→explicit accept→package handoff 中通过，waiting/needs_review 不完成；
7. retry 部分写入只补偿当前 attempt 新对象，旧 package/ref/artifact 历史保留；
8. 定向、Stage 聚合、Ruff、diff 和独立六维 implementation review 全部通过后，才能判断 PG-I 是否关闭。

## 实施结果与证据

- `PublishPackageService` 统一 video/cover/平台文案的 canonical package fingerprint；source kind、
  session/source revision、绝对路径、artifact ID 等仍保留为审计/绑定事实，不改变跨来源 delivery identity。
- legacy package 补齐 cover artifact ref；artifact handoff 在 legacy-first replay 时传入 source version IDs，
  可创建唯一合法 `publish_package_ref`；同 package/ref replay 不追加重复 ref。
- package service 自动识别同项目 artifact source 的版本替换，并同时失效旧 package 与 ref；完整
  `artifact_id -> artifact_version_id` map 防止同版本不同封面误伤；相同 source map 的 platform_copy
  canonical fingerprint 变化也会失效旧 package/ref。
- stale replay 命中已失效 package 时 fail-closed 为 `PUBLISH_PACKAGE_STALE`，不会误伤当前 active package/ref。
- `publish_copy` ArtifactVersion 自动解析为 PlatformCopy；重复、空/空白文案或话题、类型错误、显式
  platform_copy 不一致均 fail-closed；Publish V2 API 在未提供 `platform_copy` 时传 `None`，允许从 artifact
  文案自然 handoff，并有 TestClient E2E。
- Carousel 原有 source-specific fingerprint 与 replacement 失效规则保持不变。
- 定向证据：package/core/models/V2 API/AC-5 adapter/API/artifact/handoff **70 passed、12 warnings**；
  独立审查线程复跑 **67 passed、12 warnings**；Ruff 与 `git diff --check` 通过。
- 覆盖 legacy-first、v1→v2→v1 stale replay、同版本不同封面、platform_copy 变化、publish_copy
  解析/空值/重复/mismatch、API omission 和旧 package/ref 失效。
- 未调用 LLM/TTS/数字人 provider、浏览器、抖音授权/上传/最终发布；未改旧 workflow、StudioApp、
  PublishRun 状态机、账号或模型配置。

## 独立六维复审

- 复审记录：[`AC-5-implementation-batch-6-implementation-review-2026-07-20.md`](AC-5-implementation-batch-6-implementation-review-2026-07-20.md)。
- 独立审查线程最终结论：`implementation_pass_with_boundary`，P0/P1=0；其复跑定向 67 passed/12 warnings，
  父集定向 70 passed/12 warnings，Ruff 与 `git diff --check` clean。
- API optional `platform_copy` 最新修复已由 TestClient E2E 复验；审查确认 canonical、跨 source、copy、
  package/ref 幂等失效、stale、同版本不同封面和 legacy-first 边界均通过。

## 当前 Gate

`APP-IPB/PG-I implementation_pass_with_boundary`（batch 6 已完成；PG-I 仍需 Stage 级 AC-F/桌面灰度与
真实 provider/platform 边界证据，未进入 PUB-INTEGRATION）。
