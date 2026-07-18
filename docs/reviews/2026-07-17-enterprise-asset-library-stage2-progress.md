# 企业资产库 V2 阶段 2 进度（领域适配器）

- 日期：2026-07-17
- 前置：门禁 B 已通过
- 默认状态：V2 仍关闭，旧接口/旧页面仍保留

## 已开始的领域扩展

`/api/v2/library/items` 现在提供统一投影和受控写入：

- `voice`：旧音色 manifest 已导入 `media_assets(audio)`，统一返回试听 URL、时长和稳定资源 ID。
- `digital_human`：数字人档案/场景进入 `digital_human_profiles/scenes`，海报仍由媒体 revision 提供；保留左侧筛选、卡片和右侧预览语义。
- `brand`：品牌包进入 `brand_kits_v2`，支持原生创建、更新和归档，不泄露 logo 磁盘路径。
- `template`：模板进入 `template_definitions`，支持 revision 写入；预览、1080×1920 画布和实际字幕契约均来自 SQLite。
- 集合、标签和收藏进入统一资源索引，列表支持 `favorite`/`tags` 筛选。

媒体和领域资源都可以通过 `GET /api/v2/library/items/{resource_id}` 查询；统一列表的搜索、分页和 `resource_id + kind` 语义已经稳定。生产流在 V2 开关下对视频、音色、数字人和模板使用共享 `AssetPickerDialog`，关闭开关时仍走兼容选择器。

## 本轮已完成

- 资产中心 V2 已接入桌面资产页，统一卡片、搜索、详情预览、上传、归档、收藏和标签编辑。
- 资产中心 V2 已提供统一媒体上传队列（多文件、进度、取消、失败项重试）以及数字人/品牌/模板新建入口；图片默认完整展示并使用透明棋盘格背景。
- 生产流的视频、图片、音色、背景音乐、数字人、品牌和模板选择在 V2 开关下使用共享 `AssetPickerDialog`；选择后写入稳定资源 ID 和必要的兼容路径。
- 渲染边界会把受保护 URL 解析为本地 revision；数字人场景使用绑定的 `source_revision_id`，音色引用在 TTS provider 边界解析，避免 V2 选择后因 URL 不能被本地 provider 读取而失败。
- 自定义模板使用已注册 HTML 基础模板，并把 SQLite 中的字幕契约覆盖到最终 ASS 样式；模板 revision/renderer 随快照保留。
- V2 开启时，旧 `/api/assets/*` 深链接与首页读取/写入转到同一 SQLite 源，删除行为变为归档，关闭开关时仍保持旧 manifest 回滚路径。
- 共享选择器支持收藏筛选、最近使用排序和单选/多选协议；管理页与生产选择器继续共享同一资源投影。
- 渲染边界同时记录音色、数字人、品牌、模板和媒体覆盖的 usage/snapshot；模板 snapshot 带 revision/renderer 版本。
- Stage-1 旧 SQLite 的 image/video CHECK constraint 会在初始化时无损重建，以支持 audio 上传；新增迁移回归测试。

## 仍需门禁 C 前验证

- 真实桌面运行时需用已登录数据执行一次“资产管理 → 生产流选择 → 成功渲染”，并核对所有资源快照。
- 必须完成全量迁移数量/哈希对账和旧 session reconciliation，再决定是否把 `PIXELLE_ASSET_CENTER_V2` 默认值改为 true。
- 门禁 C 前不清理旧 manifest、旧路由或旧 UI，回滚仍通过 feature flag。

## 门禁 C 前剩余验证

1. 真实桌面运行时完成一次端到端闭环并核对快照。
2. 对关键旧 session 做资源引用 reconciliation。
3. 完成全量迁移数量/哈希对账、回滚演练和无障碍回归后，再申请门禁 C。
