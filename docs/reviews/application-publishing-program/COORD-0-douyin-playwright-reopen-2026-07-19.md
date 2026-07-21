# COORD-0 抖音 Playwright profile 关闭/重开基线

日期：2026-07-19；执行者：主线程；结果：`partial_pass`

## 执行摘要

复用已有 `data/publish_browser/douyin` 持久化 profile，不重新登录。仅执行一次有明确目的的顺序：打开创作者上传页并探针 → 关闭 Playwright 持久化上下文 → 再次打开同一 profile 并探针。过程中未上传视频、未填写字段、未点击发布。

| 阶段 | UTC 时间 | 登录探针 | URL | 页面标题 | 探针耗时 |
| --- | --- | --- | --- | --- | ---: |
| 首个上下文探针 | `2026-07-19T00:35:22.512128+00:00` | `true` | `/creator-micro/content/upload` | `抖音创作者中心` | `1722 ms` |
| 明确关闭后重新打开的上下文探针 | `2026-07-19T00:35:28.954343+00:00` | `true` | `/creator-micro/content/upload` | `抖音创作者中心` | `1634 ms` |

## 证据边界

- 该运行证明现有已授权 Playwright profile 在上下文关闭后可再次打开，且两次均未出现登录页；可作为任务 2 的重开证据。
- 它不证明任务 1 的首次扫码连接，也不等价于重启桌面应用，因此任务 1、任务 3 仍不能标记通过。
- 运行没有进入编辑器或发布动作，不能替代任务 5–9 的字段、封面、恢复和 FinalActionGuard live smoke。
- 由于跳过首次连接，整体九项基线和 PG-A 仍保持 `in_progress / blocked_external_manual`。

## QA 复验补充

为闭合任务 2 的视觉与事件证据，使用同一运行命令和同一 Playwright 持久化 profile、创建两个 runtime 实例，仅执行一次“首个上下文探针 → 关闭 → 新上下文重新打开并截图 → 再关闭”采集；没有上传、填写或点击发布。原始运行事件（UTC）如下：

```text
first_runtime_created                 2026-07-19T00:35:16.295334+00:00
first_context_opened                  2026-07-19T00:35:19.428430+00:00  pages=1
first_context_probe                   2026-07-19T00:35:22.512128+00:00  logged_in_probe=true probe_ms=1722
first_context_closed                  2026-07-19T00:35:22.683287+00:00
reopen_runtime_created                2026-07-19T00:35:22.683312+00:00
reopen_context_opened                 2026-07-19T00:35:24.598415+00:00  pages=1
reopen_context_probe_and_screenshot   2026-07-19T00:35:28.954343+00:00  logged_in_probe=true probe_ms=1634
reopen_context_closed                 2026-07-19T00:35:29.301263+00:00
```

执行命令摘要：`uv run python -`，先创建 `PlaywrightBrowserRuntime('data/publish_browser')` 并打开 `douyin` 持久化 profile，执行 `open_creator_page()`、`is_logged_in()` 后 `runtime.close()`；再创建新的 Runtime、打开同一 profile、再次执行 `open_creator_page()`、`is_logged_in()`、`page.screenshot()`，最后再次 `runtime.close()`；原始截图未作为交付物保留，交付的是脱敏裁剪图。

QA 截图：`docs/reviews/application-publishing-program/qa/COORD-0-douyin-reopen-editor-redacted.png`。

QA 截图 SHA-256：`034ff131a62730b5297bec5afdc07128f8058620b1f6a3aa8317b7375809809f`。

截图只保留上传页中央区域，已裁去浏览器顶部和右侧账户区域；可见“发布视频”上传页、上传按钮和页面内容，未出现登录提示，未包含账户身份信息。
