# COORD-0 抖音 Playwright 中途关闭/恢复基线

日期：2026-07-19；执行者：主线程；结果：`failed`

## 执行摘要

这是一次有明确目的的单次恢复测试，复用已有 `data/publish_browser/douyin` profile：上传已知有效 MP4，确认进入视频编辑器后关闭第一个 Playwright 上下文，再打开同一 profile 并检查是否回到原编辑器。未填写标题/描述/话题，未上传封面，未保存，未点击发布。

| 事件 | UTC 时间 | 结果 |
| --- | --- | --- |
| 首上下文打开 | `2026-07-19T00:39:56.558694+00:00` | `pages=1` |
| 上传页打开 | `2026-07-19T00:39:57.746625+00:00` | `/creator-micro/content/upload` |
| 登录探针 | `2026-07-19T00:39:59.380533+00:00` | `true` |
| 视频 input 提交 | `2026-07-19T00:39:59.631424+00:00` | `uploaded=true`，`251 ms` |
| 关闭前编辑器探针 | `2026-07-19T00:40:06.668791+00:00` | `editor_detected=true`；URL 为 `/creator-micro/content/post/video?enter_from=publish_page`；可见“发布”“作品描述”“检测中” |
| 首上下文中途关闭 | `2026-07-19T00:40:07.005035+00:00` | 已关闭 |
| 新上下文打开 | `2026-07-19T00:40:09.076328+00:00` | `pages=1` |
| 重开后恢复探针 | `2026-07-19T00:40:14.401695+00:00` | `same_editor_url=false`；回到 `/creator-micro/content/upload` |
| 新上下文关闭 | `2026-07-19T00:40:14.687149+00:00` | 已关闭 |

## 判定

- 上传和关闭前进入编辑器真实通过；关闭后重新打开同一 profile 没有恢复到原编辑器 URL，也没有发现可证明草稿恢复的页面状态，因此任务 8 标记 `failed`。
- 该结果只记录当前旧发布路径的真实行为，不推断未来 PUB-2 状态机实现；当前阶段不修改恢复代码。
- 截图：`docs/reviews/application-publishing-program/qa/COORD-0-douyin-midclose-reopen-redacted.png`。
- 截图 SHA-256：`10a8717ef2c9cf684b2f8e2d76248145dfade74a4340c19c7026b91e6fba6be9`。
- 输入视频：`data/video_assets/overlay/9f021312c89c.mp4`；SHA-256 `d1b0e1900a9054ba45d131352f0e658e5acb49fe0de78863b7aa18958bb5619b`。
- 运行命令摘要：`uv run python -`，使用项目 `PlaywrightBrowserRuntime` 两次打开同一 `douyin` persistent profile，第一次调用 `upload_video()` 后关闭，第二次打开上传页并检查 URL/页面标记，最后关闭；没有最终发布动作。
