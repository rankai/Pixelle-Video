# 企业资产库完整重构调研报告与实施方案

> 日期：2026-07-17
> 交付对象：Luna（实施）、产品负责人（验收）
> 范围：企业视频、图片、数字人、声音、品牌、画面模板资产；视频生产流中的选择、快捷上传、复用和使用追踪
> 文档性质：调研与实施蓝图，不包含本轮代码实现

## 1. 结论先行

当前企业资产库已经具备“上传、列表、预览、删除、在部分生产步骤中选择”的基础能力，但它仍然是六套并列的文件 CRUD 页面，并不是一个可支撑中小企业长期经营视频资产的资产系统。

这不是单纯换一套卡片样式能解决的问题。需要同时重构四层：

1. **领域模型**：把视频、图片、声音等媒体统一到媒体资产内核；数字人、品牌和模板保留各自领域模型，再通过统一资源索引提供一致的搜索、分类和使用追踪。
2. **管理体验**：形成统一的搜索、筛选、排序、网格/列表、详情、编辑、归档、批量管理和上传中心。
3. **生产流集成**：所有生产步骤使用同一个 `AssetPicker`，支持“最近使用、收藏、当前任务、快捷上传、选中即回填”，避免在资产库与生产任务之间跳转。
4. **数字人模型**：从“一个图片或视频文件”升级为“数字人档案 + 可用场景 + 预览片段 + 生成能力/限制”。用户参考图真正优秀的地方不是视觉风格，而是把“浏览、筛选、预览、选场景、使用”放在一个上下文里完成。

建议以 **统一媒体资产内核 + 领域资源模型 + 共享前端组件 + 旧接口兼容层** 的方式渐进式替换，不要在一次大提交中推倒重来。完整范围的基础工作量约 **21–28 人日**，加入迁移和桌面环境风险缓冲后按 **24–32 人日** 安排，共七个可独立验收的阶段；如先交付 MVP，则建议控制在 **15–20 人日**。

---

## 2. 调研范围、证据与限制

### 2.1 已检查的证据

- 前端资产中心、上传弹窗、预览弹窗、删除弹窗、视频素材选择器、模板选择器和数字人生产步骤：`desktop/src/StudioApp.tsx`。
- 资产相关样式和不同媒体的缩略图规则：`desktop/src/styles.css`。
- 前端 API 类型与上传/删除接口：`desktop/src/api.ts`。
- 后端六类资产接口：`api/routers/assets.py`。
- 视频、图片、数字人、音色、品牌资产的本地持久化服务和 JSON manifest。
- 当前本地数据：2 个视频、2 个图片型数字人、2 个音色、1 个品牌包；图片素材 manifest 当前为空/尚未建立。
- 现有资产 API 和桌面端资产操作测试。
- 用户提供的数字人管理参考图：`/var/folders/lt/6g5zql0d37g7pvzj7gny8g4r0000gn/T/codex-clipboard-2d8b3b5a-e063-4407-b582-a8bab9a51849.png`。
- 用户提供的竖屏 MP4：1080×1920、25 fps、22.45 秒、H.264 + AAC。该文件很适合作为“数字人场景预览片段”的真实样本，而不应只按一个无元数据的视频文件处理。

### 2.2 证据限制

本次本地应用已启动，API 可用；但用于本轮审计的应用内浏览器连接在宿主运行时初始化阶段触发 `Cannot redefine property: process`，因此没有把“当前资产库逐屏截图”伪装成已完成的视觉走查。该错误尚未证明属于 Pixelle 产品代码，不能直接作为 Luna 的产品缺陷任务。以下判断以用户的实际操作反馈、源码、CSS、API、现有数据和提供的参考素材为依据。实施阶段应使用稳定的桌面端截图/E2E 手段补齐基线；只有在产品内可复现时再单独修复浏览器问题。

这项限制不影响结构性结论：缺少统一查询、元数据、使用关系、共享选择器和数字人档案/场景模型，都可以直接由代码和接口确认。

---

## 3. 当前用户流程审计

### 3.1 当前主流程

1. 用户进入“企业资产库”。
2. 在视频、图片、音色、形象、模板、品牌六个页签之间切换。
3. 点击当前分类的“添加”按钮，填写一个可选名称并选择一个文件。
4. 上传成功后刷新列表，以卡片方式查看文件。
5. 通过卡片上的“预览”打开通用媒体弹窗，或通过“删除”进入二次确认。
6. 进入视频生产流后，在数字人、画面规划、配音或后期步骤里再次选择部分资产。
7. 某些步骤允许快捷上传；某些步骤需要跳回资产库管理。
8. 视频规划对素材的自动匹配主要依赖视频资产名称中的关键词。

### 3.2 流程健康度

| 环节 | 当前状态 | 主要问题 | 影响 |
|---|---|---|---|
| 分类浏览 | 可用 | 六个页签只有切换，没有数量、搜索、筛选、排序和跨类型视图 | 资产一多就无法管理 |
| 列表展示 | 可用但不友好 | 固定高度、不同类型规格不一致、原始文件名占据主信息位 | 图片/竖屏视频难判断内容，扫描效率低 |
| 搜索 | 局部可用 | 主资产库无搜索；只有视频和模板选择弹窗有名称/文件名搜索 | 用户必须记住分类和命名 |
| 上传 | 基础可用 | 单文件、无本地预览、无真实拖放、无进度/取消、无批量、无重复检测 | 企业批量导入成本高，失败不透明 |
| 预览 | 基础可用 | 通用媒体弹窗只播放文件，没有详情、标签、版本、场景和使用入口 | 预览和决策割裂 |
| 编辑管理 | 不完整 | 图片/视频/数字人/音色无法重命名或编辑元数据；删除是卡片常驻主操作 | 资产不可维护，误删风险高 |
| 生产流选择 | 部分可用 | 不同步骤重复实现，能力不一致；图片没有真正进入画面规划 | “资产库可复用”与实际体验不一致 |
| 数字人 | 概念过薄 | 目前只是图片/视频文件；没有人物档案、场景、姿态、风格、预览片段 | 无法达到参考产品的选择体验 |
| 使用关系 | 缺失 | 不知道资产在哪些任务、镜头、封面中被使用 | 无法安全归档、替换或治理 |

### 3.3 已经做对、应当保留的部分

- 六类资产都有清晰入口，用户能理解分类。
- 图片、视频、音频均已有受保护的预览路径。
- 删除已经有确认弹窗和失败反馈，不能回退为直接删除。
- 生产流中的数字人快捷上传可以“上传后自动选中”，这个闭环应推广到全部资产类型。
- 上传服务有扩展名、文件大小和安全路径校验；新架构应复用这些安全能力。
- 现有主题变量已经能承载紫色和珊瑚红主题；资产组件不得引入硬编码品牌主色。

---

## 4. 根因分析：为什么“功能有了，但不好用”

### 4.1 六套数据结构导致六套体验

当前 ID 字段分别是 `asset_id`、`portrait_id`、`reference_id`、`brand_id`、`template_id`，文件也分别由不同 service 和 JSON manifest 管理。字段集合非常薄：

- 图片：名称、文件名、时间、字节数。
- 视频：再多一个时长和第一帧缩略图。
- 数字人：名称、文件名、媒体类型。
- 音色：名称、文件名、时间。
- 品牌包和模板又是完全独立的模型。

结果是前端不能拥有统一的查询、卡片、详情、收藏、标签、使用记录、批量操作或选择器，只能不断写类型特例。

### 4.2 主资产库没有真正的检索系统

主资产库没有查询输入、标签、日期、比例、时长、来源、状态、收藏、最近使用等筛选。生产流里的视频选择器只按 `name + filename` 做前端字符串过滤；自动推荐只把视频名称与关键词比较。

对企业素材而言，“门店”“菜品”“锅底”“团购”“老板口播”“可用于封面”“竖屏”“无版权 BGM”才是检索语言，原始文件名不是。

### 4.3 图片展示问题是信息架构问题，不只是 `object-fit`

当前图片卡片强制使用约 148px 高的预览区域并以 `cover` 展示；视频和数字人又分别使用 158px、192px 与 `contain`。这会造成：

- 横图、竖图、透明 PNG 的显示语义不同。
- 图片可能被裁切，用户看不到完整构图和安全区。
- 卡片高度、信息密度和视觉重心不一致。
- 用户只能看到名称与原始文件名，看不到比例、尺寸、格式、用途和状态。

正确方案是“统一卡片骨架 + 按媒体类型选择预览画布”，而不是让所有图片使用同一裁切方式。

### 4.4 上传弹窗只有文件选择，没有资产入库流程

`FileDropField` 的视觉是拖放区域，但目前没有 `dragenter/drop` 处理；上传弹窗也没有：

- 选中文件后的本地预览和媒体信息。
- 上传进度、取消、重试。
- 批量队列和逐项错误。
- 命名、分类、标签、用途、版权/来源字段。
- 重复文件哈希检测和“跳过/替换/另存”选择。
- 针对数字人的质量检查结果。

因此它更像“把一个文件存到目录”，不是“把可复用资产纳入企业资产库”。

### 4.5 数字人被错误地建模成一个文件

参考图中至少存在三层实体：

1. **数字人档案**：人物身份、外观、性别、风格、姿态、能力和来源。
2. **场景/造型**：厨房、办公室、近景、全身、服装、手持商品等。
3. **预览和生产配置**：可播放片段、景别、默认场景、生成方式、支持的分辨率/动作。

当前 `PortraitAsset` 只有 `portrait_id/name/file/media_type`。即使把参考图的布局照搬过来，右侧也没有足够数据展示，所以必须先改领域模型。

### 4.6 资产库和生产流是两套产品

当前存在独立的 `VideoAssetPickerModal`、`TemplatePickerModal`、数字人卡片网格、音色选择逻辑和若干快捷上传弹窗。它们的搜索、预览、空状态、选择状态、上传反馈、兼容性校验都不一致。

图片资产目前虽然写着“可在画面规划和封面制作中复用”，但 `VisualGroup` 的类型只有 `digital_human | ai_video | uploaded_video`，图片没有成为正式可选视觉源。这是承诺与能力的直接断层。

---

## 5. 参考图应该借鉴什么

参考图的核心价值不是蓝色，而是以下交互结构：

- 左侧把分类、来源、收藏、性别、风格、姿态与人物卡片放在同一浏览区域。
- 单击人物后立即显示明确选中态，并在右侧打开可播放的大预览。
- 人物与场景分层；选中人物后仍可选择厨房、厨房 1 等场景。
- 预览与设置同屏，用户不需要“选中 → 关闭 → 再去另一个页面验证”。
- 竖屏人物素材按接近最终成片的画幅展示，决策信息充分。

不建议照搬的部分：

- 中小企业自有数字人通常不多，第一版不必一开始堆满性别、风格、姿态等所有筛选。应只显示有数据的 facets。
- 主资产库中的单击应进入预览/详情；生产选择器中的单击可以切换预览，最终“使用此数字人”保持明确按钮，避免误选。
- 颜色必须使用系统主题 token，参考图的蓝色不应硬编码进现有紫色/珊瑚红主题系统。

---

## 6. 目标产品模型

### 6.1 统一的是资源索引，不是把所有对象塞进一张资产表

视频、图片和音频属于媒体资产；品牌包是复合业务配置；模板是版本化渲染契约；数字人是人物档案和场景集合。它们应在资产库界面中统一浏览，但后端不能被迫使用一个充满类型特例的万能表。

资产库查询返回统一投影：

```ts
type LibraryItemKind =
  | "video"
  | "image"
  | "voice"
  | "digital_human"
  | "template"
  | "brand";

type LibraryItem = {
  resourceId: string;
  kind: LibraryItemKind;
  name: string;
  description: string;
  status: "processing" | "ready" | "warning" | "failed" | "archived";
  coverUrl?: string;
  tags: string[];
  favorite: boolean;
  createdAt: string;
  updatedAt: string;
  summary: Record<string, string | number | boolean>;
};
```

`LibraryItem` 是搜索和界面的只读投影，不是所有领域对象的唯一持久化模型。编辑时根据 `kind` 调用对应领域接口。

### 6.2 媒体资产、版本和变体

图片、视频、音频、字体等文件使用统一媒体内核：

```ts
type MediaKind = "video" | "image" | "audio" | "font";

type MediaAsset = {
  id: string;
  legacyId?: string;
  mediaKind: MediaKind;
  name: string;
  description: string;
  source: "upload" | "recording" | "generated" | "system" | "imported";
  currentRevisionId: string;
  status: "processing" | "ready" | "warning" | "failed" | "archived";
  createdAt: string;
  updatedAt: string;
  archivedAt?: string;
};

type AssetRevision = {
  id: string;
  assetId: string;
  version: number;
  parentRevisionId?: string;
  relativePath: string;
  mimeType: string;
  bytes: number;
  sha256: string;
  width?: number;
  height?: number;
  aspectRatio?: number;
  durationMs?: number;
  frameRate?: number;
  hasAudio?: boolean;
  createdAt: string;
};

type AssetVariant = {
  id: string;
  revisionId: string;
  role: "poster" | "thumbnail" | "preview" | "proxy" | "waveform" | "cover_crop";
  relativePath: string;
  mimeType: string;
  width?: number;
  height?: number;
  durationMs?: number;
};
```

原文件对应不可变的 `AssetRevision`。用户选择“作为新版本”时创建新 revision 并更新 `currentRevisionId`；标签、集合和使用历史仍属于逻辑资产。裁切、poster、代理视频和波形属于 revision 的变体，不覆盖原文件。

### 6.3 品牌、模板和数字人领域模型

```ts
type BrandKitResource = {
  id: string;
  name: string;
  logoAssetId?: string;
  fontAssetIds: string[];
  defaultBgmAssetId?: string;
  primaryColor: string;
  secondaryColor: string;
  contact: Record<string, string>;
  publishDefaults: Record<string, unknown>;
};

type TemplateDefinition = {
  id: string;
  name: string;
  schemaVersion: number;
  rendererVersion: string;
  revision: number;
  previewAssetId: string;
  coverContract: Record<string, unknown>;
  subtitleContract: Record<string, unknown>;
  status: "draft" | "ready" | "archived";
};

type DigitalHumanProfile = {
  id: string;
  name: string;
  provider: "local" | "system" | "custom";
  posterAssetId?: string;
  gender?: string;
  style?: string;
  posture?: "sitting" | "standing" | "mixed";
  supportedWorkflows: string[];
  defaultSceneId?: string;
  qualityState: "unchecked" | "passed" | "warning" | "failed";
};

type DigitalHumanScene = {
  id: string;
  profileId: string;
  name: string;
  sourceAssetId: string;
  sourceRevisionId: string;
  previewVariantId?: string;
  shotSize?: "close" | "medium" | "full";
  location?: string;
  outfit?: string;
  posture?: string;
};
```

模板 revision 和 renderer version 必须随任务一起锁定，防止模板升级后旧任务的字幕、字体和封面位置发生漂移。用户提供的 1080×1920、22.45 秒 MP4 应先作为 `MediaAsset` 入库，再由 `DigitalHumanScene` 引用指定 revision；人物名称和“客厅/门店/办公室”等场景名称由用户确认。

### 6.4 集合、使用关系与渲染快照

```ts
type AssetCollection = {
  id: string;
  name: string;
  description: string;
  sortOrder: number;
  createdAt: string;
  updatedAt: string;
};

type ResourceUsage = {
  id: string;
  resourceKind: LibraryItemKind;
  resourceId: string;
  revisionId?: string;
  sessionId: string;
  step: "source" | "voice" | "digital_human" | "storyboard" | "cover" | "postproduction" | "publish";
  purpose: string;
  slotId: string;
  createdAt: string;
  updatedAt: string;
};

type ResourceSnapshot = {
  resourceKind: LibraryItemKind;
  resourceId: string;
  revisionId?: string;
  variantId?: string;
  sha256?: string;
  resolvedRelativePath?: string;
  templateRevision?: number;
  rendererVersion?: string;
};
```

`ResourceUsage` 的唯一键为 `sessionId + step + slotId + purpose + resourceKind + resourceId`。用户替换或移除素材时必须在同一事务中删除旧关系、写入新关系。渲染启动时生成 `ResourceSnapshot`，锁定具体 revision、hash、模板 revision 和 renderer version，保证后续重命名、归档或模板升级不影响已开始任务。

### 6.5 持久化选择

推荐从多份 JSON manifest 迁移到本地 SQLite：

- SQLite 在单机桌面场景中支持事务、分页、索引和关系查询，不需要引入外部数据库。
- 优先检测 FTS5；不可用时回退到普通索引和 `LIKE` 查询，不能阻塞应用启动。
- 原始媒体文件继续存放在数据目录，数据库只存元数据和相对路径。
- 删除改为归档；只有“回收站彻底删除”才移除文件。
- 收藏和标签统一挂在资源索引层；业务字段保留在各自领域表。

建议表：`media_assets`、`asset_revisions`、`asset_variants`、`library_index`、`resource_tags`、`resource_favorites`、`resource_usages`、`resource_collections`、`collection_items`、`brand_kits`、`template_definitions`、`digital_human_profiles`、`digital_human_scenes`、`media_jobs`、`asset_migration_log`。

---

## 7. 企业资产库页面重构规格

### 7.1 页面信息架构

```text
企业资产库
├── 顶部：全库搜索 / 上传资产 / 新建集合
├── 分类：全部 / 视频 / 图片 / 数字人 / 声音 / 模板 / 品牌
├── 智能入口：最近使用 / 收藏 / 当前任务 / 待处理 / 回收站
├── 工具栏：筛选 / 排序 / 网格-列表切换 / 批量选择
├── 内容区：统一资产卡片或列表
└── 右侧详情抽屉：预览 / 信息 / 标签 / 使用记录 / 版本与变体 / 操作
```

默认落在“全部”或用户上次访问的分类。分类页签显示数量，但数量只作为辅助，不做夸张的数据看板。

### 7.2 搜索与筛选

全局搜索至少覆盖：

- 名称、描述、原始文件名。
- 标签、集合、场景、地点、人物名、品牌名。
- 图片/视频的比例、分辨率、时长和方向。
- 数字人的性别、风格、姿态、场景、支持的生成方式。
- 声音的语言、风格、性别、时长。

基础筛选：类型、收藏、标签、创建时间、最近使用、来源、状态。进入某一类型后再显示该类型专用筛选，例如视频的横/竖屏和时长、数字人的风格/姿态/场景。

筛选采用可见 chips，并提供“一键清除”。没有数据的 facet 不显示，避免参考图式的筛选密度在小资产库中显得空洞。

### 7.3 卡片系统

建立统一 `AssetCard` 骨架，媒体渲染器按类型替换预览区域：

| 类型 | 预览规则 | 卡片辅助信息 | 快捷操作 |
|---|---|---|---|
| 图片 | 完整图优先 `contain`；透明图使用棋盘格；可切换“填充预览” | 尺寸、比例、格式、标签 | 预览、使用、收藏 |
| 视频 | 使用 poster；角标显示时长和横/竖屏；悬停可静音预览 | 时长、分辨率、是否有声 | 播放、使用、收藏 |
| 数字人 | 3:4 或 9:16 人物海报；显示场景数量和质量状态 | 人物名、默认场景、支持方式 | 预览、使用、收藏 |
| 声音 | 行式卡片或波形缩略图；点击试听 | 时长、语言、风格 | 试听、使用、收藏 |
| 模板 | 固定 9:16 安全区预览 | 模板风格、字幕/封面能力 | 预览、应用 |
| 品牌 | Logo、主辅色和字体组合预览 | 品牌名、默认状态 | 设为默认、编辑 |

卡片底部不再常驻红色“删除”。危险操作放到 `…` 菜单中，默认动作为“预览/使用”。被生产任务引用的资产只能归档，并展示使用数量。

### 7.4 图片规范显示

针对用户指出的图片不友好，必须达到以下规格：

- 网格卡片预览框比例固定，但默认完整展示，不裁掉主体。
- 显示原图比例徽标：`9:16`、`16:9`、`1:1`、`4:3` 或“自定义”。
- 显示像素尺寸与透明通道状态；封面/Logo 可显示安全区叠层。
- 详情预览支持适应窗口、100%、填充、棋盘格背景和深浅背景切换。
- 同一资产可拥有原图、缩略图、封面裁切等变体，裁切不覆盖原文件。
- 图片加载失败显示可恢复错误和“重新生成缩略图”，不能只显示破图。

### 7.5 上传中心

上传不再为每一类复制一个弱弹窗，统一为 `AssetUploadDialog`：

1. 选择资产类型或由当前上下文预设。
2. 支持点击、真实拖放、多文件选择。
3. 立即显示本地缩略图、文件名、大小、比例/时长和格式校验。
4. 后台计算哈希并检测重复，提供“跳过、作为新版本、仍然新建”。
5. 批量设置标签、集合、来源；允许逐项修改名称。
6. 展示逐文件上传/分析进度，支持取消、重试和移除。
7. 入库后异步生成缩略图、poster、代理预览、波形和质量检查结果。
8. 从生产流打开时，成功资产自动返回选择器并选中，不丢失当前任务状态。

“素材规范”必须是可点击帮助，不要再以普通彩色文字伪装成链接。规则应根据类型显示硬限制和建议，并在选择文件后给出具体校验结论。

### 7.6 详情与管理

点击卡片打开右侧详情抽屉；需要沉浸预览时再进入全屏预览。抽屉包含：

- 预览及媒体控制。
- 可编辑名称、描述、标签、集合。
- 自动提取信息和质量状态。
- 文件来源、创建/更新时间。
- “用于哪些任务/镜头/封面”的使用记录。
- 版本/变体和替换入口。
- 归档、恢复、彻底删除等低频操作。

批量模式支持：加标签、加入集合、收藏、归档、导出信息；第一版不要支持跨类型批量替换。

---

## 8. 数字人管理完整方案

### 8.1 资产库中的数字人页面

桌面宽屏采用参考图的双栏结构：

```text
┌ 人物列表与筛选（约 42%） ┬ 大预览与详情（约 58%） ┐
│ 官方/自定义、收藏、搜索   │ 9:16 可播放预览          │
│ 风格、姿态、场景筛选       │ 人物状态与能力提示        │
│ 3 列人物卡片               │ 场景缩略图列表            │
│ 上传/新建数字人            │ 编辑、复制、归档、用于生产 │
└───────────────────────────┴──────────────────────────┘
```

交互规则：

- 单击人物卡片：改变选中态并在右侧立即加载预览，不再要求点击卡片底部的小“预览”按钮。
- 单击场景：在右侧播放器切换对应场景预览，并更新兼容性信息。
- 视频预览默认不自动发声；用户明确点击播放后再播放音频。
- 当前选中人物、场景都有边框、勾选和文本状态，不能只依赖颜色。
- 管理模式的主按钮为“用于视频生产”；生产选择器中的主按钮为“使用此数字人”。
- 图片型与视频型数字人明确标识能力差异，不允许选中后才发现当前工作流不支持。

### 8.2 数字人上传与质量检查

入库时自动检查：

- 媒体类型、分辨率、比例、帧率、时长、音轨。
- 人脸是否清晰、主体是否过小、是否多人、是否遮挡。
- 视频是否存在大幅镜头运动、明显剪切、过强背景噪声。
- 与所选生成工作流的分辨率和媒体类型兼容性。

第一阶段可以只做确定性的媒体检查，把需要模型判断的项目标为“未检查”；不要假装所有 AI 质量判断已可靠完成。

### 8.3 数字人在生产流中的选择器

数字人步骤使用全屏或大尺寸 `AssetPickerDialog`，复用同一双栏内容，但增加：

- 顶部显示当前生成方式及它支持的媒体类型。
- 不兼容的人物保留可见但禁用，并说明原因；不要直接过滤到消失。
- 选中人物后继续选场景和景别。
- “快捷上传”继承当前工作流约束，上传完成后自动选择。
- 确认后一次性回填 `profileAssetId + sceneId + workflow + dimensions`。
- 回到步骤后显示一个完整的“已选数字人摘要卡”，可预览、替换、编辑场景。

---

## 9. 视频生产流集成矩阵

| 生产步骤 | 可用资产 | 集成方式 | 应记录的使用关系 |
|---|---|---|---|
| 企业/选题资料 | 品牌、产品图片、案例视频 | 选择参考资产，作为文案和视觉上下文 | `source/reference` |
| 文案 | 品牌包 | 自动带入品牌名、地址、电话、优惠语和禁用词 | `source/brand` |
| 配音 | 音色 | 共享声音选择器，支持试听、最近使用、快捷录制/上传 | `voice/reference` |
| 数字人 | 数字人档案、场景 | 双栏预览与兼容性选择 | `digital_human/profile`、`scene` |
| 画面规划 | 视频、图片、数字人 | 每个镜头 slot 打开同一选择器；支持多选素材池 | `storyboard/visual` |
| 一键成片/后期 | 模板、视频、图片、BGM、品牌 | 模板与品牌默认项可继承，允许逐项覆盖 | `postproduction/*` |
| 封面 | 图片、模板、品牌 Logo/颜色/字体 | 从图片库选择底图并显示标题安全区 | `cover/background`、`brand` |
| 发布准备 | 品牌、封面、成片 | 自动填充平台标题/描述/话题的品牌默认信息 | `publish/*` |

### 9.1 共享选择器协议

所有步骤只传上下文，不自己实现资产列表：

```ts
type AssetPickerRequest = {
  context: "source" | "voice" | "digital_human" | "storyboard" | "cover" | "postproduction";
  allowedKinds: LibraryItemKind[];
  selectionMode: "single" | "multiple";
  selected: Array<{ kind: LibraryItemKind; resourceId: string }>;
  constraints?: {
    mediaTypes?: string[];
    orientations?: Array<"portrait" | "landscape" | "square">;
    minDurationMs?: number;
    maxDurationMs?: number;
    workflow?: string;
  };
};

type AssetPickerResult = {
  items: LibraryItem[];
  digitalHumanSceneId?: string;
};
```

共享选择器内固定具备：搜索、筛选、最近使用、收藏、预览、详情、快捷上传、兼容性提示、空状态和失败恢复。选择器只消费统一资源投影；确认选择后，由对应生产步骤把资源引用转换为自己的领域配置和 `ResourceSnapshot`，避免让模板、品牌和数字人伪装成普通文件。

### 9.2 自动推荐

第一阶段使用可解释的规则评分：

- 名称、描述、标签、集合与镜头关键词命中。
- 方向/时长/分辨率与 slot 约束匹配。
- 最近使用和同一任务已使用可作为轻度加权。
- 明确标注“推荐原因”，允许用户关闭推荐筛选。

语义向量检索放在后续阶段。先把结构化元数据和使用记录做对，否则 AI 搜索只会掩盖数据质量问题。

---

## 10. 前端共享组件与目录方案

建议把资产功能从超过 6000 行的 `StudioApp.tsx` 中完整拆出：

```text
desktop/src/features/assets/
├── api/
│   ├── assetApi.ts
│   └── assetQueries.ts
├── model/
│   ├── assetTypes.ts
│   ├── assetFilters.ts
│   └── assetPicker.ts
├── components/
│   ├── AssetCenterPage.tsx
│   ├── AssetCategoryTabs.tsx
│   ├── AssetToolbar.tsx
│   ├── AssetGrid.tsx
│   ├── AssetList.tsx
│   ├── AssetCard.tsx
│   ├── AssetMediaPreview.tsx
│   ├── AssetDetailDrawer.tsx
│   ├── AssetPickerDialog.tsx
│   ├── AssetUploadDialog.tsx
│   ├── AssetUploadQueue.tsx
│   ├── AssetUsagePanel.tsx
│   └── AssetEmptyState.tsx
├── digital-human/
│   ├── DigitalHumanBrowser.tsx
│   ├── DigitalHumanCard.tsx
│   ├── DigitalHumanPreview.tsx
│   ├── DigitalHumanSceneList.tsx
│   └── DigitalHumanQuality.tsx
├── hooks/
│   ├── useAssets.ts
│   ├── useAssetPicker.ts
│   └── useAssetUpload.ts
└── index.ts
```

关键约束：

- `AssetCard` 只管理共享骨架；媒体差异交给 renderer，不堆满 `if (kind === ...)`。
- 管理页和生产选择器复用查询、卡片、预览、上传、筛选，只在 action 区域不同。
- 资产选择状态由选择器内部管理，确认后再提交给生产 session，避免每次点卡片都触发远程 patch。
- 数据请求应有缓存和失效策略；上传/编辑后只失效相关分类，不重新请求所有应用数据。
- 主题只使用现有 CSS 变量和 Ant Design token，紫色、珊瑚红均需通过同一组件视觉回归。

---

## 11. 后端与 API 方案

### 11.1 推荐目录

```text
pixelle_video/services/library/
├── models.py
├── repository.py
├── search.py
├── collections.py
├── usage.py
└── migration.py

pixelle_video/services/media/
├── upload.py
├── metadata.py
├── variants.py
└── jobs.py

api/routers/library_v2.py
api/routers/media_assets_v2.py
api/routers/digital_humans_v2.py
api/routers/brand_kits_v2.py
api/routers/templates_v2.py
```

现有 `video_asset_service.py`、`image_asset_service.py`、`portrait_service.py`、`voice_reference_service.py` 和 `brand_kit_service.py` 暂时保留为兼容适配器，内部逐步转调新 repository；不要立刻删除旧 manifest 读取能力。

### 11.2 API 草案

统一查询与通用管理：

```text
GET    /api/v2/library/items?q=&kind=&tags=&status=&favorite=&collection=&sort=&cursor=&limit=
GET    /api/v2/library/facets?kind=
POST   /api/v2/library/bulk
GET    /api/v2/library/{kind}/{resource_id}/usage
POST   /api/v2/library/{kind}/{resource_id}/archive
POST   /api/v2/library/{kind}/{resource_id}/restore
GET    /api/v2/collections
POST   /api/v2/collections
PATCH  /api/v2/collections/{collection_id}
POST   /api/v2/collections/{collection_id}/items
DELETE /api/v2/collections/{collection_id}/items/{kind}/{resource_id}
```

媒体、版本和上传：

```text
POST   /api/v2/uploads                         # 创建上传会话并预检大小/磁盘
PUT    /api/v2/uploads/{upload_id}/content     # 流式写入 .part 临时文件
GET    /api/v2/uploads/{upload_id}             # uploading/analyzing/ready/failed
POST   /api/v2/uploads/{upload_id}/cancel
GET    /api/v2/media-assets/{asset_id}
PATCH  /api/v2/media-assets/{asset_id}
GET    /api/v2/media-assets/{asset_id}/revisions
POST   /api/v2/media-assets/{asset_id}/revisions
POST   /api/v2/media-assets/{asset_id}/revisions/{revision_id}/activate
POST   /api/v2/media-assets/{asset_id}/analysis/retry
```

数字人、品牌和模板使用各自领域接口。统一列表接口只返回 `LibraryItem` 投影；编辑和版本操作不通过万能 PATCH。列表接口服务端分页、筛选和排序，返回 `items/next_cursor/total/facets`。

v2 接口不返回绝对磁盘路径。旧兼容接口在迁移窗口内可继续返回旧字段；生产流完成资产 ID 和快照迁移后再移除该例外。

### 11.3 上传传输和任务恢复

当前 `_read_upload()` 会一次性把文件读入内存，不能直接承载批量视频上传。v2 必须采用以下确定方案：

1. 客户端先创建 upload session，提交文件名、类型、声明大小和目标行为（新建/新版本）。
2. 服务端检查单文件上限、批次上限和数据目录可用磁盘空间。
3. 客户端桌面 WebView 使用 `XMLHttpRequest.upload.onprogress` 展示真实上传进度；若后续切换 Tauri 原生上传，则保持相同 upload session 协议。
4. 服务端以固定大小 chunk 从 `UploadFile` 写入同一数据目录下的 `.part` 文件，不得把完整文件保存在 Python 内存中。
5. 完成字节数、MIME、哈希和安全校验后，以原子 rename 转为 revision 原文件；取消或失败清理 `.part`。
6. 分析任务写入 SQLite `media_jobs`，使用现有任务管理器或受控 `ThreadPoolExecutor` 执行；本地桌面版本不引入 Celery/Redis。
7. 应用启动时把长时间停留在 `running` 的任务重置为 `pending` 并继续处理，同时清理超过保留期且没有数据库记录的临时文件。
8. 客户端轮询或订阅 upload status，分别展示上传与分析阶段；批量上传默认限制并发数，避免同时转码拖垮桌面端。

### 11.4 元数据流水线

文件落盘后立即建立 `processing` 记录，再异步执行：

1. MIME 与扩展名一致性校验。
2. SHA-256 哈希和重复检查。
3. 图片：宽高、比例、透明通道、缩略图。
4. 视频：宽高、比例、时长、fps、音轨和 poster。
5. 音频：时长、采样率和声道。
6. 后续增强项：代理视频、波形图和需要模型参与的数字人质量判断。
7. 成功标记 `ready`；可用但有问题为 `warning`；不可用为 `failed` 并保留结构化原因。

媒体分析失败不能让整个列表接口失败。卡片显示状态，详情提供重试分析。第一期不把代理视频、波形或 AI 人脸质量判断作为垂直闭环的阻塞条件。

### 11.5 使用关系、替换和渲染快照

- 生产 session 新增或替换资源时，在同一业务操作中删除该 slot 的旧 usage 并写入新 usage；取消选择必须删除关系。
- repository 对 `session + step + slot + purpose + resource` 建立唯一约束，避免重复计数。
- 增加 reconciliation 命令，从 session 状态重建 usage，用于迁移和异常恢复。
- 渲染开始前由服务端解析资源引用并生成 `ResourceSnapshot`，锁定媒体 revision/hash、数字人 scene、模板 revision 和 renderer version。
- 迁移窗口内 session 双写旧路径与新资源引用；读取优先新引用、缺失时回退旧路径。完成数据核对后才停止路径双写。
- 归档前返回引用数量；已引用资源可归档但默认不可彻底删除。只有回收站中的未引用 revision 才允许物理清理。

---

## 12. 迁移与兼容策略

迁移必须是可重复、可回滚、不会移动原文件的：

1. 启动时检查 `asset_schema_version`。
2. 迁移前备份旧 manifest，并记录文件大小、修改时间和校验值；备份不移动原媒体。
3. 读取所有旧 manifest，以 `resource_kind + legacy_id` 生成稳定映射；图片/视频/音频进入媒体表，品牌、模板和数字人进入各自领域表。
4. 对存在的媒体计算元数据和哈希；缺失文件记入迁移日志，不静默删除记录。
5. 写入 SQLite 事务，原文件和旧 manifest 保持不动。
6. 对相同哈希先标记潜在重复，不自动合并不同业务名称。
7. 新旧 API 做一段时间双读比对；写操作进入新 repository，兼容接口从新模型序列化旧格式。
8. session 在迁移窗口内双写旧路径和新资源引用；运行 reconciliation 后核对 usage 与任务状态。
9. 验证数量、文件可访问、缩略图、资源快照和关键生产任务后，再停止旧 manifest 与旧路径写入。
10. 至少一个版本后才移除兼容层；回滚时继续使用备份 manifest 和未移动的原文件。

迁移验收必须输出：每类发现数、迁移成功数、缺失文件数、重复候选数、版本数、usage 对账结果、失败原因和 legacy 映射文件。

---

## 13. 可访问性与桌面交互要求

当前弹窗普遍是普通 `section`，页签和选中卡片也缺少完整语义。重构时一次性解决：

- 分类使用 `role=tablist/tab/tabpanel` 或语义等价的 Ant Design 组件。
- 弹窗使用 `role=dialog`、`aria-modal`、标题关联、初始焦点、焦点锁定、Escape 关闭和关闭后焦点归还。
- 可选择卡片使用按钮语义，暴露 `aria-selected`/`aria-pressed`；选中态不能只依赖颜色。
- 上传进度和处理状态使用 `aria-live`，错误与具体文件关联。
- 所有图像有有意义的 alt；装饰图标隐藏于读屏。
- 支持键盘在卡片网格中移动、打开预览、收藏和确认选择。
- 播放器默认不自动播放有声媒体，并尊重 `prefers-reduced-motion`。
- 紫色与珊瑚红主题下都检查正文、徽标、边框、禁用态和焦点环对比度。

---

## 14. 实施阶段与 Luna 工作包

### 阶段 0：冻结契约与建立基线（1–2 人日）

目标：让后续重构可测、可回退。

Luna 任务：

- 建立 `LibraryItem/MediaAsset/AssetRevision/ResourceUsage/ResourceSnapshot` 以及品牌、模板、数字人领域模型 ADR。
- 明确上传 session、后台任务恢复、版本、集合和路径双写协议。
- 记录旧 manifest 数量、API contract fixture 和关键任务 fixture。
- 使用可稳定复现的桌面端或 E2E 工具，为当前列表、上传、预览、删除及生产选择建立基线；审计宿主的浏览器错误不直接归入产品任务。
- 增加 `asset_center_v2` feature flag，默认只在开发环境开启。

验收：没有改变现有用户行为；旧测试全通过；ADR 覆盖本报告的核心表、接口和回滚策略；能清晰比较 v1/v2。

**门禁 A**：阶段 0 的 ADR 和迁移 fixture 评审通过后，才进入数据库和上传实现。

### 阶段 1：图片/视频后端垂直骨架（4–5 人日）

目标：先用图片和视频证明新内核、迁移和上传链路，不一次迁移全部类型。

Luna 任务：

- 新建 SQLite repository、媒体版本/变体/任务表和迁移日志。
- 只先导入旧图片、视频 manifest，生成稳定 legacy 映射和迁移报告。
- 实现 upload session、流式临时文件、哈希、重复检测、取消和启动恢复。
- 实现图片元数据/缩略图、视频元数据/poster；代理视频暂不作为门禁。
- 实现 v2 图片/视频列表、详情、归档接口，并让旧图片/视频 service 转调 repository。

验收：图片和视频旧数据 100% 对账；上传大文件不整文件进入 Python 内存；异常重启后任务可恢复；旧接口和旧生产流仍能工作。

### 阶段 2：第一个端到端用户闭环（4–5 人日）

目标：尽早交付并验证“管理 → 选择 → 渲染”的真实闭环。

Luna 任务：

- 上线 v2 图片/视频资产中心的搜索、友好卡片、详情、编辑、归档和基础上传队列。
- 实现第一版共享 `AssetPickerDialog`。
- 把图片、视频选择器接入画面规划和封面；快捷上传后返回原 slot 并自动选中。
- session 双写旧路径和新资源引用，维护 usage；启动一次真实渲染并生成 snapshot。
- 紫色和珊瑚红主题完成同一闭环的视觉回归。

验收：用户能上传或找到图片/视频，在画面规划或封面使用，并成功渲染；旧任务仍可打开和重跑；替换/取消选择后 usage 正确变化。

**门禁 B**：阶段 2 的真实垂直闭环通过后，才批量扩展其他类型。未通过时不得同时开工数字人、品牌和模板。

### 阶段 3：扩展媒体管理与音色（3–4 人日）

目标：补齐通用资产管理能力并迁移音频/音色。

Luna 任务：

- 完成真实多文件拖放、并发限制、进度、取消、逐项重试和重复文件三种处理方式。
- 完成 `AssetRevision`、收藏、标签、集合及其 API。
- 导入音频/音色，接入共享选择器与试听。
- 按性能需要生成代理视频和波形；失败不阻塞原媒体可用状态。
- 完成服务端分页、facets、排序和 5000 条模拟数据基准。

验收：版本、集合和重复上传行为可解释；批量失败可逐项恢复；音色可在生产步骤中试听、快捷上传并使用。

### 阶段 4：数字人档案与场景（4–5 人日）

目标：达到参考图的核心效率，而不只是外观相似。

Luna 任务：

- 完成 Profile/Scene 数据模型、API 和旧数字人导入。
- 完成左侧人物筛选/卡片、右侧大预览、场景选择、确定性质量与兼容性提示。
- 将用户提供的竖屏 MP4 作为测试场景媒体，验证 revision、poster、播放、比例、时长和音轨信息。
- 在生产流中一次性回填 profile、scene、workflow 和 dimensions，并生成资源快照。
- AI 人脸/姿态质量判断作为增强项，不阻塞本阶段上线。

验收：单击任一数字人即可立即预览；切换场景不离开页面；不兼容原因在选择前可见；旧数字人任务仍可回放。

### 阶段 5：品牌、模板和剩余生产流（3–4 人日）

目标：完成领域资源接入并覆盖生产链路。

Luna 任务：

- 迁移品牌包为复合资源，引用 Logo、字体、BGM 等媒体资产。
- 迁移模板为版本化 `TemplateDefinition`，锁定 schema、template revision 和 renderer version。
- 将共享选择器接入后期、模板、品牌和发布准备入口。
- 品牌包贯通文案、后期、封面与发布准备默认值。
- 对模板字幕、字体、封面标题位置增加“预览配置 = 渲染配置”的回归快照。

验收：品牌与模板不依赖万能 metadata；旧任务锁定旧模板 revision；新任务从统一资产库选择后，预览与最终渲染位置/字体一致。

**门禁 C**：全量迁移数量、usage、模板渲染快照和关键旧任务通过后，才默认开启 v2。

### 阶段 6：回归、灰度和清理（2–3 人日）

目标：安全替换 v1。

Luna 任务：

- 完成关键流程 E2E、视觉回归、键盘/读屏、大数据量和重启恢复测试。
- 在 feature flag 下灰度，对比旧/新查询数量、usage 和渲染结果。
- 修复迁移差异后默认开启 v2；保留一个版本的回退开关和兼容接口。
- 最后才从 `StudioApp.tsx` 删除旧资产 UI、重复 picker 和路径优先逻辑。

验收：无资产丢失、无旧任务回归、无模板渲染回归、无主题回归；回退后仍可读取新库数据。

### 工期口径

- 阶段基础工作量合计：**21–28 人日**。
- 加入旧任务差异、桌面 WebView、媒体格式和迁移问题缓冲后：**24–32 人日**。
- MVP 建议覆盖阶段 0–3，基础工作量 12–16 人日，按风险缓冲后安排 **15–20 人日**。
- 工期按一名熟悉当前代码的全栈工程师估算；多人并行不能简单按人数等比例缩短，因为迁移、契约和垂直闭环存在顺序依赖。

---

## 15. 建议的提交顺序

每个提交都应可运行，不允许一个巨型“完整重构”提交：

1. `docs/assets-v2-contract-and-baseline`
2. `feat/media-repository-image-video-migration`
3. `feat/streaming-upload-and-media-jobs`
4. `feat/library-v2-image-video-api`
5. `feat/asset-center-image-video-slice`
6. `feat/storyboard-cover-asset-picker-slice`
7. `feat/media-revisions-collections-and-voice`
8. `feat/digital-human-profiles-and-scenes`
9. `feat/brand-template-domain-resources`
10. `feat/remaining-production-picker-integration`
11. `test/assets-v2-e2e-migration-and-visual-regression`
12. `refactor/remove-legacy-asset-ui-after-rollout`

每一步先补测试再迁移下一个入口。提交 2–6 必须形成图片/视频垂直闭环；门禁 B 通过前不要启动提交 8–10。不要同时修改资产内核、所有生产步骤和主题样式，否则回归无法定位。

---

## 16. 测试与验收清单

### 16.1 数据与 API

- 旧 manifest 导入幂等，重复运行不生成重复资产。
- 上传大视频时进程内存不会随完整文件大小线性增长；空间不足在写入前失败。
- 上传取消、进程异常退出和应用重启后，`.part` 文件与 `media_jobs` 状态可正确清理或恢复。
- 文件缺失、损坏、扩展名伪造、超限和元数据提取失败均有明确状态。
- 搜索、复合筛选、排序、游标分页在新增/归档时稳定。
- 同哈希重复上传的三种处理路径正确。
- “作为新版本”会创建 revision、保留历史版本并正确切换 current revision。
- 资源替换、取消选择和删除 slot 后，usage 会删除旧关系；reconciliation 与 session 状态一致。
- 渲染快照锁定媒体 revision/hash、数字人 scene、模板 revision 和 renderer version。
- 归档不破坏已有任务；彻底删除会检查引用并明确告警。
- v2 API 不向前端暴露绝对本地文件路径；旧接口仅在兼容窗口保留该字段。

### 16.2 组件和视觉

- 9:16、16:9、1:1、超宽图、超长图、透明 PNG、低分辨率图片显示正确。
- 横屏/竖屏视频 poster、时长、播放和静音状态正确。
- 数字人图片档案与视频场景均可即时预览。
- 0、1、20、500、5000 条数据的空状态、布局和滚动性能可接受。
- 紫色与珊瑚红主题、窗口缩放和 125%/150% 显示比例无错位。

### 16.3 关键 E2E

1. 批量上传 10 张产品图片 → 批量打标签 → 搜索 → 加入画面规划。
2. 上传竖屏数字人视频 → 自动生成 poster → 建立场景 → 在数字人步骤选择并预览。
3. 从封面步骤快捷上传图片 → 自动选中 → 返回后显示安全区。
4. 收藏一个音色 → 在新任务的“最近/收藏”中试听并选择。
5. 归档一个已使用视频 → 旧任务仍能渲染 → 新任务默认不可选。
6. 切换紫色/珊瑚红主题完成同一套管理和选择流程。
7. 上传中强制重启应用 → 重开后任务继续或明确失败 → 不出现无主临时文件。
8. 更新一个模板 → 旧任务继续使用旧 revision → 新任务使用新 revision → 两者预览与成片各自一致。

### 16.4 可用性验收指标

- 已知名称资产：用户在 10 秒内找到并预览。
- 已有资产加入单个生产 slot：不超过 3 次主要操作。
- 上传失败时用户能指出失败文件和原因，并可单项重试。
- 任何卡片都能在不暴露原始磁盘路径的情况下理解类型、状态、比例/时长和用途。
- 数字人首次选择前即可看到人物预览、场景和兼容性。

---

## 17. 风险与防护

| 风险 | 防护 |
|---|---|
| JSON → SQLite 迁移丢数据 | 原文件不移动；事务导入；数量/哈希报告；一版双读与回退 |
| 大视频上传占满内存或磁盘 | 流式 `.part` 文件、前置空间检查、单批次限制、取消清理 |
| 视频分析阻塞 UI | 先建 processing 记录；持久化本地任务生成 poster/proxy；列表可渐进更新 |
| 应用重启留下僵尸任务 | `media_jobs` 持久化；启动时重排 running；临时文件保留期清理 |
| 共享组件变成万能巨石 | 卡片骨架与类型 renderer 分离；上下文通过 picker request 注入 |
| 品牌/模板被过度资产化 | 只统一搜索投影；品牌、模板、数字人保留领域表和类型化接口 |
| 生产任务受重命名/归档影响 | session 保存资源 ID；渲染启动时锁定 revision/hash/renderer version |
| usage 与任务状态漂移 | 选择操作内同步增删；唯一约束；reconciliation 对账 |
| 数字人筛选字段为空 | 只显示有值 facets；允许逐步补元数据 |
| 自动标签不准确 | 自动标签标注来源并允许编辑；第一阶段不作为硬约束 |
| 主题回归 | 禁止硬编码主色；两套主题纳入视觉测试 |
| 大规模一次重构难回退 | feature flag、兼容接口、阶段性交付、最后删除旧 UI |

---

## 18. 本轮明确不做

- 不做跨企业云端多租户、团队权限和远程对象存储；先把本地桌面资产域做稳。
- 不做依赖向量数据库的 AI 语义搜索；结构化标签与规则推荐先上线。
- 不做数字人市场或第三方供应商商城。
- 不把发布改成无人值守自动点击；仍保持自动填充、人工确认最终发布。
- 不在迁移阶段覆盖或重编码原始媒体文件。

---

## 19. 给 Luna 的最终实施原则

1. 先统一数据和契约，再做漂亮页面。
2. 统一的是资源索引和交互，不是把品牌、模板、数字人强塞进万能媒体表。
3. 管理页和生产流必须共享同一查询、预览、上传和选择组件。
4. 数字人必须拆成“档案 + 场景”，不能继续把一个视频文件叫完整数字人。
5. 图片默认完整展示，裁切是 revision 变体，不覆盖原图。
6. 删除改为归档，所有资源都要能回答“在哪里被使用”。
7. 快捷上传必须流式传输，并回到原生产上下文自动选中。
8. 资源替换、移除、版本切换和渲染快照必须有完整生命周期。
9. 不兼容资产应展示原因，不应悄悄消失。
10. 紫色与珊瑚红主题都必须通过同一套视觉与可访问性测试。
11. 旧接口与旧任务至少保留一个版本的兼容窗口。
12. 先完成图片/视频垂直闭环，再扩展数字人、品牌和模板。
13. 每个里程碑独立可运行、可验收、可回退。

完成这套重构后，企业资产库才会从“文件存放页”升级为贯穿选题、文案、配音、数字人、画面规划、后期、封面和发布准备的生产基础设施。

---

## 20. 修订后开工评审

> 评审日期：2026-07-17
> 评审对象：本方案的架构可行性、数据安全、实施顺序、工作量和验收门禁
> 证据边界：本轮评审针对实施文档与已检查代码约束，不宣称完成新的逐屏 UI 或无障碍合规审计

### 20.1 评审步骤与健康度

| 步骤 | 评审内容 | 结果 | 结论 |
|---|---|---|---|
| 1 | 领域边界 | 通过 | 媒体资产、品牌、模板、数字人已分层；统一索引不再等于万能表 |
| 2 | 上传与后台任务 | 通过 | 已明确流式临时文件、进度、磁盘检查、持久化任务和重启恢复 |
| 3 | 版本、集合和重复处理 | 通过 | 已补充 revision、current revision、集合接口和新版本语义 |
| 4 | 使用关系和渲染稳定性 | 通过 | 已覆盖增删 usage、唯一键、reconciliation、双写和不可变快照 |
| 5 | 实施顺序 | 通过 | 阶段 1–2 先交付图片/视频“管理 → 选择 → 渲染”垂直闭环 |
| 6 | 迁移与回滚 | 通过 | 原文件不移动、manifest 备份、事务导入、双读/双写和回滚窗口明确 |
| 7 | 工作量 | 通过 | 完整范围修订为 24–32 人日；MVP 为 15–20 人日；依赖顺序明确 |
| 8 | UX 与主题验收 | 通过但需实施验证 | 页面规格、数字人双栏、紫色/珊瑚红和可访问性门槛明确，仍需真实截图/E2E 验证 |

### 20.2 开工结论

**评审结果：GO，可以安排 Luna 实施。**

授权边界不是让 Luna 一次性并行重写全部资产库，而是：

1. 立即安排 Luna 执行阶段 0 和阶段 1。
2. 阶段 0 的 ADR、迁移 fixture 和回滚方案必须先通过门禁 A。
3. 阶段 2 必须完成至少一个图片/视频真实渲染闭环，通过门禁 B 后才能扩展数字人、品牌和模板。
4. 阶段 5 的全量迁移、usage 对账和模板渲染快照通过门禁 C 后，才能默认开启 v2 和清理旧 UI。

因此，本方案已经达到可实施状态；没有需要产品负责人先回答的阻塞性问题。实施过程中的范围调整应优先延期代理视频、波形和 AI 质量判断，不得削弱迁移回滚、资源快照、使用关系或生产流垂直闭环。
