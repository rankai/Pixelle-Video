# COORD-0 应用中心/桌面页面 Playwright 基线

日期：2026-07-19；执行者：主线程；结果：`partial_pass`

本证据覆盖浏览器开发模式的只读导航、核心流程导航录像，以及一次使用既有有效缓存媒体的真实成片任务录像；不代表 Tauri 打包版或发布 Gate 通过。

## 运行条件

- FastAPI：`127.0.0.1:8100`；Vite：`127.0.0.1:1420`；`PIXELLE_ASSET_CENTER_V2=true`；
- 一次 Playwright headless 浏览器运行；起始时间 `2026-07-19T00:46:19.644071+00:00`，结束时间 `2026-07-19T00:46:25.758769+00:00`；
- 运行中没有控制台错误；没有创建任务、上传素材、删除数据或点击发布，但前端自动执行了 `POST /api/ip-broadcast/sessions` 初始化请求；
- 页面导航顺序：工作台 → 口播剪辑 → 企业资产库 → 发布中心 → 任务记录；非首页页面各点击一次侧栏入口。

## 核心导航录像

同一次独立 Playwright 运行录制了工作台 → 口播剪辑 → 企业资产库 → 发布中心 → 任务记录 → 工作台的只读导航录像；未创建任务、生成媒体、上传素材、删除数据或点击发布。录像完整性经 `ffprobe` 验证，VP8、1440×1000、时长约 7.4 秒；归档文件：[`COORD-0-core-navigation.webm`](./qa/app-baseline/COORD-0-core-navigation.webm)，SHA-256 `da573d17e8c579616e8e41553539f887fb8abc51248922ba63f45347568f5d72`。

另一次独立 Playwright 运行录制了口播剪辑内部五步流程导航：文案与分段 → 配音 → 出镜 → 成片 → 发布 → 返回文案与分段；6 次有意点击，控制台错误为 0，未点击“自动继续生产”、未调用生成接口。录像经 `ffprobe` 验证为 VP8、1440×1000、6.24 秒；归档文件：[`COORD-0-core-production-navigation.webm`](./qa/app-baseline/COORD-0-core-production-navigation.webm)，SHA-256 `8e2c95cc61b1edaa55d8f180c6c1ffe26c1ba58d868884e8bc500f298e374752`，事件摘要见 [`COORD-0-core-production-navigation.json`](./qa/app-baseline/COORD-0-core-production-navigation.json)。这是一段安全的五步流程导航录像，不是数字人生成或发布任务录像。

另一次独立 Playwright 运行在预填既有有效音频/数字人视频的 session 上点击“一键成片”，真实创建并完成 `postproduction` Task，生成最终视频、封面、脚本和发布包 JSON；录像在发布前安全停手，未点击任何平台最终发布动作。完整事件、任务 ID、产物和边界见 [`COORD-0-core-production-task-2026-07-19.md`](./COORD-0-core-production-task-2026-07-19.md)。

## 页面证据

| 页面 | URL | 点击数 | 自动化耗时 | 截图 |
| --- | --- | ---: | ---: | --- |
| 工作台 | `http://127.0.0.1:1420/` | 0 | 91 ms | [`COORD-0-app-workspace.png`](./qa/app-baseline/COORD-0-app-workspace.png)；SHA `d6d68ee35c023a85d88880d68cc7c7f6bbd631fa4b46258be7ee508b4d87dcea` |
| 口播剪辑 | `http://127.0.0.1:1420/` | 1 | 1115 ms | [`COORD-0-app-voice.png`](./qa/app-baseline/COORD-0-app-voice.png)；SHA `d90bdaef2d94796e50eecf2be5937c5c9cc3bbec30925e569e40f4438dfcaeec` |
| 企业资产库 | `http://127.0.0.1:1420/` | 1 | 968 ms | [`COORD-0-app-assets.png`](./qa/app-baseline/COORD-0-app-assets.png)；SHA `b5a93e9eb92e096141ec97d979ed2aa4f190a7576f35bf9599a025f7f82433e4` |
| 发布中心 | `http://127.0.0.1:1420/` | 1 | 1004 ms | [`COORD-0-app-publishing.png`](./qa/app-baseline/COORD-0-app-publishing.png)；SHA `4219154c53d66fdfc5caa4678526bcfaa3b4a6250f116ed8e2e27022616859ca` |
| 任务记录 | `http://127.0.0.1:1420/` | 1 | 1202 ms | [`COORD-0-app-tasks.png`](./qa/app-baseline/COORD-0-app-tasks.png)；SHA `a5dfd39bbceea199072549d0809f1fd4057590183fd177ebad11ee6a17f8e2e5` |

## 判定边界

- 页面/导航基线通过；
- 发现并记录一个 legacy 副作用：`recoverAppState()` 在首次加载时自动创建 IP 口播 session。FastAPI 运行日志出现 `POST /api/ip-broadcast/sessions`，近期 `data/ip_broadcast_sessions/` 可见 6 个对应时间窗口内更新的 JSON 文件；采集前未做目录快照，因此不把 6 个文件全部归因于本次单次运行，也不删除它们；
- 已录制只读核心入口导航视频、口播五步流程导航视频和一次真实成片任务视频；真实任务使用既有缓存媒体，未覆盖全新 LLM/TTS/数字人 provider 生成、任务重试、桌面重启或发布，因此 AC-0 和 PG-A 仍是 `partial_pass / blocked_external_manual`；
- 发布中心显示的四个平台“可用”属于既有 V1 文案，仅作当前基线，不能标识 V2 平台 available；
- 截图已排除账号身份和外部平台账户隐私，后续若补录视频需继续脱敏。
