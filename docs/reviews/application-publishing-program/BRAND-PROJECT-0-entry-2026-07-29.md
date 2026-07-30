# BRAND-PROJECT-0 Entry：品牌包—我的项目边界冻结

- Stage：`BRAND-PROJECT-0`
- Gate：`PG-BP-A`
- Change Request：`CR-BRAND-PROJECT-BOUNDARY-001`
- 状态：`entry_remediated_pending_independent_re_review`
- Gate 建议：`passed_with_boundary`
- 日期：2026-07-29

## 1. 本阶段范围

本阶段只完成领域、数据契约、fixture、默认关闭 flag、兼容投影和“读不写”基线，没有修改业务 UI、业务写逻辑、生产数据库或真实执行器。

`PROGRAM-ROLLOUT/PG-L` 继续作为 `paused_external` checkpoint；Windows 实机、产品签字、真实 rollback/WebView SLA 的状态和证据未被修改。

## 2. 已冻结契约

### 2.1 领域所有权

- 品牌包继续属于企业资产库，是品牌长期资料唯一来源。
- `ContentProject / 我的项目` 是工作流容器，不是资产库 resource kind。
- 品牌与项目关系固定为 `BrandKit 1:N ContentProject`；项目最多关联一个品牌，也允许暂不关联。
- ContextSnapshot 是不可变生成事实，不等同品牌包或项目。

### 2.2 ContextSnapshot v3

新增 [`context-snapshot-v3.schema.json`](../../contracts/app-center/context-snapshot-v3.schema.json)，冻结：

- `brand_context` 可为空，兼容无品牌项目；
- 有品牌时必须固定 `brand_id + domain_revision`；
- Logo 和默认 BGM 必须固定 media revision；
- `values` 保存本次解析后的品牌值；
- `overridden_fields` 只允许品牌字段，且唯一；
- `project_brief` 只保存推广对象、营销目标、受众、卖点、活动事实和项目素材；
- 顶层和各对象拒绝未知字段。
- `offer.required` 中 `price_facts` 只出现一次，并由机器测试锁定 required 数组不得重复。

新增 [`context-snapshot-v3-write-request.schema.json`](../../contracts/app-center/context-snapshot-v3-write-request.schema.json) 冻结客户端信任边界：

- 客户端只能提交 `brand_binding + project_overrides + project_brief`；
- 客户端不得直接提交存储态 `brand_context`；
- `brand_binding=null` 时 `project_overrides` 必须为空；无品牌项目的业务字段继续写入 `project_brief`；
- 存储态 `brand_context` 只能由服务端 resolver 生成；
- 非覆盖字段必须逐字段等于固定 brand domain revision；
- 只有 `overridden_fields` 中明确列出的字段可以使用“仅本项目使用”值；
- 伪造 `brand_context` 返回 `PROJECT_BRAND_CONTEXT_UNTRUSTED`；
- resolver 的实际实现归 `BRAND-PROJECT-1`，Entry 没有接入业务写链路。

本阶段不支持在项目覆盖中用 `null` 清除 Logo 或默认 BGM：

- 删除对应项目覆盖字段即可恢复固定品牌版本中的默认值；
- 若品牌本身不应使用 Logo/BGM，应在“企业资产库”修改品牌包；
- 未来如确需项目级清除，必须通过独立 Change Request 增加显式 clear action，不能复用含义不清的 `null`。

### 2.3 v2 projection

Entry contract 和 fixture 冻结 v3 到 v2 的纯读投影：

- 品牌展示名、地址和电话投影到 v2 `store_or_brand`；
- 项目 offer/audience/facts 保持；
- 项目素材与非空品牌 Logo/BGM revision 去重合并；
- `brand_revision_ref` 投影为内部 `brand:<id>@<revision>`；
- 投影不得修改源快照或创建新快照。

v3 写入前必须先实现 v1/v2/v3 双读和 flag-off v3 兼容；本 Entry 未开始 v3 业务写入。

### 2.4 单品牌和读不写

- 只有一个可用品牌时，只允许客户端在“新建项目”表单中自动选中。
- 用户点击创建后，显式 POST 才能携带 `brand_id`。
- 列表、详情、页面打开、刷新和重启不得自动绑定品牌或创建 ContextSnapshot。
- `brand_id=null` 旧项目不会因为当前只有一个品牌而在读取时被修改。

### 2.5 错误码

冻结：

- `PROJECT_BRAND_NOT_FOUND`
- `PROJECT_BRAND_NOT_BOUND`
- `PROJECT_BRAND_NOT_AVAILABLE`
- `PROJECT_BRAND_REVISION_NOT_FOUND`
- `PROJECT_CONTEXT_CONFLICT`
- `PROJECT_BRAND_ASSET_REVISION_MISSING`
- `PROJECT_BRAND_CONTEXT_UNTRUSTED`
- `BRAND_PROJECT_BOUNDARY_DISABLED`

错误契约只包含普通用户可理解的中文文案，不包含数据库路径、SQL、provider、内部调用栈或凭证。

Stage2 独立审查收紧了两个原 Entry 已覆盖但未分离命名的状态：未关联品牌使用
`PROJECT_BRAND_NOT_BOUND / HTTP 409 / 这个项目尚未关联品牌，请先选择品牌包`；
flag 关闭使用
`BRAND_PROJECT_BOUNDARY_DISABLED / HTTP 404 / 品牌项目功能当前未启用`。
二者不得复用“品牌不存在”文案。

`PROJECT_BRAND_SYNC_NO_CHANGE` 是成功返回，已从 `error_codes` 移入 `result_codes`，固定为 HTTP 200、`changes_committed=false`。

### 2.6 Feature flag

在现有矩阵登记：

```text
name: brandProjectBoundaryV1
env: PIXELLE_BRAND_PROJECT_BOUNDARY_V1
default: false
owner_stage: BRAND-PROJECT-3
```

本阶段只登记契约，没有接入前端或后端运行时。v3 读取兼容未来不得受该 flag 关闭影响。

### 2.7 完整 rollback 契约

机器 contract 和 fixture 已冻结：

- flag 关闭后继续使用旧交互，v1/v2/v3 永久可读；
- flag 关闭禁止新 v3 写入和品牌同步；
- 同步失败不得移动 `brand_id`、`current_context_snapshot_id`，不得追加或修改历史快照；
- rollback 不删除项目、品牌或 ContextSnapshot，归档不等于删除；
- 桌面重开恢复最后一次完整提交状态，不恢复半完成同步；
- flag 再开启从最后一次完整提交继续，读取不重绑、不重建快照，重试必须由用户显式触发。

Entry 只冻结上述状态机；真实重启/flag 切换/失败注入归 `BRAND-PROJECT-3/PG-BP-D`。

## 3. Fixture

[`brand-project-boundary-entry-fixtures.json`](../../contracts/app-center/fixtures/brand-project-boundary-entry-fixtures.json) 包含：

- 完整继承品牌；
- 四个字段“仅本项目使用”覆盖；
- `brand_context=null` 无品牌旧项目兼容；
- 固定的 v2 projection；
- 缺失 domain revision；
- 缺失 Logo media revision；
- 重复覆盖字段；
- 未知技术字段；
- zero/one/multiple ready brand 与 legacy `brand_id=null` 的创建/读取矩阵；
- 客户端伪造 `brand_context` 负例和服务端解析预期；
- 无品牌 + 空覆盖正例、无品牌 + 非空覆盖负例；
- Logo/BGM `null` clear 负例；
- flag-off、失败原子性、重开恢复、再次开启的 rollback 状态；
- 单品牌读取不得自动绑定的数据库断言；
- `PROJECT_BRAND_SYNC_NO_CHANGE` 成功 outcome。

fixture 不含真实品牌、凭证、用户绝对路径或生产数据。

## 4. 真实临时 SQLite 读不写基线

Entry 测试分别创建隔离临时 App Center 和 Asset Library 数据库，在完成测试准备写入后保存表级快照，再连续执行三轮读取：

### App Center

- `list_projects`
- `get_project`
- `get_context_snapshot`

前后断言：

- `content_projects` 所有行和值完全一致；
- `brand_id=null` 保持；
- `updated_at/current_context_snapshot_id` 不变；
- `context_snapshots` 行数和值完全一致。

### Asset Library

- `list_domain_items("brand")`
- `get_domain_item("brand")`
- `domain_snapshot_metadata("brand")`
- `list_domain_revisions("brand")`

前后断言：

- `brand_kits_v2` 所有行和值完全一致；
- `domain_revisions` 行数和值完全一致；
- 三轮读取不会追加 brand revision。

所有数据库位于 pytest 临时目录；生产数据库写入为 0。

### API / 桌面读链路收口

新增 FastAPI `TestClient` 集成基线，同时挂载真实 App Center 和 Asset Library V2 router。初始化临时数据后，对两个 SQLite 的全部业务表保存前态，连续三轮调用：

- `GET /api/content-projects`
- `GET /api/content-projects/{project_id}`
- `GET /api/content-projects/{project_id}/context-snapshots`
- `GET /api/v2/library/items?kind=brand`
- `GET /api/v2/library/items/{brand_id}`

调用后逐表逐行比较，两个数据库均与前态完全相等。桌面当前所有权入口 `listContentProjects`、`getCurrentContextSnapshot`、`listLibraryItemsV2` 已静态锁定为 GET/no-method override。

本 Entry 不宣称已完成真实桌面进程到数据库的 before/after。该真实链路、重开和 flag 切换统一是 `BRAND-PROJECT-3/PG-BP-D` 阻断条件，避免把 API 证据扩大解释成桌面实机证据。

## 5. 视觉现状与归因基线

未修改 UI 的前提下，已归档：

- 当前本地 `http://127.0.0.1:1420/#/apps/marketing-copy` 全页截图和 DOM snapshot；
- 用户当前页面中“已有文案版本 / 文案产物 / 固定内容版本”技术控件截图；
- 应用内部重复“保存项目 / 归档项目 / 项目操作”截图；
- 可验证 SHA-256 和采集说明 manifest。

证据目录：[`qa/BRAND-PROJECT-0-visual-baseline-2026-07-29`](qa/BRAND-PROJECT-0-visual-baseline-2026-07-29)。

为证明 Stage 归因边界，另记录 Entry 起始 commit `8de798d260459bb0e62d44b0bb7ab670f4b8b92f`，以及 11 个禁止修改的业务 UI/业务写文件的起始工作区 SHA-256。机器测试逐文件复核 hash；本 Stage 未改变这些文件。见 [`BRAND-PROJECT-0-entry-attribution-baseline-2026-07-29.json`](qa/BRAND-PROJECT-0-entry-attribution-baseline-2026-07-29.json)。

## 6. 验证结果

| 检查 | 结果 |
| --- | --- |
| BRAND-PROJECT Entry 定向测试 | `14 passed` |
| Entry + APP-WORKBENCH Entry + 协调回归 | `42 passed` |
| API 双库全表 before/after | `passed` |
| Desktop GET ownership 静态边界 | `passed`；真实桌面 before/after 归 PG-BP-D |
| 既有 Pydantic 弃用警告 | `12`，与本阶段无关 |
| JSON Schema 自校验与 fixture 正/负例 | `passed` |
| Entry JSON 文件 `jq -e` | `passed` |
| Ruff check | `passed` |
| 新 Entry 测试 Ruff format check | `passed` |
| 受控文件 `git diff --check` | `passed` |
| LLM/RunningHub/平台/最终发布动作 | `0` |
| 浏览器业务动作 | `0`；仅本地只读截图 |

QA 明细和 SHA-256 见 [`qa/BRAND-PROJECT-0-entry-2026-07-29.json`](qa/BRAND-PROJECT-0-entry-2026-07-29.json)。

## 7. 独立审查修复与 Gate 建议

首轮独立审查结论为 `P0=0 / P1=5 / P2=2`。本轮已在 Entry 范围内完成审查要求：

- 补完整 rollback machine contract/fixture；
- 补视觉现状和可验证 hash/manifest；
- 补 zero/one/multiple/null 品牌矩阵；
- 补 API 双数据库全表零写集成，并明确桌面真实证据 PG-BP-D 边界；
- 补 server-only resolver 信任边界和客户端伪造负例；
- 补 Entry commit/禁止文件 hash 归因；
- 锁定 `offer.required` 无重复；
- 将 sync no-change 改为成功 result code。
- 冻结无品牌项目不得使用品牌覆盖，并明确 Logo/BGM 不支持 `null` clear。

建议复审后 `PG-BP-A=passed_with_boundary`，原因：

- 方案要求的领域定义、1:N 关系、字段所有权、v3、v2 projection、错误码、默认关闭 flag、旧项目兼容和读不写基线均已形成机器契约；
- rollback、客户端信任边界、视觉现状和 Stage 归因均有机器可验证证据；
- 定向测试、JSON、Ruff 和 diff check 通过；
- 首轮 P1/P2 Entry 修复项均已落实；
- 没有业务实现或外部动作越界。

本建议不代表以下能力已实现：

- 指定品牌 domain revision API；
- ProjectContextResolver；
- 新建项目原子绑定品牌和初始 v3 快照；
- 显式更换、覆盖和同步；
- v1/v2/v3 运行时双读；
- 轻量项目 UI；
- 四应用实际消费；
- 真实产物中的 Logo、颜色或 BGM 验证。

这些内容必须按方案从 `BRAND-PROJECT-1` 开始逐 Stage 实现。独立审查确认 PG-BP-A 前，台账继续停在 `BRAND-PROJECT-0`。
