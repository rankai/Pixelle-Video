# DH-QUALITY-2 工作流 A/B 与媒体质量业务实现（2026-07-24）

## 状态

`implementation_pass_with_boundary`。固定输入、Provider task 防重复、一次受控重试计划、媒体质量证据结构和人工接收前完整性检查已实现并通过隔离回归；本批未调用真实 Provider，不能把本地证据解释为图片/视频质量 Gate 通过。

## 已实现

- V2 session 保存 `quality_fixed_inputs` 与 `quality_input_fingerprint`，重启/重试前校验固定事实未被修改。
- 已存在 `digital_human_video_path` 的调度 tick 直接复用，不创建第二个 Provider task。
- 已存在 Provider task 但没有视频时 fail closed；只有记录根因与唯一重试计划后才允许继续。
- 增加 `POST /app-center/ip-broadcast/runs/{app_run_id}/retry-plan`，只登记根因和重试理由，不执行 Provider；每个 V2 Run 最多一次受控重试。
- Provider 适配层在成功和失败结果中都保留 task id 元数据；失败状态落盘为 `retryable_failed`，不会因进程重启而盲目新建任务。
- `quality_evidence_json` 记录 task、创建次数、历史 task、输入指纹、原始/最终视频与封面 SHA、ffprobe、字幕路径/SHA/烧录状态、25/50/75% 抽帧结果、spoken_script、四类 Artifact 完整性和最终发布关闭事实。
- 本地隔离 V2 Executor 与真实 Provider Executor 都要求 `video/cover/publish_copy/spoken_script` 四类结果后才允许人工接收；V1 三 Artifact 兼容路径保持不变。

## 验证

- DH-QUALITY-2 实现与 Entry 合并专测：19 passed。
- 数字人/应用中心/发布相关聚合：130 passed，12 个既有 Pydantic 弃用警告。
- Ruff check、Ruff format、JSON parse、`git diff --check`：通过。

## 边界

- 未执行真实 TTS、RunningHub、FFmpeg 质量抽帧、浏览器、平台或最终发布；`frame_samples` 在隔离伪媒体中明确记录为 unavailable。
- 本批原始实现阶段只完成可审计的执行安全与证据机制，不提升视频工作流 release state；后续真实视频质量门已单独记录于 [`DH-QUALITY-2-video-live-gate-2026-07-24.md`](DH-QUALITY-2-video-live-gate-2026-07-24.md)，并经用户授权将视频提升为 `stable`，但不改变图片默认模式或默认 flag。
- 最终发布自动点击保持关闭；独立六维复审按用户要求延后至 Program 完成。
