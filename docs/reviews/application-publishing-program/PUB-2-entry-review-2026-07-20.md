# PUB-2 Entry — PublishPackage / PublishRun / recovery skeleton

状态：`entry_passed_with_boundary`

来源：用户显式授权；当前台账唯一入口已切换为 `PUB-CORE`。

## Scope

本阶段实现不可变 PublishPackage V2、媒体预检与 fingerprint、PublishRun/Step/Event 持久化、异步 orchestrator、取消/resume/idempotency、Generic Task 投影、V2 API/UI 轮询、local capability/path hardening、V1 adapter 与 feature flag。

## Hard boundary

本阶段不实现平台 selector、上传、字段填充、真实平台级 `probe_login_state()`、抖音最终发布、图文/数字人、全局导航、管理员/RBAC/套餐/支付或第二浏览器运行时。最终发布动作必须继续由 FinalActionGuard 拒绝并停在 `waiting_for_human`。

## Entry contract

- PublishPackage V2 只能由 publishing 域持有，应用中心只保存 `publish_package_ref`。
- source 必须 exactly-one：`artifact_versions` 或 `legacy_session`；不可变 package 保存 source revision、artifact refs、media manifests 和 fingerprint。
- PublishRun 是发布状态唯一事实源；Generic Task 仅投影，不复制 request/result/绝对路径/凭证。
- 所有 run 强制 `human_confirmation_required=true`；`waiting_for_login`、`waiting_for_human`、`needs_attention` 不得映射为成功。
- API 创建必须快速返回 run_id/task_id；双击同一 idempotency key 不得创建重复 run；重试创建新 attempt，不覆盖旧证据。
- 可信路径、symlink、媒体格式/尺寸/存在性由本地预检拒绝；预检失败不得打开浏览器。
- V2 关闭后 V1 adapter 可读/可用，V2 数据不删除、不回写应用中心。
- Canonical API base is `/api/publish/v2`; run creation returns `202` and exposes events/resume/verify/retry-step/cancel/mark-outcome, with no final-publish route.
- SQL uses `publish_events` and `publish_run_step_attempts` (`UNIQUE(run_id, step, attempt)`), active-run uniqueness and immutable-package triggers; state updates will use optimistic `state_version` compare-and-set.
- JSON Schema/TypeScript use the `human_confirmation` object plus `state_version`/`attempt`/`current_step`/timestamps; SQL normalized columns are storage mapping only.
- Media manifests, when present, require hash/size/MIME and opaque `asset_*` path tokens; no arbitrary local path is accepted in package contracts.
- Mutating local APIs require a short-lived Tauri capability token and strict origin allowlist; missing/expired token and wrong origin have separate 403 codes. V2 flag defaults off and V1 rollback remains available.
- Event payloads are allowlist-sanitized before persistence; unknown fields and Cookie/QR/credential/absolute-path/business-copy fields are rejected. This is a mandatory PG-F implementation check, not a claim that the current legacy publisher is sanitized.

## Initial failure matrix

`SOURCE_INVARIANT_INVALID`、`PACKAGE_IMMUTABLE`、`MEDIA_NOT_FOUND`、`MEDIA_UNTRUSTED_PATH`、`MEDIA_INVALID`、`IDEMPOTENCY_CONFLICT`、`RUN_STATE_INVALID`、`RUN_ALREADY_ACTIVE`、`LOGIN_REQUIRED`、`FINAL_ACTION_BLOCKED`、`V2_DISABLED`。

## Gate target

PG-F 需要证明：创建 run 快速返回；重启可恢复；双击不重复；同 profile 不并发；任意路径/symlink 被拒；无效媒体不打开浏览器；`login_required` 不会变成 `completed`；关闭 V2 后 V1 回退可用。真实平台 selector/probe 证据留到后续 PUB-DOUYIN。

独立严格审查线程结论：`entry_passed_with_boundary`，P0/P1=0；`uv run pytest -q tests/publish_core_entry_contract_test.py tests/coord0_contract_test.py`：26 passed；Ruff/diff clean。现在允许进入 PUB-2 业务实现，但不得把该 Entry 结论误报为 PG-F、真实浏览器或平台通过。
