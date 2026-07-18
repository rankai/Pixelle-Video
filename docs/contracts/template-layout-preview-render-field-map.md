# TemplateLayoutContract preview/render 字段映射

| Contract field | Preview adapter | Render adapter | Golden assertion |
| --- | --- | --- | --- |
| `canvas.width/height` | 规范化画布尺寸 | 输出封面/视频画布 | exact canvas size |
| `fonts[].font_id/font_sha256/weight` | 注册字体解析 | PIL/ASS 同一 resolved font | identity exact |
| `cover.title` | 标题框、字号、行高、换行 | 封面标题绘制 | box error ≤ 2px |
| `cover.subtitle` | 副标题框、字号、行高 | 封面副标题绘制 | box error ≤ 2px |
| `cover.safe_area` | 安全区 overlay | 标题/副标题约束 | mask IoU ≥ 0.98 |
| `video_subtitle.font_token/font_size` | 字幕样式预览 | ASS force style | font/size exact |
| `video_subtitle.alignment/margin_*` | 字幕基线预览 | ASS alignment/margins | baseline error ≤ 2px |
| `video_subtitle.safe_area` | 字幕安全区 overlay | subtitle placement guard | mask IoU ≥ 0.98 |

未知字段、缺失字体、未注册 `font_token`、画布外 box 和空安全区在两端都必须拒绝；不得保存“预览能显示但最终渲染忽略”的字段。
