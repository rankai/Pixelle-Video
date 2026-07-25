# PLATFORM-EXPANSION：三平台 pilot/人工发布前收口（2026-07-25）

## 结论

`passed_with_boundary`。快手、视频号和小红书均提升为与抖音相同的 `pilot` 发布状态，发布中心允许进入受控的发布前填充；最终发布仍必须由人工确认，默认 Publish V2 rollout 继续关闭。

本批没有重复执行第三方上传。三平台各自已存在一次有目的的项目 Playwright headful live evidence，本批对既有证据、平台适配器、重启保护、release promotion 和回滚契约做了机器复验与状态收口。避免对已完成的第三方动作进行无分析重复尝试。

## 平台状态

| 平台 | 状态 | 可用范围 | 明确边界 |
| --- | --- | --- | --- |
| 抖音 | `pilot` | 视频、标题、描述、话题、竖封面，停止在人工发布前 | 横封面建议保留；最终发布不点击 |
| 快手 | `pilot` | 视频、作品描述、话题文本回退、封面预览，停止在人工发布前 | 当前普通视频编辑器不提供独立标题；封面是本地 blob 预览；不伪造远端回执 |
| 视频号 | `pilot` | 视频、标题、描述、封面，停止在人工发布前 | 无稳定远端媒体 ID；未保存草稿重启后进入 `STATE_AMBIGUOUS`，不重复上传 |
| 小红书 | `pilot` | 视频、标题、正文、话题文本、封面，停止在人工发布前 | 话题文本回退；封面本地 blob；无稳定远端媒体 ID；未保存草稿重启后进入 `STATE_AMBIGUOUS` |

## 统一安全边界

- `human_confirmation_required=true`；`allow_final_publish=false`。
- 三个平台均保留 Playwright visible/headful、单次视频注入、字段语义回读和 `final_publish_click_count=0`。
- 平台草稿重启后无法确认身份时统一 fail-closed，不自动重新上传。
- 账号页和发布中心显示与抖音一致的 `pilot/试点` 状态；仍提供复制/下载回退。
- 任何平台回滚都只将 release state 恢复为 `unverified`，不删除账号 profile、登录态或历史运行。

## 证据与复验

- 快手：[`qa/PG-M-kuaishou-live-gate-2026-07-22.json`](qa/PG-M-kuaishou-live-gate-2026-07-22.json)。
- 视频号：[`qa/PG-M-shipinhao-live-gate-fix-2026-07-22.json`](qa/PG-M-shipinhao-live-gate-fix-2026-07-22.json)。
- 小红书：[`qa/PG-M-xiaohongshu-live-gate-2026-07-22.json`](qa/PG-M-xiaohongshu-live-gate-2026-07-22.json)。
- 当前 release contract：[`platform-expansion-pilot-release.contract.json`](../../contracts/publishing/platform-expansion-pilot-release.contract.json)。
- 本批不改变 PG-L 的 Windows、产品签字、真实 rollback/WebView 外部边界。
