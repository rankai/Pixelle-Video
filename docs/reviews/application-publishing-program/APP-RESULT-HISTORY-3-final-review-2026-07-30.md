# APP-RESULT-HISTORY-3 独立六维终审

- Stage：`APP-RESULT-HISTORY-3/SINGLE_MEDIA_RECORD_BLOCKS`
- Gate：`PG-ARH-D`
- 日期：2026-07-30
- 审查方式：独立严格审查线程，只读审查，不修改代码
- 结论：`PASS`
- P0/P1/P2：`0/0/0`

## 六维结论

1. 需求完整性：图文一次生成一个成品卡并预览全部真实页面；数字人一次生成一个视频卡并使用真实播放器。
2. 逻辑正确性：Project、AppRun、Artifact、ArtifactVersion 由签名令牌固定；封面、播放、下载和发布文案属于同一版本集合。
3. 边界情况：覆盖 3/5/8 页、跨项目、路径逃逸、旧版本钉死、局部页面失败、下载/复制降级和旧数据兼容。
4. 代码质量：历史投影和媒体解析独立，只读查询稳定；Blob URL 在替换、关闭和卸载时释放。
5. 测试覆盖：后端 39/39，前端媒体定向 33/33；production build、Ruff、diff 通过。
6. 实际运行：两个重启后的 API 进程读取到重启前相同 AppRun/ArtifactVersion；preview/poster/play/download 均为 200，poster 为 `image/png`，播放/下载为 `video/mp4` 且 SHA-256 一致，`ffprobe=25.760s`。

最终平台发布点击为 0。

## 内容质量边界

- 旧抖音图文样片内容质量不通过。
- 数字人样片为受控可用，字幕、动作和精确口型仍可优化。
- 上述边界不被写成“产出质量通过”，但不阻塞历史聚合与真实预览功能 Gate。
