# PROGRAM-ROLLOUT implementation batch 8：1 小时用户式观察收口（2026-07-21）

## 结论

`implementation_pass_with_boundary` 候选，等待独立六维复审。1 小时稳定观察窗口本身已完成，但 PG-L 仍不能关闭：产品负责人正式签署、Windows、真实平台回滚和原生 WebView/生产 SLA 仍是独立边界。

## 策略与实际时间

- 当前有效策略：至少 1 小时，见 [`PROGRAM-ROLLOUT-observation-window-policy-amendment-2026-07-21.md`](PROGRAM-ROLLOUT-observation-window-policy-amendment-2026-07-21.md)。
- 原始起点：`2026-07-21T10:57:15.650469Z`；本次检查：`2026-07-21T13:46:22.413509Z`；实际经过 `2.819` 小时；起点未修改。

## 用户式本地操作与证据

- Playwright headless 打开真实 React `/apps/digital-human-video` 路由并循环 10 次；每次读取 100 个项目，切换“已有文案”并读取 10 个来源素材；本地 UI 交互 20 次。
- 隔离 FastAPI 通过 100 个项目 API 回读和 100 个项目的 1,000 个素材回读；UI 路由 10 次 p95 `435.765 ms`。
- 隔离 publish V2 local-noop 20 次 durable create-run，逐条校验同一 `run_id`、`queued` 状态和 `state_version`，20/20 state readback；最大 create `7.374 ms`。
- observed version 从 `desktop/src-tauri/tauri.conf.json` 读取为 `pixelle-video-desktop@0.1.0`；release binary 存在且 build SHA-256 `3397e254460b959acf75dab084b30e9d02bc2c1d1004942a93faa9857ecdab9b`，`build_verified=true`。
- 本地可执行范围内 P0/P1、重复上传、误点最终发布均由 UI/API/no-op 结果计算为 0；profile 损坏未执行（无 profile 打开路径），明确记录为 `not_executed`，不是伪造的 0；executor/browser/external/final publish 均为 0。
- 观察 API 8112 与用户式 API/UI 端口分别通过 socket bind 检查；app center、Generic Task、publishing、ip_broadcast_sessions 四类用户持久化路径前后快照不变、mutations=0。

证据：[`qa/PROGRAM-ROLLOUT-observation-readiness-2026-07-21.json`](qa/PROGRAM-ROLLOUT-observation-readiness-2026-07-21.json)；执行脚本：[`scripts/program_rollout_user_simulation.py`](../../../scripts/program_rollout_user_simulation.py)。

## 保留边界

本批是本机隔离 API/UI/no-op 用户式观察，不等价真实第三方平台发布、生产 WebView、Windows 构建或云端多租户。产品负责人 sign-off 仍为 `pending`；默认发布 V2 和抖音灰度仍关闭/0%。
