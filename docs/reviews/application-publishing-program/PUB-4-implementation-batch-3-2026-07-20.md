# PUB-4 发布中心与生产链路整合 implementation batch 3（2026-07-20）

状态：`implementation_pass_with_boundary`；batch 3 Entry 已 `entry_passed_with_boundary`，并经独立六维复审。审查记录见 [`PUB-4-implementation-batch-3-review-2026-07-20.md`](PUB-4-implementation-batch-3-review-2026-07-20.md)。本批收缩旧 Step 6，补 resolver runtime fail-closed 与 OpenAPI，保留安全人工交付，不执行真实发布。

## 实现内容

- 旧 `PublishWorkspace` 的平台按钮不再调用 `preparePlatformPublish`；先调用受信 session-only `createPublishPackageFromSessionV2`，成功后只导航 canonical `/publish?package_id=...`；旧页面和复制/下载展示仍保留。
- `/packages/from-session` 只从内部 session store 读取产物，执行 allowlist + media preflight，再登记 AppCenter Artifact/ArtifactVersion 并通过 `create_from_artifact_versions` 生成可复验的 canonical package；不接受前端路径，session 不存在/产物缺失/不可信时 fail-closed。
- `/packages/from-session` 在 handoff 前计算项目、媒体 manifest 与 platform copy 的 fingerprint；同内容只 replay 有效旧包，媒体或文案变化生成新 package 并失效旧 package，避免 session state 变化后错误复用旧内容。
- resolver `GET /api/publish/v2/packages/resolve?artifact_id=`：缺失 404、失效 409、多候选 409，唯一有效 package 才返回 200。
- OpenAPI snapshot 登记 resolver operation、query、200/404/409 responses。
- 新增静态 implementation tests，锁定旧 Step 6 无第二编排、resolver route 顺序与 fail-closed 分支。

## 定向验证

- `npm run test -- --run`：**7 files / 41 tests passed**；build passed（既有 chunk size warning）。
- `uv run pytest -q tests/desktop_publish_capability_test.py tests/publish_v2_api_test.py tests/publish_integration_batch_3_entry_contract_test.py tests/publish_batch3_implementation_test.py`：**13 passed**、12 个既有 Pydantic 弃用警告；包含同内容 replay 与媒体/文案 mutation→新包/旧包失效。
- Ruff 与 `git diff --check`：passed。
- 外部动作：0；未打开浏览器、未扫码/授权、未上传、未创建 PublishRun、未最终发布。

## 独立六维复审

见 [`PUB-4-implementation-batch-3-review-2026-07-20.md`](PUB-4-implementation-batch-3-review-2026-07-20.md)，结论 `implementation_pass_with_boundary`，P0/P1=0。

## 后置边界

真实 Tauri 重启/离开返回、adapter fallback E2E、多候选 resolver 真实运行时证据、跨进程 CAS/锁清理和平台动作仍需后续硬化；本批不关闭 PG-J。
