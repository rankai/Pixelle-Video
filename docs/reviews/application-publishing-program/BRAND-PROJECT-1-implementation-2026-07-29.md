# BRAND-PROJECT-1 品牌包与项目边界实施证据

日期：2026-07-29
Stage：`BRAND-PROJECT-1`
Gate：`PG-BP-B`
结论：实现完成，等待独立六维复审；未进入 Stage2。

## 1. 本阶段完成范围

1. 品牌 domain revision 支持按 `kind/resource_id/revision` 精确读取，缺失时返回空，不回退最新版本；进入项目上下文前严格校验 envelope、必填字段、字段类型、颜色格式和 `resource_id/payload.brand_id` 一致性，不补默认值、不做 `str()` 洗白。
2. 新增 `ProjectContextResolver`，以只读方式解析 v1/v2/v3 快照：
   - 校验快照归属项目；
   - 校验 fingerprint；
   - v3 校验服务端品牌来源、精确 domain revision 和固定媒体 revision；
   - 输出不含绝对路径、Provider 配置或密钥的 `ApplicationContext`。
3. 新建品牌项目使用 AppDB 单个 SQLite 事务写入项目、首个 `ContextSnapshot v3` 和 current pointer。
4. 品牌绑定、更换、解除绑定使用显式领域命令：
   - 旧快照不修改；
   - 新快照与项目 brand/current pointer 同事务切换；
   - 支持 expected context/domain revision 冲突检测；
   - 归档项目、归档品牌、缺失品牌版本或媒体版本均失败关闭。
5. Logo、默认 BGM 在创建/绑定时固定当时的 `asset_revision`，不会跟随媒体 current revision 漂移。
6. v3 品牌投影只由服务端解析。通用 context API 拒绝客户端提交：
   - `schema_version=3`
   - `brand_context`
   - v3 的非空 `source_brand_id/source_brand_revision_id`
   - v1/v2 历史 source 字段继续兼容，但由服务端校验项目品牌关系、精确 domain revision 和 v2 `brand_revision_ref`
7. DDL 和安全迁移允许 `ContextSnapshot schema_version IN (1,2,3)`；旧 v1/v2 行原样保留。
8. 新写能力由 `PIXELLE_BRAND_PROJECT_BOUNDARY_V1` 控制，默认关闭；v1/v2/v3 读取兼容不依赖开关。
9. flag 关闭时返回显式 `context_snapshot_v2` projection DTO，使用独立 `projection_fingerprint`，不复用或伪装原 v3 snapshot fingerprint。

## 2. API 与领域入口

- `GET /api/v2/domain/brands?status=ready`
- `GET /api/v2/domain/brands/{brand_id}/project-summary`
- `GET /api/v2/domain/brands/{brand_id}/revisions/{revision}`
- `POST /api/content-projects`
  - flag 开启且关联品牌时，要求 `expected_brand_domain_revision`
  - 服务端在 AppDB 内原子创建项目和 v3 快照
- `POST /api/content-projects/{project_id}/brand-binding`
  - `brand_id` 为字符串：绑定或更换
  - `brand_id=null`：解除绑定
  - 已有快照时要求 `expected_context_snapshot_id`

## 3. 已验证不变量

- `source_brand_id == payload.brand_context.brand_id`
- `int(source_brand_revision_id) == payload.brand_context.domain_revision`
- v3 fingerprint 覆盖 schema version、完整 payload 和品牌来源字段；已部署 v1/v2 payload-only fingerprint 继续只读兼容
- 品牌标量来自指定历史 revision；项目覆盖项记录在 `overridden_fields`
- Logo/BGM 与项目素材均是明确 `{asset_id, asset_revision}`
- v1/v2/v3 读取不写入项目库或资产库
- 绑定失败不会留下半个项目或孤立快照
- 创建/换绑使用 `BEGIN IMMEDIATE`；`expected_context_snapshot_id`（包括 `null`）在同一事务内 CAS，并发冲突不会覆盖其他写入
- 品牌首次解析后、AppDB 写前以 AssetDB `BEGIN IMMEDIATE` guard 二次校验品牌仍为 ready、current revision 未变且 immutable payload 一致；并发归档/更新发生在 guard 前则失败关闭且 AppDB 零写，发生在 guard 后则等待已固定快照提交
- 旧 AppRun 已固定的 snapshot 不被改写

AssetDB 与 AppDB 不是跨库原子事务，本证据不作该声明。写入顺序固定为：

1. 无锁解析并验证历史品牌和媒体 revision；
2. AssetDB `BEGIN IMMEDIATE` 获取只读 revision guard 并执行 CAS 式二次校验；
3. guard 持有期间执行 AppDB 单库事务；
4. AppDB 成功后释放 guard；AppDB 失败则其事务回滚，AssetDB 因全程无写入而无需数据补偿。

## 4. 验证结果

最终定向与扩展回归命令：

```text
uv run pytest -q \
  tests/brand_project_stage1_test.py \
  tests/app_workbench_project_context_test.py \
  tests/brand_project_boundary_entry_contract_test.py \
  tests/app_center_api_test.py \
  tests/app_center_registry_test.py \
  tests/asset_library_v2_repository_test.py \
  tests/config_llm_profiles_test.py \
  tests/coord0_contract_test.py
```

终验修复后的最终结果：`107 passed, 12 existing Pydantic deprecation warnings`。其中 Stage1 审查探针文件定向结果为 `32 passed`。

网络中断前的分批结果为 `27 passed` 和 `23 passed`；首次完整聚合得到 `91 passed`，另有 1 个临时 SQLite `disk I/O error`，该用例隔离重跑通过。磁盘恢复后当时的聚合稳定得到 `92 passed`；第二轮审查修复新增探针后最终为上述 `106 passed`，最终证据不包含环境失败。

覆盖范围：

- 历史品牌 revision 精确读取与 missing revision；
- ready 品牌缺失全部历史 revision 时，project-summary 与精确 revision API 一致返回 `PROJECT_BRAND_REVISION_NOT_FOUND / HTTP 409`，不虚构 revision 1；
- 品牌 revision 缺字段、错误类型、`brand_id` 不一致均失败关闭；
- 原子创建、品牌绑定/更换/解绑；
- 首次解析与 AppDB 写之间并发归档/更新的二次校验和全表零写；
- current context 乐观并发冲突；
- 归档项目/品牌、缺失媒体 revision；
- Logo/BGM revision 固定；
- v3→v2 projection fingerprint 可重算、flag-off 兼容读取和读接口零写；
- v1/v2 source 字段兼容与服务端关系/revision 校验，v3 客户端 source revision/brand context 伪造拒绝；
- v1 legacy 只接受字符串、字符串数组或严格 `ContextFact` 对象，歧义 dict/list/number 失败关闭；
- brands summary/revision API 的稳定 code、HTTP 和中文安全文案；
- `IN (1,2)` 到 `IN (1,2,3)` 迁移及 v2 行保留；
- 迁移前后 `AppRun` / `run_attempt` 引用保留和仓储重启读取；
- 资产库和应用中心既有回归。

静态检查：

```text
uv run ruff check <Stage1 touched Python files and tests>
uv run ruff format --check <Stage1 touched Python files and tests>
uv run python -c '<parse contract JSON and jsonschema check_schema>'
git diff --check
```

检查范围包括 `api/config.py`、`api/routers/assets_v2.py`、`docs/contracts/app-center/app-center-v1.sql`、flag/schema/fixture、全部 Stage1 实现和八个聚合测试文件。结果：Ruff check/format、契约与 QA JSON 解析、JSON Schema 自检、全量 artifact hash 和 `git diff --check` 全部通过。逐文件 SHA-256 记录在 [`qa/BRAND-PROJECT-1-implementation-2026-07-29.json`](qa/BRAND-PROJECT-1-implementation-2026-07-29.json)。

## 5. 首轮独立审查修复

首轮独立审查结论为 `P0=0 / P1=8 / P2=2`。本轮已按 Stage1 边界完成修复并补齐回归：

- `BEGIN IMMEDIATE` + current snapshot CAS（含 `null`）；
- v1/v2 payload-only fingerprint 兼容与 v3 envelope fingerprint；
- v3→v2 纯读投影，flag 关闭仍可读取既有 v3；
- 稳定错误码、HTTP 状态与中文安全文案；
- 损坏品牌 revision、错误媒体来源/revision/type 均失败关闭；
- 换绑前验证当前快照完整性；
- v1/v2 仅允许安全、可证明的业务映射；
- 项目库和资产库全表读前/读后零写；
- `IN (1,2)` 迁移保留 `AppRun` / `run_attempt` 并验证重启。

Gate 仍保持 `PG-BP-B_implementation_review_pending`，等待独立复审确认，不据此自行进入 Stage2。

## 6. 第二轮独立审查修复

第二轮独立审查结论为 `BLOCKED P0=0 / P1=6 / P2=1`。本轮已逐项补探针并完成：

- strict brand domain revision envelope/payload 校验，无缺字段默认或类型强转；
- AssetDB guard + AppDB 单库事务的清晰跨库顺序，并发归档/更新失败关闭；
- 显式 projection DTO 与可重算 `projection_fingerprint`；
- brands project-summary/revision 只读 API 稳定错误契约；
- v1 legacy 白名单、严格字符串/数组/规范 fact 映射；
- v1/v2 `source_brand_*` 兼容且由服务端验证，v3 仍拒客户端伪造；
- Ruff/format/hash 扩展到 assets router、配置、SQL 和全部 Stage1 文件。

Gate 继续为 `PG-BP-B_implementation_review_pending`，等待独立复审。

## 7. 终验剩余项修复

终验剩余 `P1=1` 指出：ready 品牌删除全部 `domain_revisions` 后，project-summary 曾由 brand metadata 分支回填虚构的 revision 1。现仅收紧 brand 分支：

- `domain_snapshot_metadata("brand", ...)` 在历史集合为空时返回 `domain_revision=null`，不回填 1；
- project-summary 对无效/缺失 revision 返回 `PROJECT_BRAND_REVISION_NOT_FOUND / HTTP 409` 和冻结中文安全文案；
- 精确 revision 端点保持同一 409 契约；
- template、digital-human、voice 等其他 kind 的兼容行为未改变；
- 新增双库全表 before/after 零写回归。

Gate 仍为 `PG-BP-B_implementation_review_pending`。

## 8. 明确未做

- 未修改任何业务 UI；
- 未实现“同步最新品牌资料”或差异预览（归 Stage2）；
- 未改变“我的项目”和“企业资产库”的前端信息结构；
- 未调用 LLM、RunningHub、浏览器或任何发布平台；
- 未点击最终发布；
- 未修改生产数据库；
- 未提交 Git。

## 9. Gate 建议

实现线程建议将 `PG-BP-B` 置为 `implementation_review_pending`。只有独立六维复审确认 P0/P1/P2 可接受后，协调层才可切换 `BRAND-PROJECT-2`。
