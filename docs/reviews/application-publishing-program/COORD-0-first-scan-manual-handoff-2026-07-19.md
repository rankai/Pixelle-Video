# COORD-0 首次扫码人工授权交接协议

日期：2026-07-19；状态：`waiting_user`；负责人：用户（扫码）/主线程（证据复验）

## 目的与边界

本协议只用于补齐 PUB-A 任务 1“首次扫码连接证据”。它不要求重新登录当前已授权账号，也不触碰现有 `data/publish_browser/douyin` profile；该 profile 只用于已有授权基线和任务 2/3 的重开验证。

首次扫码不能从已经授权的 profile 反推，也不能由自动化脚本伪造。需要一个隔离的、可丢弃的 QA profile，由 Playwright 打开可见 Chromium，用户亲自扫码一次。整个过程禁止上传媒体、填写内容、保存草稿或点击任何发布按钮。

## 执行前置条件

1. 使用新的临时 profile 或明确标记为 QA 的 profile；不得清理、覆盖或复制当前已授权 profile。
2. 浏览器必须可见，二维码页面和登录态探针都要能截图/记录；不得输出 Cookie、token、账号标识或二维码原图。
3. 只打开抖音创作者中心的登录/上传入口；如果页面已经是登录态，停止并换用干净 profile，不把它算作首次扫码。
4. 只准备证据记录，不准备最终发布动作；最终发布仍由 `FinalActionGuard` 和人工确认边界控制。

## 用户一次性动作

| 顺序 | 动作 | 必须观察的结果 |
| ---: | --- | --- |
| 1 | 打开隔离 QA profile 的抖音入口 | 页面出现二维码或明确的未登录态；`signed_out_pre=true` |
| 2 | 用户使用抖音 App 扫码并在手机上确认登录 | 仅发生一次扫码；不点击网页发布/上传控件 |
| 3 | 等待页面跳转或登录探针变为已登录 | `signed_in_post=true`，记录等待结束时间 |
| 4 | 关闭浏览器上下文并以同一 QA profile 重开 | `reopen_signed_in=true`；不进入发布流程 |
| 5 | 关闭 QA profile，保留脱敏证据 | 不保留敏感会话材料；profile 可按本地安全策略销毁 |

## 证据记录字段

最小 JSON 记录应包含以下字段；`profile_ref` 只允许写脱敏别名，不写绝对路径、Cookie 或账号信息：

```json
{
  "task": "PUB-A-1-first-scan",
  "profile_ref": "qa-douyin-profile-redacted",
  "started_at_utc": "<ISO-8601>",
  "wait_timeout_seconds": 180,
  "timeout_at_utc": "<ISO-8601-or-null>",
  "qr_visible": true,
  "signed_out_pre": true,
  "scan_completed_by_user": true,
  "signed_in_post": true,
  "reopen_signed_in": true,
  "ended_at_utc": "<ISO-8601>",
  "cleanup_completed_at_utc": "<ISO-8601-or-null>",
  "intentional_action_count": 1,
  "screenshots": [
    {"name": "qr-before-redacted.png", "sha256": "<sha256>"},
    {"name": "signed-in-after-redacted.png", "sha256": "<sha256>"}
  ],
  "sensitive_data_recorded": false,
  "final_publish_clicked": false,
  "upload_started": false
}
```

截图至少两张：扫码前（二维码或未登录提示可见但二维码需打码）和扫码后/重开后的已登录探针。截图、事件日志和录屏都要去除账号、token、Cookie、个人信息，内容只保留验证所需区域。

## 判定规则

- 只有 `qr_visible=true`、`signed_out_pre=true`、`scan_completed_by_user=true`、`signed_in_post=true`、`reopen_signed_in=true` 全部成立，任务 1 才能标记 `passed`。
- 只看到当前已授权页面、只看到登录探针为 true、或用户没有实际扫码，均只能标记 `blocked_external_manual`，不得写成首次扫码通过。
- 该证据只关闭首次扫码连接条件；它不关闭任务 8 中途恢复、全新 provider 生成或最终人工发布条件，也不放行 PG-A 后续业务实现。

## 失败与恢复

二维码过期、扫码后未登录、重开丢失登录态或发生风控时，记录失败时间和页面状态，停止重试；不要清理当前已授权 profile，也不要连续重复扫码。下一次只在新的隔离 QA profile 上重新执行，并保留新的 `profile_ref` 和证据链。
