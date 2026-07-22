# COORD-0 抖音描述/话题/封面 live smoke

日期：2026-07-19；执行者：主线程；结果：`passed`（字段与竖封面保存）；保留在最终人工发布前，未点击发布。

## 执行条件

- 复用既有 `data/publish_browser/douyin` Playwright 持久化 profile，不重新扫码或登录；登录探针为 `true`。
- 使用已知有效视频 `data/video_assets/overlay/9f021312c89c.mp4`，SHA-256 `d1b0e1900a9054ba45d131352f0e658e5acb49fe0de78863b7aa18958bb5619b`。
- 使用隔离生成的合规封面 `valid_cover_png.png`（1080×1440），SHA-256 `026cfad4d9bc1d5d05a5b79a9afb8f90ecd2f0769c74c96aa904c15011de5bdc`。
- 两次运行均有明确目的：第一次确认真实 DOM 语义并让封面进入裁切弹窗；第二次只点击弹窗内唯一可见“保存”，没有点击底部“发布”。第二次自动化耗时 `18498 ms`，无人工等待。

## 通过证据

| 项目 | 结果 |
| --- | --- |
| 标题 | 真实 `input[placeholder*='标题']` 回填 `COORD-0封面保存验证` |
| 描述 | 真实 `[contenteditable='true'][data-placeholder*='简介']` 回填；保存后页面可见“门店短视频营销封面保存验证。” |
| 话题 | 同一真实作品描述编辑器回填 `#门店营销 #短视频运营`；页面预览包含两项话题文本，平台话题建议列表可见。这里验证的是文本话题写入与预览，不把建议列表出现误称为单独运营数据绑定。 |
| 封面 | 图片 input 接受 1080×1440；“设置封面”裁切弹窗出现；唯一可见弹窗“保存”点击后弹窗消失，`cover_modal_closed=true`。 |
| 发布边界 | 截图仍显示底部“发布”按钮；脚本只点击封面弹窗“保存”，`final_publish_clicked=false`。 |

## 归档

- 脱敏截图：[`COORD-0-douyin-fields-cover-saved.png`](./qa/COORD-0-douyin-fields-cover-saved.png)，已裁掉右侧平台预览和顶部账号区域，SHA-256 `b5d8567545948c438bd8e90a7b2f32eb7911e6157794ff79b72da9a4ee97c73d`。
- DOM/事件摘要：[`COORD-0-douyin-fields-cover-saved.json`](./qa/COORD-0-douyin-fields-cover-saved.json)，已将第三方 console error URL 中的 `sign_token` 替换为 `REDACTED`，SHA-256 `c56e59c8305d28fe14e31e49cdf130c38e26ea4f9af7d22c6deb5c48b38acf5f`。
- 页面仍提示“横/竖双封面缺失”，这是平台对横版+竖版双封面的建议/质量提示；本次完整验证的是竖版封面上传、裁切和保存，不声称横版封面已设置。
- 运行捕获到抖音第三方脚本的若干 console error（`secsdk`、`BoxParser` 和一次资源缺失）；它们未阻断本次字段/封面保存，但应在 PUB-2/PUB-3 复验时作为外部平台噪声单独观测。

## 判定边界

该 smoke 只证明现有登录 profile 下字段和竖封面控件可被一次性安全操作，并证明自动化在人工发布前停止；不证明最终发布成功，不证明中途关闭恢复，不证明首次扫码或 Tauri 免扫码。
