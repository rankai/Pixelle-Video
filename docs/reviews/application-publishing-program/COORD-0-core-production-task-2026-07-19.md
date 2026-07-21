# COORD-0 核心生产任务录像

日期：2026-07-19；执行者：主线程；结果：`passed_with_boundary`

## 目的与边界

这是一次有明确目的的真实任务执行录像：在当前桌面工作台预填一条已确认口播稿、既有有效音频和既有有效数字人视频，进入“成片”步骤点击唯一的“一键成片”，等待 FastAPI TaskManager 完成后停在“发布前安全停手”。

本次验证覆盖真实 UI → FastAPI → TaskManager → FFmpeg/字幕/封面 → 发布素材包链路；没有点击抖音“打开抖音”或任何最终“发布”按钮。由于 COORD-0 禁止新增业务实现，本次使用已有缓存媒体验证渲染与交付，不把它扩写为从 LLM、TTS、数字人 provider 全新生成的端到端证据。

## 运行条件

- API：`http://127.0.0.1:8100`；Vite：`http://127.0.0.1:1420`；Playwright Chromium，viewport `1440×1000`。
- session：`11fb418e06664fa2a4d214f64c5f736b`。
- Task：`f1edf647-4d4d-45e9-a845-4a46203514b7`，`step_key=postproduction`，`status=completed`，`duration_ms=14029`。
- 输入媒体均为已有有效缓存：音频 MP3、数字人 MP4；没有上传外部文件、没有调用抖音。
- 关键 UI 动作：进入“口播剪辑” → 选择“成片” → 点击唯一按钮“一键成片”；未点击任何最终发布动作。

## 通过证据

| 项目 | 结果 |
| --- | --- |
| 任务启动 | 页面按钮计数为 1，`compose_clicked=true` |
| 任务执行 | 页面保持在工作台，轮询 14 秒后显示“步骤执行完成” |
| 任务状态 | TaskManager `completed`，进度 `3/3` |
| 产物 | `final_video`、`cover`、`script`、`publish_package_json` 均生成；session `completed_steps=5`、`next_action=publish` |
| 发布安全边界 | 录像结果 `final_publish_clicked=false`；页面停在“发布前安全停手”，只展示“打开抖音”入口 |
| 控制台 | `console_errors=[]` |

## 归档

- 任务录像：[`COORD-0-core-production-task.webm`](./qa/app-baseline/COORD-0-core-production-task.webm)，SHA-256 `3a1f9a6bca0ad3d11f24a3902087ba8d243e3d9184908ba4777d7403d8d96cf8`；VP8、800×554、21.76 秒。
- 完成态截图：[`COORD-0-core-production-task-final.png`](./qa/app-baseline/COORD-0-core-production-task-final.png)，SHA-256 `6821af260a1b4ca60e94041659d86fe6f686c661805f4ecf806ddc9e9cee59a6`。
- UI 结果摘要：[`COORD-0-core-production-task.json`](./qa/app-baseline/COORD-0-core-production-task.json)，SHA-256 `a65bfafb9e93551c5d12e2b3ddb5ab31fc2931949e6a8c86936a3ca5e959dcb2`。
- session/task 结果：[`COORD-0-core-production-task-session.json`](./qa/app-baseline/COORD-0-core-production-task-session.json)，SHA-256 `4cfe998d7449a2d54ee3794a435197acca9f74b778b11ac98b93c81f0034337a`。
- 完整 Task API payload：[`COORD-0-core-production-task-api.json`](./qa/app-baseline/COORD-0-core-production-task-api.json)，SHA-256 `dd3503a3974efb33d2334e8a1ea7b48161f9037773dc8b32b4ed58c2cde3b949`；已检查无 API key、cookie、账号身份或平台 token。

## 判定

本证据将 AC-0 的“真实生产任务录像”从缺失提升为 `passed_with_boundary`：真实成片与交付包链路已跑通，但不替代首次扫码、抖音中途关闭恢复，也不证明 LLM/TTS/数字人 provider 的全新生成链路。PG-A 仍需这些外部/后续阶段条件，不得据此放行业务实现。
