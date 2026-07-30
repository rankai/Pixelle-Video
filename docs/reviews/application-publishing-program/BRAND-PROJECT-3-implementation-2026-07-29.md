# BRAND-PROJECT-3 轻量项目 UI 实施证据

日期：2026-07-29
Stage：`BRAND-PROJECT-3`
Gate：`PG-BP-D_implementation_review_pending`

## 1. 实施结论

Stage3 已完成品牌包—项目轻量 UI、项目资料追加命令和四应用共享接线，当前停在独立复审入口：

- 品牌包继续只存在于企业资产库；项目仍是工作流对象；
- 新建项目支持 0/1/多品牌；单品牌只在前端自动选中，点击“创建项目”前项目列表实测仍为空；
- 有品牌和无品牌项目均显式创建 ContextSnapshot v3；旧 v1/v2/null 项目不自动绑定，提供明确“关联品牌包”动作；
- 品牌摘要只展示名称、Logo 占位、继承说明和品牌色，不展示 brand ID、revision、snapshot 或 fingerprint；
- 项目编辑器只展示推广对象、营销目标、受众、卖点、活动和本次素材说明；
- “本项目品牌设置”默认折叠；标量覆盖显示“仅本项目使用”，支持逐项和全部恢复；
- 品牌更新只显示“品牌资料有更新”；“查看变化”是只读 preview，只有显式确认“同步最新品牌资料”才追加快照；
- 文案、标题、图文复用 `CreationWorkspace` 中的共享组件；数字人口播复用同一组件；
- flag-off 保留原有 UI，Stage3 flag 默认关闭；
- 应用页不恢复项目保存/归档生命周期动作；未调用 LLM、TTS、RunningHub、第三方平台或最终发布。

## 2. 服务端边界

新增 `POST /api/content-projects/{project_id}/project-material`：

- 使用 `expected_context_snapshot_id` 做并发保护；
- 只追加项目业务资料和允许的标量项目覆盖；
- 保存时读取项目当前固定的品牌历史 revision，不解析最新品牌；
- 品牌包已经有新版本时，保存项目资料也不会隐式同步；
- Logo/BGM 不在轻量项目表单编辑，保留历史不可变引用和已有媒体覆盖；
- 同一 AppDB 事务中追加 v3 Snapshot、更新项目 pointer 和 `primary_goal`；
- stale snapshot、未知覆盖、历史品牌 revision 缺失均失败关闭且零写。

## 3. P1 修复

真实 900px reload 发现 v3 项目的品牌摘要仍在，但 `projectDetailsOpen` 被重置，业务编辑器入口过深。修复为：

- CreationWorkspace 初次加载和项目切换在 flag-on + schema v3 时默认打开轻量表单；
- DigitalHuman 加载 v3 snapshot 时执行同一规则；
- 品牌摘要在用户主动关闭后提供直接“编辑本次信息”动作；
- 1440/900 参数化 remount 测试均验证 reload 后“本次项目信息”和“目标受众”仍可编辑；
- Browser 900px hard reload 复验 `brand=true / editor=true / audience=true`。

## 4. 首轮独立审查修复

首轮独立审查结论为 `BLOCKED P0=0 / P1=4 / P2=1`。本轮在 Stage3
边界内完成修复，Gate 仍保持 `PG-BP-D_implementation_review_pending`：

- `current snapshot=null`、v1、v2 项目在营销文案、爆款标题、抖音图文、
  数字人口播四个应用中统一显示“这是旧项目”关联卡；不自动写入，显式关联时
  使用 `expected_context_snapshot_id=null`；
- 新增只读安全接口
  `GET /api/v2/media-assets/{asset_id}/revisions/{revision_id}/project-preview`，
  Logo 严格按快照中的 `asset_id + asset_revision` 读取；当前资产推进到新版本后
  历史项目仍请求固定 revision，缺失时显示安全占位；
- 品牌列表和品牌更新检查失败不再静默。归档、历史 revision 缺失和网络失败均
  显示业务错误，同时保留历史摘要、禁用同步并提供“重新关联品牌”；
- 新建和重新关联品牌选择器均可搜索；零品牌时明确提供“前往企业资产库”；
- 受控隔离环境补齐 Registry flags 后验证数字人口播 route，未修改产品 Registry
  边界，也未进入任何生成动作。

终验复核随后保留 `P1=1`：归档品牌 warning Alert 在 1440/1280 的中窄创作栏
中让约 236px 操作区挤压正文，`.ant-alert-section` 仅约 19px，中文逐字竖排。
Stage3 内追加最小布局修复：

- 只给归档/不可用品牌业务告警增加 `brand-project-status-alert` 专用样式；
- 正文独占完整可读行，保持 `writing-mode: horizontal-tb` 和
  `word-break: normal`；
- action 区置于正文下方并允许按钮换行，不修改全局 Ant Alert；
- 组件测试锁定专用 Alert/actions 结构；
- 真实 1440/1280 下正文宽度恢复为 291px、Alert 高度降为约 214px；
  900 下正文 685px，390 下正文 199px；四视口均无横向溢出。

## 5. 自动化验证

Desktop：

```text
npm test -- --run \
  src/features/app-workbench/BrandProjectContext.test.tsx \
  src/features/creation/CreationWorkspace.test.tsx \
  src/features/app-center/DigitalHumanApplicationView.test.tsx \
  src/features/app-center/AppShell.test.tsx \
  src/features/app-center/applicationRoutes.test.ts
```

结果：`5 files / 68 passed / 0 failed`。

```text
npm run build
```

结果：TypeScript 和 Vite production build 通过，4610 modules transformed。仅保留既有 chunk-size warning。

后端和契约聚合：

```text
uv run pytest -q \
  tests/brand_project_stage2_test.py \
  tests/brand_project_stage1_test.py \
  tests/app_workbench_project_context_test.py \
  tests/brand_project_boundary_entry_contract_test.py \
  tests/app_center_api_test.py \
  tests/app_center_registry_test.py \
  tests/asset_library_v2_repository_test.py \
  tests/config_llm_profiles_test.py \
  tests/coord0_contract_test.py
```

结果：`128 passed / 0 failed / 12 existing Pydantic deprecation warnings`。

Ruff check、Ruff format check 和 `git diff --check` 均通过。

## 6. 真实页面验证

隔离环境：

- API：`http://127.0.0.1:8100`
- Vite：`http://127.0.0.1:1420/#/apps/marketing-copy`
- 数据根：`/tmp/pixelle-brand-project-stage3.1EQ6Ga`
- 后端：`PIXELLE_ASSET_CENTER_V2=true`、`PIXELLE_BRAND_PROJECT_BOUNDARY_V1=true`
- 前端：四应用 workbench flags 和 `VITE_BRAND_PROJECT_BOUNDARY_V1=true`

Browser plugin 实测：

1. 新建弹窗唯一品牌“街角咖啡”自动选中；
2. 未点击创建前 `GET /api/content-projects` 返回 `[]`；
3. 创建后出现品牌摘要和六类本次业务字段；
4. 地址覆盖显示“仅本项目使用”，逐项恢复入口可见；
5. 1440/1280/900/390 响应式页面均可用；390px 下实测 `scrollWidth=375 <= innerWidth=390`，无横向溢出；
6. 900px reload 后同一 v3 项目仍显示编辑器；
7. 品牌修改后显示变化 badge，preview modal 列出“将同步更新/保留本项目设置”；
8. preview 不改变 current snapshot；显式确认后 badge 消失且编辑器仍在；
9. 页面无业务运行错误。控制台仅有既有 AntD `List` deprecated warning，登记为非阻塞 P2；Stage3 新增 Alert 已改用 `title`，未再新增 Alert deprecated warning。

首轮独立审查修复复验使用第二套隔离环境：

- API：`http://127.0.0.1:8101`
- Vite：`http://127.0.0.1:1421`
- 数据根：`/tmp/pixelle-brand-project-stage3-review.6XrXYw`
- 后端除 Stage3 flags 外，仅为 route 验证打开既有
  `PIXELLE_APP_CENTER_CONTENT_APPS`、`PIXELLE_APP_CENTER_DOUYIN_CAROUSEL`
  和 `PIXELLE_APP_CENTER_DIGITAL_HUMAN`

复验结果：

1. 0 品牌显示禁用选择器、“前往企业资产库”和禁用创建；1 品牌继续零预写；
   多品牌搜索“山野”只显示“山野茶铺”；
2. null、v1、v2 历史项目均显示明确关联卡，四应用 route 全部通过；
3. Logo 固定 v1 后把资产 current 推进到 v2，页面仍请求带固定
   `revision_id=revision-d18c7e415de44c33842d4f21a96bcdcf` 的 v1 thumbnail；
4. 归档品牌后历史摘要“街角咖啡”继续可读，页面显示“这个品牌当前不可用于新项目”，
   “同步最新品牌资料”禁用，“重新关联品牌”可用；
5. 1440、1280、900、390 均无横向溢出；390px 下
   `scrollWidth=375 <= innerWidth=390`；
6. Tab 从项目选择器依次进入“我的项目”和“重新关联品牌”，焦点环为
   `3px solid rgb(226, 219, 255)`；Enter 可打开更换品牌 dialog；
7. 本次干净复验页面控制台 `warning/error=[]`。

终验 P1 布局复验：

1. 1440/1280/900/390 下 `actionBelowSection=true`，正文不再被按钮区挤压；
2. 四视口均为 `writing-mode=horizontal-tb`、`word-break=normal`；
3. 390px 下 action 按钮自动分行，`scrollWidth=375 <= innerWidth=390`；
4. “重新关联品牌”真实点击仍能打开更换品牌 dialog；
5. 无 framework overlay；控制台只有既有 AntD `List` deprecated warning。

视觉文件和 SHA-256 见
[`qa/BRAND-PROJECT-3-implementation-2026-07-29.json`](qa/BRAND-PROJECT-3-implementation-2026-07-29.json)。

## 7. Gate 边界

- 状态：`PG-BP-D_implementation_review_pending`
- 不声称 Stage4 四应用生成消费已完成；v3 实际进入 LLM/渲染/交付仍属于 BRAND-PROJECT-4；
- 默认 flag 仍关闭；
- 隔离本地 API 只创建 Stage3 验收项目和品牌同步快照；
- LLM/TTS/RunningHub/第三方平台调用均为 0；
- 上传、扫码、授权和最终发布点击均为 0；
- 无 Git commit；
- `PROGRAM-ROLLOUT/PG-L paused_external` 不变。
- 首轮审查问题已实施并自验，仍需同一独立审查线程复验后才能改变 Gate；
  不得据此进入 BRAND-PROJECT-4。
