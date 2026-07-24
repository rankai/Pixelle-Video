# DH-DUAL-2 桌面双模式与素材体验实现（2026-07-24）

## 状态

实现已完成，等待独立六维复审。当前候选 Gate：`PG-DH-C`。

## 实现内容

- 桌面 flag 解析新增 `VITE_APP_CENTER_DIGITAL_HUMAN_DUAL_MODE`，并与后端 `digitalHumanInAppCenter` 联合 gate；未同时开启时应用卡片不可操作。
- 数字人应用升级为 V2 `1.1.0` payload，支持 `image_talking` 与 `video_lipsync`；原有空白项目、已有文案和恢复路径继续保留。
- `AssetPickerDialog` 支持按 `PickerContext.media_type` 过滤数字人 scene；不兼容 scene 禁用并展示原因；视频 scene 使用受保护的 blob URL 和原生 `video controls` 预览。
- 选择 scene 后写入 `portrait_id`、`scene_id`、`source_revision_id`，展示图片/视频类型、revision、分辨率、时长和质量提示；切换到不兼容模式会清理素材选择但保留制作目标/文案。
- pending/run 恢复读取 V2 `content_source` 和 `digital_human` 嵌套字段，恢复 mode、来源版本、scene、pinned revision 与输入；创建请求保持幂等键预写和 busy 防重复提交。
- 初次入口的唯一主动作改为“开始生成”：一次点击先幂等创建 AppRun，再立即调用 execute；运行已存在时，单独的运行状态区仍提供开始生成/重试/取消/人工接收。
- create 成功后先持久化 `execute` phase 和 `app_run_id`，若 execute 响应丢失，重启/回读仍指向同一 AppRun，不会重复创建；仅在 execute 成功后清理 pending。
- 运行状态区主动作改为“开始生成”；needs_review/completed 默认交付 final video、cover、publish copy，默认下载请求使用 `final_video`，原始数字人视频只在诊断折叠区出现。
- 应用中心目录的数字人入口仅在联合 readiness 通过时可用；旧 `/ip` 路由、最终人工确认门和平台发布边界未改变。

## 验证证据

- 桌面 Vitest：`11 files / 67 tests passed`。
- 桌面构建：`npm run build`（`tsc` + Vite）通过；仅保留既有大 chunk warning。
- 服务端双模式聚合回归：`110 passed, 12 existing Pydantic warnings`。
- 目标文件 Ruff format/check、JSON 解析和 `git diff --check` 通过；未修改文件的历史 format 提示未纳入本批结论。
- In-app Browser 真实页面：在本地 FastAPI + Vite 环境打开应用中心，确认四个应用卡片和数字人入口；进入数字人应用后确认图片/视频 Tab、V2 `1.1.0`、素材入口和“开始生成”前置状态；真实 `/api/v2/library/items?kind=digital_human` 返回 `capabilities=digital_human`、profile/scene 的 `width/height/duration_ms`。
- 真实选择器交互：图片模式打开选择器，选中 `美女` 图片场景并点击“确认使用”，页面回读 `图片场景`、`revision 已锁定`、`944×1280`、`质量：已就绪`；视频模式打开选择器时图片资产禁用并明确提示“当前模式只支持视频场景”。全过程未触发 Provider。
- 真实视频 scene 边界：当前本地真实 AssetLibrary 没有登记视频 scene，因此没有把图片 asset 冒充视频预览；视频 scene 的可播放 controls 和 mixed-profile 过滤由定向 Vitest 覆盖，待后续真实视频资产登记后再补桌面 live 选择证据。
- 可追溯视觉/交互证据已归档到 [`qa/DH-DUAL-2-visual-2026-07-24/`](qa/DH-DUAL-2-visual-2026-07-24/)：应用中心、双模式、窄视口、图片选择器、确认回填、视频模式边界截图，以及对应 DOM snapshot；截图 SHA-256 记录在 QA JSON。
- 1440×900 页面截图已采集；1280×800 与 900×760 测得 `scrollWidth == clientWidth`，无横向溢出。
- Provider、浏览器平台、第三方授权、真实上传和最终发布点击：均为 0。

## 六维复审边界

- 本批验证的是桌面入口、资产选择与 payload/恢复契约；needs_review/completed 结果区会通过受保护的 `artifactBlobUrl(session_id, "final_video")` 加载真实 final video 预览，不等价于 RunningHub/TTS 真实生成或视频唇形质量通过。
- 字幕/封面质量和媒体后期完整性由后续 `DH-QUALITY-1` 负责。
- 未开启自动点击最终发布；人工确认仍是唯一发布前边界。

## 下一步

交独立线程按需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六维复验；仅在 P0/P1=0 且 PG-DH-C 通过后切换至 `DH-QUALITY-1`。
