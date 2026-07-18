# 企业资产库 V2 门禁 C 评审记录

- 日期：2026-07-18（最终复审）
- 范围：阶段 2/3（领域资源、统一索引、生产流共享选择、渲染快照）
- 结论：**通过；新版默认启用，旧实现保留回滚窗口**

## 已验证

| 检查项 | 结果 | 证据 |
| --- | --- | --- |
| 领域资源统一投影 | 通过 | `AssetLibraryRepository.list_domain_items()`、`GET /api/v2/library/items` |
| 音色/数字人/品牌/模板原生写入 | 通过 | `create_brand_kit`、`create_digital_human_profile`、`create_template_revision`；API 回归测试 |
| 收藏、标签、集合 | 通过 | `resource_tags`、`resource_favorites`、`resource_collections/collection_items` |
| 统一资产中心 UI | 通过（构建级） | `desktop/src/features/assets/components/AssetCenterV2.tsx`；`npm run build` |
| 生产流共享选择 | 通过（构建级） | `AssetPickerDialog` 在 V2 开关下接入图片/视频覆盖、音色、背景音乐、数字人、品牌和模板；BGM/品牌默认音乐记录为稳定音频资产 ID |
| 渲染资源 usage/snapshot | 通过（测试级） | postproduction 边界记录媒体、音色、数字人、品牌和模板；模板带 revision/renderer |
| URL→本地 revision 边界 | 通过（测试级） | TTS/数字人/图片/视频 overlay 在 provider/render boundary 解析稳定 ID；数字人场景固定 `source_revision_id` |
| 旧 API 兼容 | 通过（测试级） | V2 开启时 `/api/assets/*` 从 SQLite 读写并将删除转换为归档；V2 关闭时保留旧 manifest |
| 领域资源管理 | 通过（构建/接口级） | 数字人档案/场景、品牌、模板新建与修订入口；模板使用注册基础渲染器叠加版本化字幕契约 |
| 领域引用完整性 | 通过（测试级） | 数字人/场景只接受存在的图片或视频及其有效 revision；品牌 logo/BGM 引用按媒体类型校验；无效引用会在写入前拒绝 |
| 批量资产管理 | 通过（构建/接口级） | 统一列表提供批量收藏/归档；归档默认隐藏并支持恢复，API 回归覆盖可逆操作 |
| Stage-1 SQLite 音频约束迁移 | 通过 | 旧 CHECK constraint 重建测试 |
| 后端/前端回归 | 通过 | `347 passed`；Ruff 通过；Desktop `npm run build` 通过 |
| 真实媒体渲染闭环 | 通过（自动化） | V2 上传的 MP4/PNG 以稳定 ID 进入 overlay，实际 ffmpeg 合成字幕并输出 `1080×1920`；`tests/ip_broadcast_render_regression_test.py` |
| 全生产引用快照 | 通过（自动化） | `test_v2_full_production_reference_set_is_snapshotted` 验证 voice、digital human/scene、brand BGM、template revision、video overlay 均在成片边界写入 usage/snapshot |
| 增量迁移与音色对账 | 通过（本地数据） | `legacy_media_migration_v2` 补齐已有数据库的 2 条音色（MP3/FLAC）；facets 与 voice 列表均返回 2 |
| 数量/SHA 对账 | 通过（本地数据） | `scripts/assets_v2_reconcile.py --baseline ... --json`：视频 2/2、数字人 2/2、音色 2/2、品牌 1/1，manifest/file SHA 与缺失文件均为零差异 |
| API smoke | 通过 | V2 开关启动后 `/health`=200；`/api/v2/library/items?limit=500` 返回 14 条资产（video/image/voice/audio/digital_human/brand/template），facets、voice 列表、模板列表/排序成功 |
| 浏览器无显式 API 配置 | 通过 | 未设置 `VITE_API_BASE_URL` 的 `127.0.0.1:1420` 实测可加载资产中心与 14 条资源；不再出现“后端服务未连接” |
| API 启动竞态与端口兜底 | 通过 | `desktop/src/api.ts` 首次请求前探测 `/health`，开发端优先 8100、sidecar 兜底 8000；8100/8000 当前均实测 200 |
| 真实桌面资产中心/详情 | 通过（Computer Use） | 本地 Chrome 在 V2 开关下完成资产中心列表、搜索/类型筛选、图片卡片和数字人详情预览检查；截图归档于 `docs/reviews/enterprise-asset-library-v2-desktop-qa.jpeg`、`docs/reviews/enterprise-asset-library-v2-detail-qa.jpeg` |
| 真实桌面共享选择器 | 部分通过 | 口播剪辑 → 出镜 → “从统一资产库选择”已打开数字人选择器，完成“人物 → 场景”选择；API 日志记录 session config PATCH 与 `/api/v2/sessions/{id}/reconcile` 200，usage 已写入数字人/场景/模板资源 |
| 真实浏览器生产共享选择 | 通过（Playwright） | 浏览器端 `127.0.0.1:5174` 真实走完“粘贴脚本 → 整理文案 → 配音参考音色选择 → 数字人/场景选择 → 模板选择 → BGM 选择 → 画面规划创建覆盖组 → 图片资产选择”；所有选择器均从 V2 列表加载稳定资源 ID，成片页显示 `1080×1920`、覆盖组和 BGM 已选择 |
| 真实浏览器一键成片 | 通过（稳定素材） | session `829bc9ca2aec46839bb1170a27df3c05` 在成片页实际点击“一键成片”，生成 `output/ipb_6689a621_final_bgm.mp4` 与 `temp/ipb_cover_6689a621.png`；ffprobe 为 `1080×1920`、5.29s，session step 4/5 为 done，8 个资源快照已写入 |
| 服务级回滚 smoke | 通过 | 临时 API `127.0.0.1:8101` 关闭 `PIXELLE_ASSET_CENTER_V2`：`/health`=200、`/api/v2/library/items`=404，旧 `/api/assets/images` 与 `/api/assets/voices` 仍返回 200；进程已正常停止 |
| 发布安全边界 | 通过（浏览器） | 成片会话进入发布步骤后，抖音/小红书/视频号/快手都展示“自动填充 · 人工发布”，最终发布按钮保持人工操作 |
| Tauri 桌面壳构建与 sidecar | 通过 | Rust 1.97.1 下 `npm run tauri:build -- --bundles app` 成功；从 `/tmp` 启动 release `.app`，内置 `templates/workflows/config.example.yaml` 资源路径正常，sidecar `/health`=200、V2 列表=200 |
| 真实桌面新版资产库 | 通过（Computer Use） | release `.app` 首屏重试后正常加载；资产中心列表、模板缩略图/详情预览、上传弹窗、数字人创建弹窗、图片上传→缩略图→详情→归档刷新均实测通过 |
| 桌面 sidecar V2 开关 | 通过 | 修复 Tauri shell 未转发 `PIXELLE_ASSET_CENTER_V2` 的问题；桌面启动后 V2 路由与前端开关一致，不再误报“后端服务未连接” |
| 发布版 sidecar 完整生产闭环 | 通过 | 发布版 sidecar（隔离 token、app data、内置资源）真实完成资产选择配置→postproduction；task `e026e03c-54c9-4758-998c-244c30bb600f`=`completed`，MP4 `ipb_6068180f_final_bgm.mp4` 为 `1080×1920`，封面 `ipb_cover_6068180f.png` 为 `1080×1920` |
| 发布版无 Playwright 浏览器降级 | 通过 | `HTMLFrameGenerator` 启动失败时按同一模板 CSS 契约使用 PIL 生成封面；`test_packaged_cover_renderer_falls_back_when_playwright_browser_is_missing` 通过 |
| 发布版资源快照账本 | 通过 | session `d76c27f4d4954dacbbc15ef0d1cc9af1` 写入 9 个 snapshot，包含 image/video/audio/voice/digital-human/scene/brand/template，revision SHA 与 renderer version 可追溯 |

## 通过后的控制措施

1. 专用浏览器桥接仍会在运行时初始化时报 `Cannot redefine property: process`，因此浏览器端生产链路继续以 Playwright 验证；Tauri release 壳已能构建、启动并完成资产库真实交互。
2. 已用真实媒体完成“资产管理 → 生产流选择 → 成功渲染”的自动化闭环，并在发布版 sidecar 隔离数据目录内完成包含音色、数字人、品牌、模板、图片/视频覆盖的完整成片回归。
3. 回滚证据已补齐；新版默认开启，但保留 `PIXELLE_ASSET_CENTER_V2=false` 与 `VITE_ASSET_CENTER_V2=false` 的服务级/前端级回滚开关，旧 manifest、旧路由和旧页面进入观察期后再分批清理。

## 放行条件

- 真实桌面生产闭环成功，且最终 MP4、封面、字幕契约和模板 revision 可复现；**已通过**；
- 迁移数量、SHA-256、缺失文件和关键旧 session 的 usage 对账为零差异或有审批记录；
- 复测回滚：关闭 V2 后旧 UI/旧接口仍可继续完成既有任务（服务级 smoke 已通过，待桌面壳复测）；
- 以上证据已归档，默认开关已改为 true；旧实现保留一个观察/回滚窗口，待线上指标稳定后再分批清理。
