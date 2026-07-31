# APP-RESULT-HISTORY-3 单成品媒体记录块实施与可视化验证

- Stage：`APP-RESULT-HISTORY-3/SINGLE_MEDIA_RECORD_BLOCKS`
- Gate：`PG-ARH-D`
- 日期：2026-07-30
- 结论：待独立六维复审

## 1. 实施结果

### 抖音图文

- 一次图文 `AppRun` 仅投影一个 `single_carousel` 成品项。
- 卡片常驻信息为真实封面、标题、页数与最多“预览、去发布”两个操作。
- 点击卡片或“预览”直接打开全部实际页面，不再使用分页 Tab 作为主交互。
- 预览层承接下载和复制发布文案；页面失败时保留可读提示、下载与发布文案回退。
- 3/5/8 页均按相同模型聚合为一个成品卡。

### 数字人

- 一次数字人 `AppRun` 仅投影一个 `single_video` 最终视频项。
- 卡片常驻信息为真实封面/首帧、标题、时长与最多“播放、去发布”两个操作。
- 点击直接进入真实 `<video>`，不显示模式、VoiceProfile、Provider、版本号或合成步骤。
- 预览层承接下载与复制发布文案；在线播放失败仍可下载。

## 2. 版本与安全边界

- 列表项中的 HMAC 签名版本令牌固定本次 `ArtifactVersion` 集合。
- 图文页面、封面、下载包、视频、封面和发布文案都按同一令牌读取；后续 Artifact 新版本不会改变旧记录。
- 媒体服务校验项目/运行归属、允许的媒体根目录、相对路径和内容类型，拒绝跨项目与路径逃逸。
- 列表与预览为只读；预览不会启动 Provider，也不会写数据库。
- Modal 关闭和组件卸载时释放 Blob URL。
- 所有真实验收中平台最终发布按钮点击次数为 0。

## 3. 自动化验证

- 后端 Entry/投影/媒体定向：39 passed。
- 图文 3/5/8 页参数化验证：均为一个产品、完整有序页面、固定旧版本、零数据库写入。
- 视频验证：视频、封面、发布文案固定为一个产品并按同一版本读取。
- API 验证：真实媒体响应、跨项目拒绝、路径逃逸拒绝、无 Provider 启动。
- 桌面全量：20 files/148 passed。
- 前端验证：单卡显示预算、真实图文全部页面、真实 video、部分页面失败回退、下载/复制、Blob URL 回收。
- TypeScript + Vite production build、Ruff、format、`git diff --check` 通过。

## 4. 真实可视化与运行证据

| 场景 | 结论 | 证据 |
| --- | --- | --- |
| 抖音图文历史卡 | 通过；仅一个成品卡，常驻信息克制 | `evidence/app-result-history-2026-07-30/carousel-history-card.png` |
| 图文完整预览 | 通过；3 个实际页面一次性直接可见，无分页 Tab | `evidence/app-result-history-2026-07-30/carousel-complete-preview.png` |
| 数字人历史卡 | 通过；仅一个最终视频卡 | `evidence/app-result-history-2026-07-30/digital-human-history-card.png` |
| 数字人真实播放器 | 通过；打开真实 `<video>` | `evidence/app-result-history-2026-07-30/digital-human-real-preview.png` |
| 数字人播放中 | 通过；实际播放到约 15 秒，字幕和连续画面可见 | `evidence/app-result-history-2026-07-30/digital-human-output-frame-live.png` |

真实数字人记录：

- Project：`project_54ad306c64814e73b396d9942e8c9fbe`
- AppRun：`run_1135525853084e54a9f6a1936f0f98f1`
- 视频：`output/ipb_8d5ca49c_final.mp4`
- 时长：25.76 秒
- 结果：API/桌面服务重启后仍从历史记录读取并可播放。

## 5. 产出质量边界

功能与内容质量分开验收，详见
[`APP-RESULT-HISTORY-output-quality-review-2026-07-30.md`](APP-RESULT-HISTORY-output-quality-review-2026-07-30.md)：

- 历史卡、真实预览和版本一致性可以通过。
- 当前旧图文样片内容质量不通过，不能作为成品质量通过证据。
- 数字人样片达到受控可用，字幕大小、动作丰富度和精确口型同步仍是质量改进项。
