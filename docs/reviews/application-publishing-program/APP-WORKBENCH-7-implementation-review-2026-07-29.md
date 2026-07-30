# APP-WORKBENCH-7 独立六维复审

日期：2026-07-29
阶段：`APP-WORKBENCH-7`
Gate：`PG-AW-H`
审查线程：`/root/app_workbench_stage7_strict_reviewer`

## 结论

`PASS`，P0=0、P1=0。建议将 `PG-AW-H` 登记为 `passed_with_boundary`，并把唯一入口切回 `PROGRAM-ROLLOUT/PG-L`。本结论不替代 Windows 用户设备、产品负责人签字、真实平台 rollback 或原生 WebView SLA 验收。

## 六维验证

### 1. 需求完整性

- 四个工作台均覆盖：门店营销文案、爆款标题、抖音图文、数字人口播视频。
- 本阶段 manifest 有 16 条本阶段记录（4 应用 × 1440×900、1280×800、900×760、390×844），不是 prior 阶段引用。
- 四个生产工作台 flag 已登记，后端 Registry 仍 fail-closed；左右空间收口与窄窗单列降级均有证据。
- 状态、Artifact、handoff 事实复用已通过的 APP-WORKBENCH-5/6 契约；本阶段没有扩大 Provider 或平台范围。

### 2. 逻辑正确性

- 1440/1280/900/390 CSS 视口的 DOM 读数分别记录 shell 宽度 1161/1001/769/283，`overflow=false`、`errorCount=0`。
- 390×844 进入单列输入/结果 Tab 降级；桌面视口保持双栏。
- `.app-workbench-shell` 使用可用画布扩展和 16px gap，未改变来源版本、Artifact、最终发布 guard 或 Provider 状态机。

### 3. 边界情况

- 本地 AppShell remount/restart、数字人幂等恢复、来源失效 fail-closed 均有引用证据。
- 本地 rollback smoke 验证 V2 flag true→false 后 profile/旧材料保留、重复上传 0，`publish`/`confirm_publish` 均被 `FINAL_ACTION_BLOCKED` 拒绝。
- `final_publish_click_count=0`、`third_party_open_count=0`、`provider_calls=0`。
- Windows 实机、真实平台 rollback、原生 WebView SLA 明确保持外部边界，未被冒充为完成。

### 4. 代码质量

- Desktop `npm test -- --run`：16 files / 104 passed。
- Desktop production build：通过；仅既有 Vite chunk >500KB warning。
- Python `compileall`、`git diff --check`：通过。
- 后端聚合测试：92 passed；12 条为既有 Pydantic deprecation warnings。

### 5. 测试覆盖

- 聚合命令覆盖应用中心 API、图文 renderer、数字人恢复/质量、工作台 v2、LLM profile、coordination contract。
- feature flag resolver 覆盖默认 false、非法值 fail-closed、四个工作台 flag 和冲突 alias。
- 16 条视觉 manifest 记录均指向存在的截图文件，并记录目标 CSS viewport、DOM 宽高、shell/grid、溢出和错误数。
- 回滚/重启证据均注明为 local bounded smoke；未把本地证据升级成真实平台或 Windows 验收。

### 6. 实际运行结果

- 视觉文件逐项存在，1440、900、390 代表性截图抽检符合桌面双栏/窄窗单列预期；四视口 DOM 均无横向溢出和错误。
- 生产环境四个工作台 flag 显式开启；默认 Provider、第三方平台和最终发布动作未触发。
- 发布边界计数为 0，人工发布安全停手保持不变。

## 非阻塞 P2

1. 视觉 manifest 的 `title` 字段为空；数字人记录的 `grid` 字段为 null，但均有 shell/DOM metrics 和实际截图，不影响 Gate。
2. 截图像素尺寸受 in-app Browser 宿主容器/DPR 影响；验收以 manifest 的 CSS viewport 和 DOM 读数为准。
3. 既有 Pydantic deprecation 与 Vite chunk size warning。

## 验证依据

- [`APP-WORKBENCH-7-implementation-2026-07-28.md`](APP-WORKBENCH-7-implementation-2026-07-28.md)
- [`qa/APP-WORKBENCH-7-implementation-2026-07-28.json`](qa/APP-WORKBENCH-7-implementation-2026-07-28.json)
- [`qa/APP-WORKBENCH-7-visual-2026-07-28/manifest.json`](qa/APP-WORKBENCH-7-visual-2026-07-28/manifest.json)
- [`qa/PUB-4-batch-4-local-runtime-2026-07-21.json`](qa/PUB-4-batch-4-local-runtime-2026-07-21.json)
- [`qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json`](qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json)
- 复跑命令结果：后端 92 passed/12 warnings；Desktop 16 files/104 passed；build、compileall、diff check passed。
