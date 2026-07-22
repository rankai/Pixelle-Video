# PROGRAM-ROLLOUT implementation batch 3：本地生命周期、打包与性能基线（2026-07-21）

状态：`implementation_pass_with_boundary`；完成本地 sidecar 10×生命周期与 1/15/60 秒媒体预检基线，完成 macOS sidecar/Tauri release build；Windows 与稳定观察窗仍是明确后置边界。

## 实际证据

- `uv run python desktop/scripts/build_sidecar.py`：通过，重新生成 arm64 sidecar；
- `PATH=/Users/nickfury/.cargo/bin:$PATH npm run tauri build`：通过，完成 macOS release binary；
- `uv run python scripts/program_rollout_lifecycle_smoke.py`：10/10 本地 sidecar 周期通过；每周期 health=healthy、主动 SIGTERM、端口释放、external_actions=0、browser_actions=0、final_publish_clicks=0；生命周期 probe 使用临时 `PIXELLE_DESKTOP_TASKS_DB`，全局 `data/desktop_tasks.sqlite` 前后签名不变；
- `uv run python scripts/program_rollout_performance_smoke.py`：1/15/60 秒各 10 样本，记录 media preflight p50/p95：
  - 1 秒：0.074 / 0.883 ms；
  - 15 秒：0.078 / 0.190 ms；
  - 60 秒：0.108 / 0.254 ms；
- 桌面全套 Vitest：10 files / 53 passed；desktop API：6 passed；Entry/隐私/回滚定向测试：4 passed；Ruff、JSON、diff clean。

## 边界

- 10×是本地 sidecar 生命周期，不等价 10×原生 WebView 黑盒重启或 10×真实平台发布 run；
- 性能数字只代表本机媒体预检本地开销，不代表平台上传/处理 SLA；create-run/account-list/UI-state p95 仍需下一批补齐；
- Windows 构建在当前 macOS 环境明确 deferred；产品负责人签字、7 天/20 run 稳定观察窗、crash/lock contention soak 和双向真实 runtime rollback 尚未关闭；
- 没有扫码、第三方授权、浏览器动作、平台上传、最终发布或破坏性清理。

## 下一入口

交独立六维 implementation 复审；若通过，进入 batch 4，补 crash/lock contention 与 API/UI 性能、rollback rehearsal 和最终 PG-L evidence 汇总。
