# COORD-0 抖音 Playwright 上传证据

日期：2026-07-19；执行者：主线程；结果：`partial_pass`

## 执行方式

- 使用项目内 `PlaywrightBrowserRuntime` 的持久化 profile：`data/publish_browser/douyin`。
- 未重新登录；登录探针通过，URL 为 `https://creator.douyin.com/creator-micro/content/upload`。
- 发现 1 个 `input[type=file]`，使用一次 `set_input_files()` 选择既有测试视频：`data/video_assets/overlay/9f021312c89c.mp4`。
- 测试 MP4 SHA-256：`d1b0e1900a9054ba45d131352f0e658e5acb49fe0de78863b7aa18958bb5619b`；大小：`3,314,053` bytes。
- 未点击“发布”“确认发布”或“立即发布”。

## 运行结果

| 观测项 | 结果 |
| --- | --- |
| 登录探针 | `true`（无登录提示；不记录账号标识） |
| 文件输入数量 | `1` |
| 上传动作 | `set_input_files` 成功返回 |
| 上传后 URL | `/creator-micro/content/post/video?enter_from=publish_page` |
| 编辑器 | 可见“基础信息”“作品描述”“设置封面”“扩展信息”“发布设置”等区域 |
| 处理状态 | 页面显示“检测中 3%” |
| 发布动作 | 未执行 |
| 截图 | `docs/reviews/application-publishing-program/qa/COORD-0-douyin-playwright-editor-redacted.png`（已裁掉右上角账户入口） |
| 截图 SHA-256 | `0e3154953df14f7a595af202dab4a5d43627e13bd666473d8409a93e02aa9a6f` |

原始临时截图 `/tmp/pixelle_douyin_playwright_after_upload.png` 仅用于本机复核，不作为长期证据归档。

## 边界与缺口

- 该证据证明有效 MP4 已被 Playwright 送入抖音编辑器，不证明预审完成、封面保存、字段保存或发布成功。
- 本次脚本未记录精确开始/结束时间与用户可见点击数；由于上传动作是直接 `set_input_files`，可记录的意图动作数为 1 个自动化文件选择动作，时间指标保持缺失，不伪造。
- 任务 1、3、4、6–9 仍未全部完成；任务 2 的关闭/重开证据已另行补充，因此九项发布 UX 基线和 PG-A 不能标记 complete。FinalActionGuard 与 V1 rollback 仍为 design-only。
