# DH-QUALITY-2 视频模式真实质量门（2026-07-24）

## 结论

视频模式 `video_lipsync/natural` 已完成一次有目的的真实 RunningHub 生成和成片验收，结果为 `passed_with_boundary`。根据用户明确授权，工作流 release state 从 `candidate` 提升为 `stable`；图片自然度候选仍保持 `candidate`，图片稳定模式仍是默认工作流。这里的 `stable` 表示视频工作流本身稳定，不改变默认模式选择。

本次只验证视频质量和产物完整性，不执行平台上传或最终发布，也不把本次 bounded visual gate 误报为 Program 完成后的独立六维总审查。最终发布按钮仍由人工确认，自动点击保持关闭。

## 真实运行

- workflow：`video_lipsync/natural` → `digital_lip_sync_video.v1`
- Provider task：`2080534254718251010`，`succeeded`，创建 1 次，重试 0 次
- AppRun：`run_79b3d2f8ad0f480b8f269656552bb13d`
- TTS：本地 Edge TTS 成功；未重复调用
- 产物：`final_video`、`cover`、`publish_copy`、`spoken_script` 四项均已登记
- 成片规格：1080×1920、H.264/AAC、25fps、6.12s；音频 6.101s，在允许的时长误差内
- 字幕：`readable_v2`，已烧录进视频，25/50/75% 抽帧可读且处于安全区

## 视觉验收

对同一成片的 25%、50%、75% 抽帧逐一检查：

| 项目 | 结果 | 说明 |
| --- | --- | --- |
| 字幕 | 通过 | 白字/深色底，清晰、无遮挡、不贴边 |
| 人物边缘 | 通过 | 未观察到严重黑白抠像边、光晕或锯齿 |
| 口型 | 通过 | 嘴部开合与语音段落一致，无明显卡顿或错位 |
| 背景 | 通过 | 背景连续稳定，无黑白 matte 或撕裂 |
| 动作 | 通过 | 手部运动存在自然运动模糊，不属于身份/背景瑕疵 |
| 封面 | 通过 | “门店短视频这样讲”短标题可读，未回退到脚本前缀 |

截图证据：[`qa/DH-QUALITY-2-video-live-gate-2026-07-24/`](qa/DH-QUALITY-2-video-live-gate-2026-07-24/)。机器可读证据：[`qa/DH-QUALITY-2-video-live-gate-2026-07-24.json`](qa/DH-QUALITY-2-video-live-gate-2026-07-24.json)。

## 边界与后续

1. 视频 workflow 已为 `stable`，但 `default_mode=false`；默认仍为图片稳定模式，最终发布仍由人工确认。
2. Program 级独立六维终审按用户要求延后至整体方案完成，当前不伪造该结论。
3. 平台动作、上传、最终发布点击均为 0；本证据不能外推为抖音、快手、视频号或小红书发布成功。
4. 后续若更换 RunningHub workflow、人物/视频输入或字幕模板，必须重新执行同等质量门。
