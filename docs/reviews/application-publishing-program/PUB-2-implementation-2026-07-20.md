# PUB-CORE / PUB-2 Implementation Evidence

状态：`implementation_pass_with_boundary`

## 实现范围

- `PublishPackageV2`、exact-one source、human-stop policy、稳定 package fingerprint 与失效单向写入。
- 应用中心 ArtifactVersion → immutable package builder；视频/封面可信根、格式探针、hash/size re-verify、symlink reject、opaque `asset_*` token。
- `publish_runs_v2`、`publish_run_step_attempts`、`publish_events` repository；状态 CAS、event cursor、idempotency、同账号/平台串行、旧库 guard/index hardening。
- 异步 run service：preflight、login_required、waiting_for_human、resume、cancel、retry、human outcome、restart recovery、Generic Task redacted projection、profile lock handoff。
- `/api/publish/v2`：package/run/events/resume/verify/retry/cancel/mark-outcome；local capability + origin allowlist；`PIXELLE_PUBLISH_V2_ENABLED=false` 时 V1 保持可用。
- `/api/publish/v2/accounts*`：与 V2 publishing DB 同源的账号 alias、capability guard、稳定账号错误码；`connect/verify/open` 当前明确为同步 bounded probe projection（HTTP 200），不伪装为异步 operation。
- 明确没有平台 selector、上传控件、真实平台探针、最终发布路由或第三方授权动作。

## 验证命令与结果

```text
uv run pytest -q tests/publish_*_test.py tests/coord0_contract_test.py tests/app_center_core_test.py
99 passed, 12 existing Pydantic deprecation warnings

uv run ruff check pixelle_video/services/publish api/desktop_security.py \
  api/routers/publish_v2.py api/schemas/publish_v2.py api/tasks/models.py \
  tests/publish_*_test.py tests/coord0_contract_test.py
All checks passed

git diff --check
passed
```

独立严格审查线程 `/root/pg_a_closure_reviewer_v3` 已完成六维复验：`P0=0`、`P1=0`，结论为 `implementation_pass_with_boundary`；封面 exactly-one、OpenAPI schema parity、V2 账号 route parity/稳定错误码和 bounded probe 状态语义均已增量复验。详见 [`PUB-2-implementation-review-2026-07-20.md`](PUB-2-implementation-review-2026-07-20.md)。

## 关键边界证据

| 检查 | 证据 |
| --- | --- |
| 重复 package/run | stable fingerprint；同 idempotency 返回同 run；不同包/同账号平台返回 `RUN_ALREADY_ACTIVE` |
| 媒体 | 未信任路径、缺失、坏 magic、同根 symlink、hash/size 变化均 fail-closed；预检失败不调用 executor |
| 状态/事件 | queued-first、CAS、事件 state/version 校验、同事务 transition+event、cursor 单调递增 |
| retry | 新 attempt 行、run attempt +1、失败/成功终态不可覆盖、CAS 回滚不留孤儿事实 |
| 恢复/锁 | queued/running/waiting_human 可转 needs_attention；等待人工期间保持 profile lock，terminal/restart 释放 |
| 安全 | event payload allowlist；不持久化 cookie/QR/凭证/绝对路径/业务文案；from-session 禁止任意 path；V2 capability/origin/flag |
| 人工停手 | 只有 `mark-outcome` 可登记 succeeded；没有 final-publish API；未认证账号进入 `waiting_for_login` |

## 未声称内容

本证据不代表抖音 selector、平台级登录探针、真实上传、最终人工发布或 PUB-DOUYIN 已完成；这些仍按上位台账排队。
