# PROGRAM-ROLLOUT implementation batch 2：诊断、telemetry、隐私与回滚边界（2026-07-21）

状态：`implementation_pass_with_boundary_candidate`；本批落地 content-free 本地 telemetry、诊断路径脱敏和已有 V1/V2 rollback smoke 的可执行断言，不开启默认 rollout。

## 实现

- 新增 `desktop/src/rolloutTelemetry.ts`：只允许 platform、adapter_version、step、error_code、duration_bucket、app_version；local-only、500 条上限、无网络上传；
- 发布中心 V2 与旧 fallback 入口记录无内容 telemetry，不记录标题、描述、账号、cookie、路径、signed URL 或媒体内容；
- `/api/desktop/diagnostics` 不再返回配置绝对路径，检查消息不泄露 output 绝对路径，并显式返回 `local_only/raw_path_redacted/secrets_redacted`；
- 新增 telemetry、诊断隐私和 V1/V2 rollback fixture 断言；保留 V2 flag 关闭时旧入口/复制下载/历史可读的既有回退契约。

## 定向验证

- `npm test -- --run`：10 files / 53 tests passed；
- `npm run build`：通过；仅保留既有 bundle size warning；
- `uv run pytest -q tests/desktop_api_test.py`：6 passed，12 个既有 Pydantic warnings；
- `uv run pytest -q tests/program_rollout_privacy_rollback_test.py tests/program_rollout_entry_contract_test.py`：4 passed；
- Ruff、JSON parse、`git diff --check`：通过。

## 边界与未完成项

- 本批没有上传 telemetry、没有默认开启发布 V2、没有改变 Douyin gray 0% 或其他平台 release state；
- macOS/Windows packaged lifecycle、10×重启/10×run/crash/lock soak、真实性能、双向真实 smoke 和 7-day observation window 后置；
- 不执行扫码、第三方授权、最终发布或 profile/session 删除。

## 下一入口

交独立六维 implementation 复审；通过后进入 rollout batch 3（本地 packaged lifecycle、soak、性能和 rollback rehearsal），不得把本批误记为 PG-L。
