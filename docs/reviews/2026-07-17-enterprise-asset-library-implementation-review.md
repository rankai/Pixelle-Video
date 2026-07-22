# 企业资产库完整重构实施复审

- 日期：2026-07-18
- 实施范围：阶段 0–5 的代码落地、阶段 6 的门禁复核
- 结论：**门禁 C 已通过；新版默认启用，旧实现保留回滚窗口**

## 已落地能力

1. SQLite 资产内核：媒体资产、不可变 revision、缩略图/poster、分析 job、归档/恢复、哈希去重和流式 upload session。
2. 统一资源投影：图片、视频、音频/音色、数字人档案/场景、品牌、模板统一搜索、收藏、标签、集合、facets、使用记录。
3. 生产流闭环：共享 `AssetPickerDialog` 接入图片/视频覆盖、音色、背景音乐、数字人、品牌和模板；选择结果写入稳定资源 ID，渲染边界再解析为本地 revision，品牌默认 BGM 与手动 BGM 均可通过 V2 音频 revision 解析。
4. 数字人双栏管理：左侧人物/收藏筛选和卡片，右侧即时预览、场景切换、“用于视频生产”；场景可独立增加并绑定指定 revision。
5. 上传体验：批量选择、XHR 进度、取消、逐项失败和重试；图片完整展示、透明棋盘格、规格摘要；资产详情支持归档/恢复。
6. 列表维护：资产中心提供批量管理模式，可多选后批量收藏、归档或清空选择；归档默认隐藏，可显式恢复。
7. 引用完整性：数字人/场景引用在写入前校验媒体类型和 revision 归属；品牌 logo/BGM 也按允许的媒体类型校验，避免库内出现不可预览资源。
8. 模板一致性：模板 revision、renderer version、字幕契约进入快照；自定义模板基于注册 HTML 基础模板渲染，字幕契约覆盖到最终 ASS。
9. 兼容与回滚：V2 明确启用后旧 `/api/assets/*` 读写 SQLite，删除转归档；V2 关闭后旧 manifest/UI 仍可工作，旧实现未清理。

## 验证结果

- `uv run pytest -q`：347 passed，12 warnings（均为既有 Pydantic 弃用提示）。
- `uv run ruff check ...`：通过。
- `desktop/npm run build`：通过。
- V2 API smoke：facets、模板列表和最近/名称排序通过。
- 浏览器 API 连接修复：开发端未显式设置 `VITE_API_BASE_URL` 时，`5173/5174/1420` 自动指向 `http://127.0.0.1:8100`；健康检查与资产列表实测均为 200。
- API 启动竞态修复：浏览器首个真实请求前探测 `/health`，8100 不可用时自动尝试本机 sidecar 8000；只有候选地址均不可达才显示“后端服务未连接”。
- 无显式环境变量回归：未设置 `VITE_API_BASE_URL` 的 `127.0.0.1:1420` 已实际打开资产中心并读取 14 条 V2 资产。
- Stage-0 baseline：无缺失文件；reconciliation dry-run 已覆盖现有 session。
- 增量迁移：对已有 `legacy_media_migration_v1` 数据库补执行 `legacy_media_migration_v2`，当前本地音色 2 条（MP3/FLAC）已进入 V2 SQLite。
- 数量/SHA 对账：基线新增逐文件 SHA-256，reconciliation 的 baseline audit 对视频 2/2、数字人 2/2、音色 2/2、品牌 1/1 验证通过，缺失文件与 checksum mismatch 均为 0。
- 真实媒体闭环：V2 稳定视频/图片 ID 经渲染边界解析后，实际生成带字幕和覆盖画面的 `1080×1920` MP4。
- 全生产引用快照：自动化 Gate-C 回归验证 voice、数字人/场景、品牌 BGM、模板 revision 和视频覆盖组均在成片边界写入 usage/snapshot。
- 真实桌面资产中心验收：使用 Computer Use 驱动本地 Chrome，完成 V2 资产列表、类型筛选、图片完整预览和详情侧栏检查；截图已归档为 `docs/reviews/enterprise-asset-library-v2-desktop-qa.jpeg` 与 `docs/reviews/enterprise-asset-library-v2-detail-qa.jpeg`。
- 真实桌面共享选择器：在口播剪辑的出镜步骤打开统一资产库数字人选择器，完成“人物 → 场景”选择；后端收到 session config PATCH 和 reconcile 200，数字人、场景、模板 usage 已落库。
- 真实浏览器生产选择链路：Playwright Chromium 完成“粘贴脚本 → 整理文案 → 参考音色 → 数字人/场景 → 模板 → BGM → 画面规划覆盖组 → 图片资产”的真实 UI 操作；成片页确认画布 `1080×1920`、覆盖组及 BGM 状态。
- 真实浏览器一键成片：在同一类生产会话实际点击“一键成片”，成功生成 MP4 与封面，ffprobe 验证 `1080×1920`，并写入 8 个资源快照。
- 发布安全边界：同一成片会话进入发布步骤后，抖音/小红书/视频号/快手均显示“自动填充 · 人工发布”，明确停在最终人工点击前。
- 服务级回滚 smoke：独立进程关闭 `PIXELLE_ASSET_CENTER_V2` 后，V2 路由返回 404，旧图片/音色路由仍返回 200，随后进程正常停止。
- Tauri 壳构建与 release 实测：Rust 1.97.1 下 `npm run tauri:build -- --bundles app` 成功；从 `/tmp` 启动 `.app` 后，内置资源直接映射到 `Contents/Resources/{templates,workflows}`，sidecar 使用 `~/Library/Application Support/ai.pixelle.video.desktop` 数据目录，`/health` 与 V2 列表均返回 200。
- 真实桌面新版资产库：Computer Use 实测资产中心列表、模板缩略图和详情预览、上传弹窗、数字人创建弹窗；上传测试资产成功生成缩略图并在列表/详情展示，归档后刷新隐藏。修复了 sidecar 未转发 `PIXELLE_ASSET_CENTER_V2` 导致首屏误报“后端服务未连接”的问题。
- 发布版 sidecar 完整生产闭环：在隔离桌面 token 与 app data 下，使用 V2 图片/视频/音色/数字人/场景/品牌/模板完成生产配置并执行 postproduction task；task `e026e03c-54c9-4758-998c-244c30bb600f`=`completed`，最终 MP4 和封面均生成且为 `1080×1920`，9 个资源 snapshot 写入账本。
- 发布版封面降级：Playwright 浏览器不可用时按模板 CSS 契约走 PIL fallback，避免发布版因缺少浏览器二进制而把成片任务判失败；对应回归测试已加入。

## 门禁 C 已放行

专用浏览器桥接仍会报 `Cannot redefine property: process`，因此浏览器端生产链路继续用 Playwright 完成；这不影响桌面壳的本地生产链路。Tauri release sidecar 已完成包含所有资源类型的完整成片回归，服务级回滚也已通过。

默认运行配置：

```text
PIXELLE_ASSET_CENTER_V2=true
VITE_ASSET_CENTER_V2=true
```

如需回滚，显式设置两个开关为 `false`；旧 UI/路由暂不删除，进入灰度观察期后分批清理。

## 数字人资料完整性补充（2026-07-18）

本次统一页面不是把旧资产管理器删除后另起一套孤立数据，而是在原有独立服务和 manifest 的基础上增加 V2 资产内核、统一投影和兼容适配层。旧的图片、视频、音色、形象等接口仍保留；V2 开启时兼容接口读写 SQLite，关闭时回到旧 manifest/页面，因此可以灰度和回滚。

复审中发现数字人表单此前只完成了“名称 + 选择已有媒体”的半成品接入，封面图和演示视频上传入口没有接上，这是缺口而不是预期行为。现已修订为：

- 封面图单独上传为 image asset，用于人物卡片和稳定封面；
- 演示视频单独上传为 video asset，作为默认场景的 source asset，并保留固定 revision；
- 也可以选择已有图片/视频资产，避免重复上传；
- 视频 poster 使用生成的 poster variant，不再把 MP4 当作 `<img>`；点击数字人时优先播放默认场景演示视频，场景列表标注“演示视频/图片场景”；
- 生产流仍只传递 profile/scene/asset/revision ID，渲染边界再解析为本地文件。

补充验证：`uv run pytest -q` 为 **349 passed**，`desktop/npm run build` 通过；新增回归覆盖“封面与演示视频分离、场景媒体类型和 revision 预览 URL”。
