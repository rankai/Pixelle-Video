# APP-WORKBENCH-7 实施与证据收口

日期：2026-07-28
阶段：`APP-WORKBENCH-7`
Gate：`PG-AW-H`
Change Request：`CR-APP-WORKBENCH-001`

## 结论

本阶段实现与本地可视化证据已完成，等待独立六维复审。四个应用工作台均完成当前灰度开关登记、双栏布局收口、四视口可视化采集、窄窗降级检查和无错行检查；最终发布动作与第三方平台动作保持为 0。

本阶段不是 Windows 实机验收，也不是真实平台 rollback/WebView SLA 验收。PG-L 的真实 Windows 用户设备、产品负责人签字、真实平台回滚和原生 WebView SLA 仍保持外部等待。

## 1. 本次实现

### 1.1 灰度开关

生产前端环境显式登记四个工作台开关：

- `VITE_APP_WORKBENCH_V2=true`
- `VITE_APP_WORKBENCH_TEXT_V2=true`
- `VITE_APP_WORKBENCH_CAROUSEL_V2=true`
- `VITE_APP_WORKBENCH_DIGITAL_HUMAN_V2=true`

后端 Registry/feature flag 仍以 fail-closed 归一化为准；本阶段没有新增 Provider 调用、第三方平台打开或最终发布点击。

### 1.2 横向空间与响应式布局

以应用中心既有 tokens 为基准，将 `.app-workbench-shell` 扩展到可用画布：`width: calc(100% + 16px)`、水平 `margin: 0 -8px`、双栏 gap 保持 16px；窄窗继续由既有媒体查询降为单列。这样在 1280 CSS px 下工作台从 969px 扩展到 1001px，减少左右空白且不引入横向滚动。

### 1.3 四应用统一检查

已检查以下路由：

- `marketing-copy`：门店营销文案
- `viral-titles`：爆款标题
- `douyin-carousel`：抖音图文
- `digital-human-video`：数字人口播视频

检查字段包含页面标题、工作台容器、结果/交付区域、错误文案、状态标签、滚动宽度和最终发布/第三方动作计数。

## 2. 测试与构建

| 范围 | 命令/结果 |
| --- | --- |
| Desktop 回归 | `npm --prefix desktop run test -- --run`：16 files / 104 passed |
| Desktop 构建 | `npm --prefix desktop run build`：passed；仅保留既有 Vite chunk >500KB warning |
| Python/应用中心聚合 | `uv run pytest -q tests/app_center_api_test.py tests/app_center_carousel_renderer_test.py tests/app_center_ip_broadcast_api_test.py tests/app_workbench_*_test.py tests/digital_human_dual_mode_recovery_test.py tests/digital_human_quality_impl_test.py tests/config_llm_profiles_test.py tests/coord0_contract_test.py`：92 passed，12 条既有 Pydantic deprecation warnings |
| 静态质量 | `git diff --check`、`uv run python -m compileall -q api pixelle_video`：passed |

## 3. 多视口真实可视化证据

证据目录：[`qa/APP-WORKBENCH-7-visual-2026-07-28/`](qa/APP-WORKBENCH-7-visual-2026-07-28/)。

使用 Codex in-app Browser 的 CDP `Emulation.setDeviceMetricsOverride` 设置 CSS 视口，随后通过 `tab.screenshot()` 采集，每个应用每个视口一张截图，共 16 张；页面 DOM 同步记录 `innerWidth/innerHeight`、document 宽度、工作台宽度、横向溢出和错误数。完整清单见 [`manifest.json`](qa/APP-WORKBENCH-7-visual-2026-07-28/manifest.json)。

| CSS 视口 | 应用数 | document.clientWidth | 工作台 shell 宽度 | 横向溢出 | 错误数 |
| --- | ---: | ---: | ---: | --- | ---: |
| 1440×900 | 4 | 1425 | 1161 | false | 0 |
| 1280×800 | 4 | 1265 | 1001 | false | 0 |
| 900×760 | 4 | 885 | 769 | false | 0 |
| 390×844 | 4 | 375 | 283 | false | 0 |

窄窗 390×844 进入单列降级；没有发现横向滚动或错误文案。截图文件的像素尺寸会受 in-app Browser 的设备像素比影响，manifest 中的 CSS 视口和 DOM 读数是验收依据。

## 4. 状态、恢复与回滚边界

- 四应用状态/Artifact/交付动作继续复用 APP-WORKBENCH-5/6 已通过契约；本阶段未改变 Provider 状态机。
- 重启恢复证据复用 [`qa/PUB-4-batch-4-local-runtime-2026-07-21.json`](qa/PUB-4-batch-4-local-runtime-2026-07-21.json)：AppShell unmount/remount 后保留 canonical package/artifact query，且不重复创建发布运行。
- 数字人工作台恢复/幂等证据复用 APP-WORKBENCH-5 与 `DH-DUAL-3`/`DH-DUAL-4` QA；来源失效仍 fail-closed，需手动重新选择。
- 本地 flag/V1 回滚与最终动作 guard 证据见 [`qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json`](qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json)：V2 从 true 回落 false，profile/旧材料保留，重复上传为 0，publish/confirm_publish 均 deny。
- 这些是本地 bounded smoke，不等价真实平台回滚、原生 Tauri WebView SLA 或 Windows 用户设备生命周期。

## 5. 安全边界与 Gate

- `final_publish_click_count=0`
- `third_party_open_count=0`
- 未执行真实 TTS/RunningHub 调用；未打开抖音、快手、视频号、小红书；未自动点击最终发布。
- 已通知独立审查线程按需求完整性、逻辑正确性、边界、代码质量、测试覆盖、实际运行结果六维复审。

当前 Gate：`PG-AW-H=passed_with_boundary`（独立复审 P0/P1=0）。台账已按总协调队列切回 `PROGRAM-ROLLOUT/PG-L`；不把本阶段证据解释为 PG-L 外部条件已完成。
