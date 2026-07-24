# DH-DUAL-4 灰度与收口实现（2026-07-24）

## 状态

`implementation_pass_with_boundary`。双开关联合门、默认关闭、旧路由保留、候选工作流不提前开放和最终发布安全边界已冻结并通过契约回归；本方案的真实 Provider/桌面/平台外部证据仍按上位协调台账保留边界。

## 已实现/确认

- 后端 `PIXELLE_APP_CENTER_DIGITAL_HUMAN_DUAL_MODE` 与桌面 `VITE_APP_CENTER_DIGITAL_HUMAN_DUAL_MODE` 只有同时开启且双方 readiness 为 true 才启用 V2。
- 默认关闭；desktop-only 或 backend-only 不会暴露可执行 V2；backend 关闭时旧 `/ip` 路由继续可用。
- `image_talking/stable` 保持 `pilot_verified`；图片 natural 保持 `candidate`；视频模式已通过后续真实 live quality gate，当前为 `stable`，但不切换默认模式。
- 灰度顺序固定为开发→本机受控→图片→视频→双模式→重启/回滚→产品签字；不修改默认 Publish V2 或最终发布按钮边界。

### 2026-07-24 真实视频质量门后续更新

`DH-QUALITY-2` 随后完成一次真实 `video_lipsync/natural` Provider smoke 和 25/50/75% 抽帧视觉验收；字幕、人物边缘、口型、背景、封面和技术规格均通过 bounded visual gate。根据用户明确授权，视频工作流已从 `candidate` 提升为 `stable`，但 `default_mode=false`，仍由图片稳定模式作为默认；Program 级独立六维终审仍延后至整体方案完成。

## 验证

- rollout contract/fixture/gate：3 passed。
- 数字人/质量/恢复/应用中心聚合回归：141 passed，12 个既有 Pydantic 弃用警告。
- Ruff、format、JSON、`git diff --check`：通过。

## 边界

- 没有开启生产默认 flag，没有执行真实 Provider、真实 Windows/桌面设备安装、平台发布或最终发布。
- PG-L Windows 实机、产品签字、真实平台 rollback/WebView SLA 仍属于上位 Program 外部等待，不由本 Stage 自动关闭。
- 独立六维复审按用户要求延后至 Program 完成。
