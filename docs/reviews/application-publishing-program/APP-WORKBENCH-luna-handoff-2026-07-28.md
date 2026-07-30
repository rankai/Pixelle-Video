# APP-WORKBENCH 应用工作台优化 Luna 交接

- 日期：2026-07-28
- Change Request：`CR-APP-WORKBENCH-001`
- 分支：`codex/publish-v2-sidecar-gate`
- 当前提交锚点：`8de798d26045`
- 当前唯一入口：`APP-WORKBENCH-4`
- 当前 Gate：`PG-AW-E_implementation_in_progress`
- 上位外部等待：`PROGRAM-ROLLOUT/PG-L=paused_external`
- 交接原则：保留现有工作区，不 reset、不回退、不跳 Stage

## 0. 30 秒接手摘要

本轮不是从头实施。当前代码和方案方向一致，`APP-WORKBENCH-0` 至
`APP-WORKBENCH-3` 已通过对应 Gate，禁止返工或撤销；唯一工作入口是
`APP-WORKBENCH-4 / PG-AW-E_implementation_in_progress`。

Luna 接手后的第一目标只有一个：在更新后的后端进程上完成一次受控的抖音
图文真实生成，并补齐 package、单页局部重渲染、发布中心 handoff、三视口
视觉和六维复审证据。`PG-AW-E` 通过前不得进入数字人 Stage 5。

当前实现状态：

- 方案、数据合同、共享左右工作台、项目上下文、文案和标题工作台已经完成；
- 抖音图文主体代码及定向自动化已经完成，但真实闭环证据尚未完成；
- 数字人领域优化、统一结果传递和全量终审尚未开始；
- 当前工作区故意保持未提交状态，所有改动都属于本轮连续实施，不得清理；
- 最终发布仍由用户人工点击，本轮不得打开平台、不得上传、不得代替用户发布。

交接完成定义：

1. Luna 能从本文件和总台账直接定位唯一入口；
2. 不重复执行已经通过的 Stage 0-3；
3. 不连续重试真实生成，失败后先检查 Run、日志和数据库；
4. 每个后续 Stage 均完成 Entry、实现、定向测试、构建、证据、独立六维复审和 Gate 更新；
5. Stage 7 完成后返回 `PROGRAM-ROLLOUT / PG-L`，不得越权关闭外部验收项。

## 1. 方案与审查事实

正式实施方案：

- `docs/superpowers/specs/2026-07-28-application-workbench-experience-optimization-implementation-plan.md`
- 共 1118 行；
- 已覆盖功能、UI 布局、结果展示、结果传递、数据契约、迁移、回滚、测试和 Stage/Gate；
- 方案六维自审：
  `docs/reviews/application-publishing-program/APP-WORKBENCH-0-plan-self-review-2026-07-28.md`；
- 自审结论：`passed_for_entry_with_boundary`；
- P0：0；
- P1：0；
- 已修复 P2：3。

Luna 必须继续以总协调台账的 `current_stage/current_substage` 为唯一入口。领域方案只用于读取当前 Stage 的详细交付要求。

## 2. 当前开发进度

不使用主观百分比，以 Gate 为准：

| Stage | Gate | 状态 | 已完成内容 | 证据 |
| --- | --- | --- | --- | --- |
| APP-WORKBENCH-0 | PG-AW-A | `passed_with_boundary` | CR、契约、fixture、四应用基线、feature flag、迁移/回滚约束 | `APP-WORKBENCH-0-entry-2026-07-28.md`、Entry review、QA JSON |
| APP-WORKBENCH-1 | PG-AW-B | `passed_with_boundary` | 统一左右工作台、真实结果状态、窄屏配置/结果 Tab、键盘/focus、旧 UI 回滚 | `APP-WORKBENCH-1-implementation-2026-07-28.md`、review、QA |
| APP-WORKBENCH-2 | PG-AW-C | `passed_with_boundary` | ContextSnapshot v2、项目资料、v1 显式升级、草稿/切换/重启恢复、事实与 revision 校验 | `APP-WORKBENCH-2-implementation-2026-07-28.md`、review、QA |
| APP-WORKBENCH-3 | PG-AW-D | `passed_with_boundary` | 受信风格、文案/标题 input v2、结构化结果、编辑/选择/反馈、文案到标题 typed handoff、真实 Doubao smoke | `APP-WORKBENCH-3-implementation-2026-07-28.md`、review、QA |
| APP-WORKBENCH-4 | PG-AW-E | `implementation_in_progress` | Entry 已通过；图文 v2 输入、固定来源/素材 revision、风格/页数/模板、计划/页面/包结果、单页重渲染接线、下载和发布中心 handoff 已写入代码并通过定向自动化 | `APP-WORKBENCH-4-entry-2026-07-28.md`；本交接 |
| APP-WORKBENCH-5 | PG-AW-F | `not_started` | 数字人领域工作台优化尚未开始；此前只完成共享壳层/项目上下文接入，不得当成 Stage 5 完成 | - |
| APP-WORKBENCH-6 | PG-AW-G | `not_started` | 统一 ArtifactActions、VersionSwitcher 和完整跨应用交付尚未开始 | - |
| APP-WORKBENCH-7 | PG-AW-H | `not_started` | 全量灰度、四应用真实可视化终审、重启/回滚和收口尚未开始 | - |

结论：已通过 4 个 APP-WORKBENCH Gate（A-D）；E 正在实现；F-H 尚未进入。

## 3. 方案符合性复核

### 3.1 符合项

1. 架构未偏离：
   - FastAPI/Python 继续负责应用中心、LLM 与媒体执行；
   - SQLite 继续保存本地业务数据；
   - 没有引入第二套 Node/NestJS 业务后端；
   - 没有引入第二套模型配置。
2. 数据所有权符合：
   - `ContentProject` 是共享业务上下文；
   - `ContextSnapshot v2` 固定每次运行事实；
   - `ArtifactVersion` 追加版本，不覆盖历史；
   - `ArtifactHandoff` 固定来源版本。
3. UI 符合：
   - 复用现有主题和 tokens；
   - 桌面左输入、右结果；
   - 窄屏使用配置/结果 Tab；
   - 结果默认面向用户，不以 Run ID、Artifact ID 或裸 JSON 为中心。
4. 模型符合：
   - 文案、标题、图文继续复用当前模型管理与 `ConfigAppLLMPort`；
   - 风格只改变表达，不允许引入项目外事实。
5. 发布安全符合：
   - 图文 handoff 只进入发布中心；
   - 未打开抖音或其他平台；
   - 未上传；
   - 最终发布自动点击为 0。
6. 回滚符合：
   - 新工作台使用独立 feature flag；
   - 默认 flag 仍关闭；
   - 旧 UI、旧项目、旧 Run 和旧 Artifact 保留。

### 3.2 当前未完成项

`APP-WORKBENCH-4` 还缺以下 Gate 证据，因此不能关闭 `PG-AW-E`：

1. 更新后的后端进程启动后，完成一次有目的的真实图文生成；
2. 回读 `carousel_plan`、3 个 `carousel_page`、`carousel_package`；
3. 核对 PNG、ZIP、页序、标题、发布描述、话题和文件 hash；
4. 编辑一页文字或替换一张图片，只重渲染该页；
5. 确认旧 package 失效、新 package/version 追加，其他页版本不变；
6. 将固定 package handoff 到发布中心，验证重复点击幂等；
7. 确认整个过程没有打开发布平台；
8. 1440×900、900×760、390×844 做真实视觉对照；
9. 写 `APP-WORKBENCH-4-implementation`、六维 review 和 QA JSON；
10. P0/P1=0 后才更新 `PG-AW-E=passed_with_boundary` 并进入 Stage 5。

## 4. 刚才真实运行的准确结论

第一次点击“生成抖音图文”返回：

```text
FOREIGN KEY constraint failed
```

根因不是输入、LLM 或 renderer，而是浏览器连接的后端仍是修改前启动的旧进程；该进程的 `app_registry` 尚未登记 `builtin.douyin-carousel/1.1.0`，前端已按新合同创建 `1.1.0` Run，因此在创建 Run 时被外键拒绝。

处理后事实：

```text
app_registry:
builtin.douyin-carousel  1.0.0  pilot
builtin.douyin-carousel  1.1.0  pilot
```

数据库：

- 文件：`data/app_center.sqlite`
- `PRAGMA foreign_key_check`：空；
- 失败点击没有创建新的图文 AppRun；
- 最近图文 AppRun 仍是旧的 `1.0.0/needs_review`；
- 未调用 LLM；
- 未创建图文文件；
- 未打开发布平台。

主线程没有进行第二次真实生成。Luna 接手后必须先执行第 5 节的启动前检查，再只做一次目的明确的真实重试。

## 5. Luna 恢复步骤

### 5.1 启动前只读检查

```bash
sqlite3 -header -column data/app_center.sqlite \
  "SELECT app_id,version,json_extract(manifest_json,'$.name') AS name,status
   FROM app_registry
   WHERE app_id='builtin.douyin-carousel'
   ORDER BY version;"

sqlite3 data/app_center.sqlite "PRAGMA foreign_key_check;"
```

预期：

- 同时存在 `1.0.0` 和 `1.1.0`；
- foreign key check 无输出。

### 5.2 启动更新后的后端

```bash
PIXELLE_APP_CENTER_CONTENT_APPS=true \
PIXELLE_APP_CENTER_DOUYIN_CAROUSEL=true \
PIXELLE_APP_CENTER_DIGITAL_HUMAN=true \
PIXELLE_APP_CENTER_DIGITAL_HUMAN_DUAL_MODE=true \
PIXELLE_PUBLISH_V2_ENABLED=true \
uv run python api/app.py
```

### 5.3 启动本地桌面 Web 预览

```bash
cd desktop
VITE_API_BASE_URL=http://127.0.0.1:8000 \
VITE_APP_CENTER_SHELL=true \
VITE_CONTENT_PROJECTS=true \
VITE_CONTENT_APPS=true \
VITE_DOUYIN_CAROUSEL=true \
VITE_APP_CENTER_DIGITAL_HUMAN=true \
VITE_APP_CENTER_DIGITAL_HUMAN_DUAL_MODE=true \
VITE_APP_WORKBENCH_V2=true \
VITE_APP_WORKBENCH_TEXT_V2=true \
VITE_APP_WORKBENCH_CAROUSEL_V2=true \
VITE_APP_CENTER_NEW_NAV=true \
VITE_PUBLISH_CENTER_V2=true \
VITE_ASSET_CENTER_V2=true \
npm run dev -- --host 127.0.0.1 --port 1421
```

端口 1421 必须显式设置 `VITE_API_BASE_URL`；否则浏览器会把 `/api` 请求发到 Vite，返回 HTML 并出现 `Unexpected token '<'`。

### 5.4 单次真实验证输入

- 项目：`APP-WORKBENCH-3 门店咖啡实测`
- 项目 ID：`project_b57435d1b41548eda1b3a64d5c69bf77`
- 来源：已选择的主标题版本
- 封面钩子：`工作日下午茶，咖啡加面包怎么选？`
- 页数：3
- 模板：`template:clean-01`
- 资产：`测试`图片，UI 已确认显示“已固定版本”
- 风格：`门店种草`
- CTA：`收藏这份下午茶清单，到店前再看一遍`
- 发布描述：`工作日下午茶想喝现磨咖啡，也想搭配当日烘焙面包，可以看看这份三页选择清单。`
- 话题：`咖啡，下午茶，门店探店`

真实重试前先确认：

1. 页面没有 `FOREIGN KEY` 错误；
2. 后端进程是更新后启动的进程；
3. `app_registry` 已有 `1.1.0`；
4. 资产 revision 可解析；
5. 当前模型配置检查通过。

只执行一次。失败时先回读 AppRun、后端日志和数据库，不连续点击。

## 6. 当前自动化基线

交接前重新执行：

### Backend

```text
53 passed, 12 existing Pydantic deprecation warnings
```

覆盖：

- Entry contract；
- ContextSnapshot v2；
- 文案/标题 v2；
- 图文 v2；
- carousel renderer/PG-H；
- registry；
- app-center API。

### Desktop

```text
6 test files passed
55 tests passed
```

覆盖：

- 共享 AppWorkbench；
- CreationWorkspace；
- 图文 v2 固定输入；
- 真实页面预览；
- 单页重渲染 API；
- 固定 package 到发布中心；
- DigitalHumanApplicationView 既有回归；
- application routes。

### 静态与构建

```text
Ruff: passed
git diff --check: passed
TypeScript: passed
Vite production build: passed
```

已知非阻塞项：

- 12 条既有 Pydantic V2 deprecation warnings；
- Vite vendor chunk 大小 warning；
- Vitest/JSDOM 的 `navigation to another Document` 提示；
- Ant Design `List/Alert/addonAfter` deprecation 只在开发控制台显示。

这些不得被错误登记为本 Stage P0/P1。

## 7. 当前工作区边界

工作区不是 clean，并且包含本方案多个 Stage 的连续实现：

- 修改文件：23 个；
- tracked diff：约 `+3194/-157`；
- 新增：共享 AppWorkbench、项目上下文、风格/输入合同、Stage 证据、图文 v2 测试等；
- 尚未为本轮 APP-WORKBENCH 创建最终分批提交。

Luna 必须：

1. 保留所有现有改动；
2. 不执行 `git reset --hard`、`git checkout --` 或大范围回退；
3. 不把 Stage 4 partial 当成完成；
4. 不提前进入 Stage 5；
5. 先关闭 `PG-AW-E`，再按方案继续 Stage 5、6、7；
6. 分批提交必须按 Stage/意图拆分，并确保台账、实现、测试和证据同批一致。

## 8. Luna 的下一条执行指令

```text
以《应用中心与桌面自动发布整体协调实施方案》的实时台账为唯一入口，
从 APP-WORKBENCH-4 / PG-AW-E_implementation_in_progress 接手。
保留现有工作区，不撤销 APP-WORKBENCH-0 至 4 的改动。
先执行数据库 registry/FK 只读检查，启动更新后的后端和带
VITE_API_BASE_URL 的桌面预览；按交接中冻结的输入只执行一次
有目的的真实抖音图文生成。完成 plan/page/package、PNG/ZIP/页序/
发布文案、单页局部重渲染、package handoff、重启恢复、三视口视觉、
自动化、构建、六维复审和 PG-AW-E 更新后，才能进入 APP-WORKBENCH-5。
不得打开发布平台，不得点击最终发布，不得跳 Stage。
```

## 9. 关键代码导航

| 领域 | 主要文件 | 接手时关注点 |
| --- | --- | --- |
| 共享工作台 | `desktop/src/features/app-workbench/AppWorkbenchShell.tsx` | 左输入/右结果、窄屏 Tab、加载/错误/空状态 |
| 应用详情编排 | `desktop/src/features/creation/CreationWorkspace.tsx` | 文案、标题、图文输入和结果展示、handoff |
| 数字人接入 | `desktop/src/features/app-center/DigitalHumanApplicationView.tsx` | 当前只接入共享壳层；Stage 5 领域优化未完成 |
| 路由与入口 | `desktop/src/features/app-center/applicationRoutes.ts` | 应用入口映射和回退 |
| Feature flags | `desktop/src/flagResolver.ts` | 新工作台开关默认关闭，旧 UI 必须可回退 |
| 前端 API | `desktop/src/api.ts` | snapshot、ArtifactVersion、handoff、图文局部重渲染 |
| 应用中心 API | `api/routers/app_center.py`、`api/schemas/app_center.py` | Run、Artifact、handoff、图文页面重渲染 |
| 项目上下文 | `pixelle_video/app_center/project_context.py` | ContextSnapshot v2 和事实/revision 固定 |
| 文案与标题 | `pixelle_video/app_center/structured_apps.py` | input v2、结构化输出、受信风格 |
| 图文生成 | `pixelle_video/app_center/carousel.py` | plan/page/package、文件生成与局部重渲染 |
| 持久化 | `pixelle_video/app_center/repository.py`、`migration.py` | 追加版本、固定 handoff、迁移和 FK |
| 应用登记 | `pixelle_video/app_center/registry.py` | `builtin.douyin-carousel/1.1.0` 必须存在 |
| 核心测试 | `tests/app_workbench_*_test.py` | 后端 Stage 0-4 合同与行为 |
| 桌面测试 | `desktop/src/features/creation/CreationWorkspace.test.tsx` | 真实页面预览、局部重渲染、固定 package handoff |

## 10. 仍然保留的 Program 外部边界

完成 APP-WORKBENCH-7 后，台账必须回到：

```text
PROGRAM-ROLLOUT / PG-L
```

以下仍不能被本方案关闭：

- 真实 Windows 用户设备验收；
- 产品负责人签字；
- 真实平台 rollback；
- 原生 WebView SLA。
