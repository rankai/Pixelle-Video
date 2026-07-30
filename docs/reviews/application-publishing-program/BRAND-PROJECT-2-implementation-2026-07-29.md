# BRAND-PROJECT-2 品牌资料差异预览与显式同步实施证据

日期：2026-07-29
Stage：`BRAND-PROJECT-2`
Gate：`PG-BP-C`
结论：实现完成，等待独立六维复审；未进入 Stage3。

## 1. 本阶段完成范围

1. 新增只读品牌差异预览：
   - `GET /api/content-projects/{project_id}/brand-sync-preview`
   - 仅返回普通用户可读的字段标签、变化状态和“仅本项目使用”的覆盖保留说明；
   - 不返回品牌 revision、snapshot id、fingerprint、绝对路径或 Provider 配置；
   - 预览前后 AppDB、AssetDB 全表内容一致。
2. 新增显式品牌同步：
   - `POST /api/content-projects/{project_id}/brand-sync`
   - 请求必须携带 `expected_context_snapshot_id` 和 `idempotency_key`；
   - 非覆盖品牌字段采用最新品牌资料，项目覆盖字段和 `project_brief` 原样保留；
   - Logo、默认 BGM 重新固定最新可用媒体 revision；
   - 有业务变化时追加 `ContextSnapshot v3` 并原子切换 current pointer；
   - 已是最新资料时返回 `PROJECT_BRAND_SYNC_NO_CHANGE`，不追加快照。
3. 新增持久化幂等记录 `brand_sync_requests`：
   - `(project_id, idempotency_key)` 唯一；
   - 相同请求重试和仓储重启后返回首次结果；
   - 同 key 不同请求指纹失败关闭；
   - `no_change` 仅记录幂等请求事实，不写项目或快照。
4. 同步继续使用 Stage1 的跨库顺序：先解析候选资料，再持有 AssetDB `BEGIN IMMEDIATE` revision guard，guard 内同时 CAS 品牌 revision 和候选 Logo/BGM，随后执行 AppDB 单库 `BEGIN IMMEDIATE` 事务；不声称跨数据库原子事务。
5. 品牌归档、缺失 domain/media revision、并发更新、归档项目、expected snapshot 过期均失败关闭。
6. v1/v2 当前快照只在用户显式同步且成功时升级为 v3；原 v1/v2 快照不修改。v3 正常追加；`brand_id=null` 预览为未绑定，显式同步返回稳定失败。
7. 同步前创建的 Snapshot、AppRun、Artifact、ArtifactVersion 保持不变，历史生成结果不会因品牌后续修改而漂移。
8. 能力继续由 `PIXELLE_BRAND_PROJECT_BOUNDARY_V1` 控制：flag 关闭时 preview/sync 稳定返回 `BRAND_PROJECT_BOUNDARY_DISABLED / HTTP 404 / 品牌项目功能当前未启用`，但既有 v3 仍可通过 v2 projection 读取；重新开启和仓储重启后可恢复显式同步。
9. 未绑定项目显式同步稳定返回 `PROJECT_BRAND_NOT_BOUND / HTTP 409 / 这个项目尚未关联品牌，请先选择品牌包`，不再复用“品牌不存在”。

## 2. 事务与幂等边界

有变化同步的 AppDB 单事务包含：

1. 校验项目未归档、品牌绑定未变化、current snapshot 等于 expected；
2. 校验幂等 key 未被不同请求使用；
3. 追加不可变 `ContextSnapshot v3`；
4. 更新 `ContentProject.current_context_snapshot_id`；
5. 写入持久化幂等结果。

任一步失败则 AppDB 全部回滚。AssetDB 在此流程只读，并由 revision guard 确保解析后到 AppDB 提交期间品牌状态、current domain revision 和 immutable payload 未变化。

对候选中未覆盖的 Logo/BGM，guard 同时校验 `media_assets.status=ready`、`media_kind`、`current_revision_id` 等于候选固定 revision，并校验 exact revision 存在且归属该 asset。并发归档或新增 revision 发生在 guard 前会失败关闭，AppDB 全表零写；发生在 guard 后则等待已固定快照提交。

从已验证当前 snapshot 继承的 Logo/BGM 项目覆盖使用历史 exact-only 语义：要求 asset/revision 存在、归属正确且媒体类型匹配，但允许 asset 后来归档或 current revision 前移。客户端新选择的覆盖仍要求 `ready + current`，并进入同一 guard CAS。

`no_change` 不创建快照、不更新项目 pointer；仅在 AppDB 事务内持久化幂等响应，因此重启后重复请求仍得到同一业务结果。

## 3. 已验证不变量

- preview 零写；
- 同步只由显式 POST 触发，不在读取或生成时隐式同步；
- `expected_context_snapshot_id` 在 AppDB 事务内做 CAS；
- 非覆盖字段跟随最新品牌资料；
- `overridden_fields` 的值和集合均保持；
- `project_brief`、项目素材引用保持；
- Logo/BGM 采用同步时解析的明确媒体 revision；
- 非覆盖 Logo/BGM 在 AssetDB guard 内完成 ready/kind/current/exact CAS；
- 历史 Logo/BGM 项目覆盖允许复制已归档但仍存在的 exact revision；
- 新选择的媒体覆盖必须是当前 ready revision；
- `no_change` 不产生重复 snapshot；
- 同 key 同请求在进程内、重启后均幂等；
- 同 key 不同请求不泄露 key，返回安全冲突；
- 旧 snapshot、AppRun、Artifact、ArtifactVersion 不改写；
- v1/v2/v3、null brand、flag-off/reenable、旧 DDL 迁移和重启可恢复；
- 归档品牌/项目、缺 revision、并发品牌更新均失败关闭。

## 4. 验证结果

最终定向与扩展回归：

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

审查修复后的结果：`124 passed, 12 existing Pydantic deprecation warnings`。其中 Stage2 专项文件为 `17 passed`。

覆盖范围：

- preview 差异、覆盖保留说明和双库零写；
- applied sync 的快照追加、pointer 切换、Logo/BGM 重新固定；
- no-change、持久化幂等、重启重放、同 key 请求冲突；
- v1/v2 显式升级到 v3 且旧快照不变；
- archived/missing revision/null brand/expected snapshot 冲突失败关闭；
- 解析后到 guard 前品牌并发更新失败关闭；
- Logo/BGM 分别在 guard 前并发归档、追加 revision 的四组故障注入，AppDB 全表零写；
- 已归档 Logo/BGM 历史项目覆盖的 exact revision 原样保留；
- 新媒体覆盖使用非 current revision 时失败关闭；
- flag-off 禁止写、v3 projection 可读、reenable 与重启恢复；
- API preview/apply/repeat/no-change/stale expected、flag-off 和未绑定项目稳定 code/message contract；
- Stage1 DDL 到 Stage2 DDL 安全迁移，项目、AppRun、ArtifactVersion 和外键保留。

静态与契约检查：

```text
uv run ruff check <Stage1+Stage2 touched Python files and tests>
uv run ruff format --check <Stage1+Stage2 touched Python files and tests>
uv run python -c '<parse contract and QA JSON; jsonschema check_schema>'
uv run python -c '<execute app-center-v1.sql in temporary SQLite and inspect FK>'
git diff --check
```

Ruff check/format、JSON 解析、JSON Schema 自检、SQL 建库、外键检查、artifact SHA-256 和 `git diff --check` 均通过。逐文件哈希记录在 [`qa/BRAND-PROJECT-2-implementation-2026-07-29.json`](qa/BRAND-PROJECT-2-implementation-2026-07-29.json)。

## 5. 首轮独立审查修复

首轮独立审查结论为 `BLOCKED P0=0 / P1=2 / P2=1`。本轮已逐项修复：

- 将候选非覆盖 Logo/BGM 的 ready/kind/current/exact 校验纳入 AssetDB `BEGIN IMMEDIATE` guard，并保持 guard 持锁期间执行 AppDB 事务；
- 区分“从已验证当前 snapshot 继承的历史覆盖”和“本次新选择覆盖”，前者 exact-only、后者 ready/current；
- 冻结 `PROJECT_BRAND_NOT_BOUND` 与 `BRAND_PROJECT_BOUNDARY_DISABLED` 的 HTTP 和准确中文文案；
- 补齐 Logo/BGM 并发归档/新增 revision、归档历史覆盖保留、新覆盖旧 revision 拒绝和 API 错误响应探针。

Gate 继续保持 `PG-BP-C_implementation_review_pending`，等待独立复审，不进入 Stage3。

## 6. 独立终验

PG-BP-C 独立终验确认 `PASS P0/P1/P2=0`，Stage2 以 `passed_with_boundary` 关闭。协调层据此才可串行切换 `BRAND-PROJECT-3 / PG-BP-D_implementation_in_progress`。

## 7. 明确未做

- 未修改任何业务 UI，自动选择唯一品牌包和同步提示界面留给 Stage3；
- 未调用 LLM、TTS、RunningHub、浏览器或任何发布平台；
- 未扫码、授权、上传或点击最终发布；
- 未修改生产数据库；
- 未提交 Git；
- 未进入 `BRAND-PROJECT-3`；
- `PROGRAM-ROLLOUT/PG-L paused_external` checkpoint 未改变。

## 8. Gate 结论

`PG-BP-C=passed_with_boundary`。Stage3 只实施轻量项目 UI、共享组件、响应式与真实本地可视化验收，不调用 LLM、RunningHub 或发布平台。
