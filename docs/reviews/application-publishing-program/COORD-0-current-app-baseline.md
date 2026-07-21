# COORD-0 应用中心/桌面基线（历史只读导航快照）

本文件保留 `2026-07-19T00:46Z` 的只读导航快照；其中“未执行真实生成/Tauri 重启”只对该快照成立，不代表当前 COORD-0 总体事实。当前补充证据见 [`COORD-0-app-baseline-playwright-2026-07-19.md`](./COORD-0-app-baseline-playwright-2026-07-19.md)、[`COORD-0-core-production-task-2026-07-19.md`](./COORD-0-core-production-task-2026-07-19.md)、[`COORD-0-tauri-sidecar-restart-2026-07-19.md`](./COORD-0-tauri-sidecar-restart-2026-07-19.md) 和 [`COORD-0-first-scan-passed-2026-07-19.json`](./qa/COORD-0-first-scan-passed-2026-07-19.json)：真实成片任务已 `passed_with_boundary`，Tauri/sidecar 重启和首次扫码已通过；中途恢复失败作为旧路径基线交 PUB-2，不在本阶段重试。现有资产中心历史基线仍可参考 `docs/reviews/2026-07-18-asset-center-ux0-evidence.md`，但它不是本次应用中心/发布联合基线。

## 当前状态指针

- 该文件的下述运行记录与“尚未覆盖”清单是历史快照，不得覆盖实时台账；
- 实时唯一工作入口和 Gate 状态以 [`2026-07-18-application-center-publishing-program-progress.md`](../2026-07-18-application-center-publishing-program-progress.md) 为准；
- 真实成片任务录像明确使用既有有效缓存媒体，不等价于全新 LLM/TTS/数字人 provider 生成，也不包含最终平台发布。

## Playwright 浏览器基线

运行环境：项目已有 FastAPI（`127.0.0.1:8100`）和 Vite 浏览器开发模式（`127.0.0.1:1420`），`PIXELLE_ASSET_CENTER_V2=true`；没有修改代码、创建任务、上传素材或点击提交/发布按钮。但前端 `recoverAppState()` 在加载工作台/口播页时自动调用 `POST /api/ip-broadcast/sessions`，FastAPI 日志明确出现该请求，并在 `data/ip_broadcast_sessions/` 写入本地 session JSON；这属于当前 legacy 行为，不能称为完全无副作用。使用一次 Playwright headless 浏览器运行依次打开工作台、口播剪辑、企业资产库、发布中心和任务记录；每个导航只点击一次。

运行时间（UTC）：`2026-07-19T00:46:19.644071+00:00` – `2026-07-19T00:46:25.758769+00:00`；浏览器控制台错误：`0`。

| 页面 | 结果 | 点击数 | 自动化耗时 | 截图 SHA-256 |
| --- | --- | ---: | ---: | --- |
| 工作台 | passed | 0 | 91 ms | `d6d68ee35c023a85d88880d68cc7c7f6bbd631fa4b46258be7ee508b4d87dcea` |
| 口播剪辑 | passed | 1 | 1115 ms | `d90bdaef2d94796e50eecf2be5937c5c9cc3bbec30925e569e40f4438dfcaeec` |
| 企业资产库 | passed | 1 | 968 ms | `b5a93e9eb92e096141ec97d979ed2aa4f190a7576f35bf9599a025f7f82433e4` |
| 发布中心 | passed | 1 | 1004 ms | `4219154c53d66fdfc5caa4678526bcfaa3b4a6250f116ed8e2e27022616859ca` |
| 任务记录 | passed | 1 | 1202 ms | `a5dfd39bbceea199072549d0809f1fd4057590183fd177ebad11ee6a17f8e2e5` |

截图目录：`docs/reviews/application-publishing-program/qa/app-baseline/`。

页面基线确认：工作台展示项目/生产队列/企业资产；口播剪辑展示五步生产流程；资产库展示视频素材；发布中心展示四个平台 legacy V1 “可用”文案和最终人工确认边界；任务记录展示成功/失败任务与重试入口。

## 核心入口导航录像

一次有明确路由顺序的 Playwright 运行已录制并通过 `ffprobe` 完整性检查：工作台 → 口播剪辑 → 企业资产库 → 发布中心 → 任务记录 → 工作台；5 次侧栏点击、0 个控制台错误，未执行业务写入或发布。录像：[`COORD-0-core-navigation.webm`](./qa/app-baseline/COORD-0-core-navigation.webm)，SHA-256 `da573d17e8c579616e8e41553539f887fb8abc51248922ba63f45347568f5d72`。

另一次运行录制口播剪辑五步流程导航：文案与分段 → 配音 → 出镜 → 成片 → 发布 → 返回文案与分段；6 次点击、0 个控制台错误、未点击自动继续或执行生成。录像：[`COORD-0-core-production-navigation.webm`](./qa/app-baseline/COORD-0-core-production-navigation.webm)，SHA-256 `8e2c95cc61b1edaa55d8f180c6c1ffe26c1ba58d868884e8bc500f298e374752`；事件摘要：[`COORD-0-core-production-navigation.json`](./qa/app-baseline/COORD-0-core-production-navigation.json)。它证明五步流程入口可巡检，不证明数字人生成、媒体处理、任务重试或平台发布。

## 尚未覆盖（针对本历史快照）

- 当时未录制“真实生产任务”视频；该缺口已由后续 `COORD-0-core-production-task-2026-07-19.md` 以 `passed_with_boundary` 补齐；
- 该快照使用浏览器开发模式，不等价于 Tauri 打包版、sidecar 重启或真实用户设备；Tauri/sidecar 后续重启证据另行归档；
- 未执行导入、生成、删除、重试或发布等用户主动业务动作；但页面初始化自动创建 session 的副作用已观察并记录，未删除这些文件；
- 发布中心中的“四个平台可用”仅作为 legacy V1 基线记录，不能解释为 V2 release state。

历史补采入口：用户授权后，在隔离数据和不含账号隐私的设备上执行 AC-0/PUB-0 current baseline，记录截图/录像 SHA-256、首个有效点击至完成耗时、点击数、自动化时间与人工等待分离；后续仍不得用本历史快照绕过 PG-A。
