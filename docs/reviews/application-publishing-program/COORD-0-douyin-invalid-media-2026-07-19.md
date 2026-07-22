# COORD-0 抖音无效媒体本地拒绝基线

日期：2026-07-19；执行者：主线程；结果：`passed`（本地预检）；不向抖音提交坏文件。

## 目的与边界

验证无效媒体在进入浏览器平台上传前即可被本地媒体探针拒绝，避免把平台上传当成盲试。使用 `docs/contracts/publishing/generate_media_fixtures.py` 在 `/tmp/pixelle-pub0-media-20260719` 生成隔离 fixture；没有写入项目 `data/`，没有打开抖音文件选择器，没有创建草稿或发布。

## 结果

仓库 `pixelle_video.services.assets_v2.repository` 的 `_video_metadata` 使用 ffprobe 读取视频元数据：

| 文件 | 结果 | 依据 |
| --- | --- | --- |
| `valid_mp4_h264.mp4` | accepted | H.264，16×16，200 ms，10 fps |
| `missing_moov_atom.mp4` | rejected | `ValueError: Unable to inspect video metadata`；ffprobe 报 `moov atom not found` |
| `zero_byte.mp4` | rejected | `ValueError: Unable to inspect video metadata`；ffprobe 无可读媒体 |
| `fake_extension.mp4` | rejected | `ValueError: Unable to inspect video metadata`；ffprobe 报 `moov atom not found` |

封面使用 `_image_metadata` 加本地尺寸门槛复核：`valid_cover_png.png` 为 1080×1440，accepted；`invalid_cover_dimensions.png` 为 1×1，`REJECT_DIMENSIONS`。fixture 生成输出的 SHA 与固定 manifest 一致：有效 MP4 `cebb770ea49011d28217678bed7da4fae76788aa3275be14809ca10bc9f23e0c`，无效 MP4 分别为 `551e61fcb6912b591773c6921c529eae42d9a9b23e2b1fa1725a2ab59779830c`、`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`、`11886b5183125f3f1f05e7a55d8595b2d084baf40a952c404f51c505e7d2335b`。

## 判定

任务 4 的“无效 MP4 上传”按安全边界解释为“浏览器上传前本地拒绝”；本地拒绝通过。平台侧不再重复提交坏文件，也不把本地 fixture 结果冒充平台 UI 错误提示。
