# COORD-0 抖音 Playwright 字段/封面综合基线

日期：2026-07-19；执行者：主线程；结果：`partial_pass`

## 执行摘要

复用既有 `data/publish_browser/douyin` 持久化 profile，不重新登录；只执行一次综合测试，自动化入口为 Playwright。测试没有点击任何发布按钮。

| 项目 | 结果 |
| --- | --- |
| 开始时间（UTC） | `2026-07-19T00:19:14.915851+00:00` |
| 结束时间（UTC） | `2026-07-19T00:19:32.516734+00:00` |
| 自动化耗时 | `17601 ms` |
| 意图动作 | `set_video_input_files`、`fill_title`、`set_cover_input_files` |
| 登录探针 | `true` |
| 上传后 URL | `/creator-micro/content/post/video?enter_from=publish_page` |
| 标题 | `COORD-0基线测试`，页面计数 `11/30` |
| 描述/话题 | 页面控件可见，但未找到安全可回填语义/selector，未执行，未声称通过 |
| 封面 | 找到图片 input 并提交；页面提示“图片分辨率需大于1000*752”，未声称保存成功 |
| 发布 | 页面存在发布相关控件，但 `final_publish_clicked=false` |
| 截图 | `docs/reviews/application-publishing-program/qa/COORD-0-douyin-playwright-fields-editor.png` |
| 截图 SHA-256 | `74b0ce79e99ad2be5cda42f1398cd6eed9e9a2f0cf5e50055421a31b38bd09a6` |

## 输入资产

- 视频：`data/video_assets/overlay/9f021312c89c.mp4`；SHA-256 `d1b0e1900a9054ba45d131352f0e658e5acb49fe0de78863b7aa18958bb5619b`。
- 封面：`data/video_assets/overlay/9f021312c89c_cover.jpg`；SHA-256 `aaf4c7996239fc706df8f86f2a14caa6ec4168f39beec8b66837211101b1a265`；尺寸 `704x1280`。

## 判定边界

- 任务 5 的有效 MP4 进入编辑器仍通过；标题字段具备真实回填证据。
- 任务 6（标题、描述和话题）只能部分通过：页面控件可见，但未找到安全可回填语义/selector，不能标记完整通过。
- 任务 7（封面上传、裁切和保存）未通过：平台明确拒绝当前尺寸，未点击或伪造保存结果。
- 任务 9 只证明停留在发布前且未点击发布；FinalActionGuard 的 live smoke 仍未完成。
- 任务 1、3、4 仍需各自的首次连接/应用重启/无效媒体证据；任务 8 已单独完成一次恢复验证并真实失败，见 [`COORD-0-douyin-playwright-midclose-recovery-2026-07-19.md`](./COORD-0-douyin-playwright-midclose-recovery-2026-07-19.md)；任务 2 的既有 profile 关闭/重开证据见 [`COORD-0-douyin-playwright-reopen-2026-07-19.md`](./COORD-0-douyin-playwright-reopen-2026-07-19.md)。九项总体和 PG-A 继续 `in_progress / blocked_external_manual`。
