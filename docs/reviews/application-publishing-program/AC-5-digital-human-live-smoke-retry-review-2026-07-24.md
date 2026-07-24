# AC-5 数字人真实 retry 独立六维复审（2026-07-24）

## 结论

`passed_with_boundary`。P0=0，P1=0，实质性 P2=1。

本复审为只读复核，未修改代码或证据。审查对象是余额恢复后对同一 queued AppRun 的唯一一次真实 retry，并同时核对前一次余额失败/重试 JSON。

## 六维结果

1. **需求完整性：通过**
   - 隔离双开关、Edge TTS→RunningHub→后期链路、video/cover/publish_copy Artifact、重启恢复、人工 accept 和最终发布停手均有证据。
   - 同一 project/AppRun/session/idempotency 被复用；前次余额失败后的无产物 accept=409 边界仍保留。

2. **逻辑正确性：通过**
   - `execute_provider` 串联 voice、digital_human、postproduction，并在 `needs_review` 停止。
   - generated Artifact 的三类登记、fingerprint、accept 前置校验和平台发布隔离符合契约。

3. **边界情况：通过（有界）**
   - flag-off/readiness fail-closed、余额失败→跨重启 failed→一次 retry→queued、无产物 accept=409 均有既有证据。
   - 本次只验证 blank_project；copywriting/selected_title 的真实 provider 运行和平台发布仍不在范围内。

4. **代码质量：通过**
   - 本批无业务代码变更；证据 JSON、SQLite、session 和媒体文件互相吻合。
   - 真实运行复用既有锁、绑定、trusted-root、MIME/签名/SHA 校验和安全响应边界。

5. **测试覆盖：通过（有界）**
   - AC-5 定向 API/adapter/artifact：47 passed，保留 12 个既有 Pydantic 弃用警告。
   - 应用中心前端：18 passed；desktop build、`git diff --check`、JSON 校验通过。
   - 真实 RunningHub 不重复纳入自动回归；没有把一次 live smoke 外推为平台发布或持续稳定性保证。

6. **实际运行结果：通过（有界）**
   - RunningHub task `2080465311014019073` 成功，331 秒完成。
   - 独立复算数字人视频、最终视频、封面 SHA 与证据一致；`ffprobe` 确认最终视频为 H.264/AAC、1080×1920、8.544 秒，封面为 1080×1920 PNG。
   - 三个 Artifact 均为 `generated`/`ready`；重启后 state/version/Artifact IDs 保持；accept 200 后 AppRun=`completed`/version 8。
   - `final_publish_clicked=false`、`platform_actions=0`。

## P2 与后续

首次真实进程关闭时出现 Playwright browser cleanup 异常，未损坏业务状态，重启后的第二次关闭为 clean，因此不升 P1。但 `HTMLFrameGenerator.close_browser()` 仍应在后续维护批次补 exception-safe、幂等清理和模拟 close failure 测试。

本批可以收口 AC-5 真实 Provider/Artifact Gate；不能据此开启默认双开关、平台自动发布或声称多平台发布完成。

## 验证依据

- [`AC-5-digital-human-live-smoke-retry-2026-07-24.json`](qa/AC-5-digital-human-live-smoke-retry-2026-07-24.json)
- [`AC-5-digital-human-live-smoke-2026-07-24.json`](qa/AC-5-digital-human-live-smoke-2026-07-24.json)
- 隔离目录：`/tmp/pixelle-digital-human-retry-Sp7dyH`
- 审查者：独立应用中心审查线程（只读）
