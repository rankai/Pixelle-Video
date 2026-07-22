# 企业资产库 V2 阶段 1 / 门禁 B 验收记录

- 日期：2026-07-17
- 结论：**通过（GO to Stage 2 domain adapters）**
- 范围：图片/视频资产内核、迁移、流式上传、共享选择器接入、生产流解析和成功渲染
- 默认状态：V2 仍保持关闭；本记录不批准默认启用或清理旧实现

## 已交付

| 能力 | 状态 | 证据 |
|---|---|---|
| SQLite media asset/revision/variant 内核 | 通过 | `pixelle_video/services/assets_v2/repository.py` |
| 图片/视频旧 manifest 兼容迁移 | 通过 | 初始化时按 `media-{kind}-{legacy_id}` 建立稳定映射，原文件不移动 |
| 图片缩略图、视频 poster | 通过 | Pillow/ffmpeg variant 生成；无效旧视频保留 warning，不阻塞迁移 |
| upload session + 流式 `.part` | 通过 | `/api/v2/uploads` + `PUT /api/v2/uploads/{upload_id}/content` |
| SHA-256 去重、取消、大小校验 | 通过 | repository 测试覆盖；去重按 media kind 隔离 |
| 重启恢复 | 通过 | 启动时清理 `.part` 并将中断 session 标记 `restart_recovery` |
| V2 列表、详情、修订、变体和文件流 | 通过 | `api/routers/assets_v2.py`；返回相对路径/受保护 URL，不泄露绝对磁盘路径 |
| V2 图片/视频资产库接入 | 通过 | `VITE_ASSET_CENTER_V2=true` 时桌面端列表、上传、归档切换到 V2 API |
| 生产流共享选择 | 通过 | 画面规划复用同一 `VideoAsset` 适配模型；选择后保存 `video_asset_id` |
| 渲染时稳定 ID 解析 | 通过 | `ip_broadcast_composer._resolve_uploaded_video_path()` 在 worker 侧解析当前 revision |
| usage / snapshot 对账 | 通过 | `resource_usage`、`resource_snapshots`；postproduction render boundary 自动记录 |

## 自动化验证

- `uv run pytest`：**313 passed, 12 warnings**。
- 阶段 2 适配器加入后的当前回归：**314 passed, 12 warnings**（门禁 B 原始记录保留当时快照）。
- `uv run ruff check ...`：所有阶段 0/1 修改文件通过。
- `npm run build`：桌面端 `tsc + vite build` 通过。
- 阶段 1 专项测试：迁移、缩略图、分片上传、重复文件、重启恢复、API、usage/snapshot、V2 ID 解析全部通过。

## 真实媒体闭环

使用 `/Users/nickfury/Downloads/7b76dcd0-6891-11f1-809a-9dc8023b9ad3.mp4_.mp4` 作为上传素材：

1. 通过 V2 repository 分片上传并生成 `media-*` revision。
2. 生产流只保存 `video_asset_id` 和受保护 API URL，不保存绝对路径。
3. postproduction worker 解析 V2 revision，完成画布归一化、音频合并、画面覆盖和封面生成。
4. 最终 MP4 成功生成（522,386 bytes）；同一 session 的 usage=1、snapshot=1，snapshot SHA-256 与 revision 一致。

## 门禁 B 决定

门禁 B 通过，允许进入阶段 2：音色、数字人、品牌和模板的领域适配器/共享选择器扩展。

仍然禁止：

- 默认开启 `asset_center_v2` / `VITE_ASSET_CENTER_V2`。
- 删除旧 manifest、旧 service、旧 API 或旧资产页面。
- 在阶段 2 完成前宣称全量迁移或通过门禁 C。
