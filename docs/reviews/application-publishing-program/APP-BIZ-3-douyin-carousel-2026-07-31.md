# APP-BIZ-3 抖音图文实施与独立复验

- 日期：2026-07-31
- 范围：项目内容、图片素材、3/5/8 页图文规划、三类版式、真实预览、下载和发布中心交接
- 独立审查：Ptolemy（只读审查线程，未修改代码）
- 当前结论：PASS（第六轮独立只读复验）

## 已交付

- 复用项目来源 ArtifactVersion 和已登记素材引用；不接受自由路径或未登记资产。
- 缺少素材描述时由真实多模态分页结构化请求生成一句客观描述，连同 `missing_facts` 写入分页计划、页面和内容包 Artifact；重试时保留或重新生成描述，并同步页面/package 的 model/provider 元数据。
- 固定封面、内容、行动三类版式；固定 3:4（1080×1440）尺寸、连续页码和 3/5/8 页边界。
- `clean-01`、`cover-focus-01`、`action-card-01` 三种风格真实影响渲染结果；单页重试保留版式并限制为原 Run 素材。
- Planner/Executor 对页数、角色、素材白名单、未知模板和事实边界 fail-closed；未确认的具体适用条件、价格、日期、地址和承诺性表述进入一次修复循环，仍不合规则阻断。
- 历史记录展示缺失事实、逐页预览和逐页下载；完整 ZIP 仍可下载并交给发布中心。

## 自动验证

- 后端图文、历史和契约定向测试：`115 passed`。
- Desktop CreationWorkspace、ProjectGenerationHistory、ArtifactActions：`47 passed`。
- Desktop production build：通过。
- `git diff --check`：通过。

## 真实闭环证据

通过当前默认 `local-default` 模型、真实仓库门店照片和真实 `AppRunner` 执行 8 页 Run：

- 输出目录：`/var/folders/lt/6g5zql0d37g7pvzj7gny8g4r0000gn/T/pixelle-carousel-real-clinic-8-tq4cp_mm`
- AppRun：`run_932f930451734cd48f13c86068ed3595`
- 状态：`needs_review`
- 模型记录：`local-default:doubao-seed-2-0-pro-260215` / `openai_compatible`
- Artifact：`carousel_plan`、`carousel_page × 8`、`carousel_package`、来源 `selected_title`
- 版式顺序：`cover`、`content × 6`、`action`
- 8 张 PNG 均为 1080×1440；ZIP 可读且恰含 8 张 PNG；`missing_facts` 已持久化并投影到历史记录。
- 素材描述为 `嘉口腔门店外立面实拍图`；已人工检查真实门店图片生成的第 1 页和第 8 页，图文与门店/到店咨询目标一致。
- 发布中心交接已在同目录 `publishing.sqlite` 完成并验证：package `pkg_91fa84dbb62428295b3667d44b409327` 未失效，9 个 source ArtifactVersion 完全匹配；`publish_package_ref` 为 `artifact_version_6ebc7c77d0284ae1ad4be8a1ef5c772b`，引用 ID 一致。

## 独立复验循环

第一至三轮发现并修复版式角色、缺失事实、素材描述、逐页下载、重试绑定、v2 schema、模板实际渲染、历史投影和 Publish handoff 证据缺口；第四轮补齐页面资产白名单、多模态输入、重试描述一致性、模板 fail-closed；第五轮补齐 Runner model/provider 元数据和真实项目素材；第六轮补齐素材事实边界并完成最终 PASS。审查线程全程只读，未修改代码。
