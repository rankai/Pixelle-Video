# APP-RESULT-HISTORY-0 Entry：生成记录块与结果基数冻结

- Stage：`APP-RESULT-HISTORY-0`
- Gate：`PG-ARH-A`
- Change Request：`CR-APP-RESULT-HISTORY-001`
- 状态：`passed_with_boundary`
- 日期：2026-07-30

## 1. 本阶段范围

本阶段只完成生成记录块 schema、语义契约、fixture、Feature flag 登记、视觉现状和回滚基线，没有修改 Repository、业务 API、业务 UI、生产数据库、LLM/TTS/RunningHub 或发布平台。

原 `PROGRAM-ROLLOUT/PG-L-WINDOWS-AND-PRODUCT-ACCEPTANCE` 继续作为暂停 checkpoint；Windows 实机、产品签字和真实 rollback/WebView SLA 的既有状态不变。

## 2. 已冻结的用户语义

### 2.1 一次生成是一块记录

- 一个 `AppRun` 对应一个历史记录块，不把候选结果拆成多条历史。
- “再次生成”创建新的 `AppRun` 和新的记录块；同一 Run 的可恢复重试仍属于原记录。
- 默认只看当前项目、当前应用的历史；用户可以轻量切换到当前项目的“全部成果”。
- 按 `result_available_at DESC, app_run_id DESC` 排序，cursor 必须稳定且不泄露数据库细节。
- `record_id` 固定等于 `app_run_id`；同一页和跨页不得重复出现同一 Run。

### 2.2 四类结果形态

| 应用 | 结果形态 | 一个记录块内展示 |
| --- | --- | --- |
| 门店营销文案 | `multi_copy` | 本次实际生成的全部文案方案；fixture 固定 3 条 |
| 爆款标题 | `multi_title` | 本次实际生成的全部标题；默认目标 6 条 |
| 抖音图文 | `single_carousel` | 一个完整图文成品；fixture 固定 5 页但仍只有 1 个成品项 |
| 数字人口播 | `single_video` | 一个最终可播放视频；fixture 固定 cover/publish_copy/spoken_script 为详情能力，不拆成结果卡 |

[`generation-record-block-v1.schema.json`](../../contracts/app-center/generation-record-block-v1.schema.json) 拒绝未知字段、绝对路径和 `..` 路径穿越，并用条件 schema 锁定 `app_id → result_shape → item.kind`。排队、运行、失败和取消记录允许空结果且 `result_available_at=null`；待确认和完成记录必须有结果，只有明确的 `legacy_unavailable` 旧记录例外。

[`generation-record-page-v1.schema.json`](../../contracts/app-center/generation-record-page-v1.schema.json) 冻结 `current_app/all_results` 查询返回、最多 20 个记录块和 opaque cursor。机器 harness 对 cursor 签名、项目/scope/app 绑定、相同时间的 `app_run_id` tie-break、跨页无重复遗漏和重复 Run 拒绝执行验证。

### 2.3 媒体成品卡显示预算

抖音图文主卡只显示：

- 真实封面；
- 标题；
- 页数；
- `预览`；
- `去发布`。

数字人口播主卡只显示：

- 真实封面或首帧；
- 标题；
- 时长；
- `播放`；
- `去发布`。

主卡最多两个操作。Artifact ID、版本、provider、model、工作流步骤、绝对路径、ContextSnapshot/Handoff ID、下载变体，以及数字人的脚本/封面附件均不得占用主列表。

### 2.4 只读投影和旧数据

- 事实来源继续是现有 `app_runs`、`artifacts`、`artifact_versions`、`artifact_handoffs` 和 `app_events`。
- 不创建第二套结果事实表。
- 列表和预览必须只读；不得在读取时回填、更新时间戳或创建 ArtifactVersion。
- 来源不明的旧记录 fail-closed，只显示“这条旧记录暂时无法展示”，不得猜测归类或写回。
- 项目隔离是阻断条件，不能用前端过滤代替服务端约束。

## 3. Feature flag 与回滚

在 [`feature-flag-matrix.json`](../../contracts/app-center/feature-flag-matrix.json) 登记：

```text
name: appResultHistoryV1
backend_env: PIXELLE_APP_RESULT_HISTORY_V1
frontend_env: VITE_APP_RESULT_HISTORY_V1
default: false
owner_stage: APP-RESULT-HISTORY-3
```

Entry 未接入运行时。未来同步关闭前后端开关时：

- 恢复现有结果面板；
- 保留全部 AppRun、Artifact、ArtifactVersion 和媒体；
- 不删除、不回写旧结果；
- 不产生平台动作或最终发布点击。

## 4. Fixture 和机器断言

[`app-result-history-entry-fixtures.json`](../../contracts/app-center/fixtures/app-result-history-entry-fixtures.json) 包含：

- 3 条营销文案在一个记录块；
- 6 条爆款标题在一个记录块；
- 5 页图文仍只有一个 carousel 成品；
- video + cover + publish_copy + spoken_script 仍只有一个数字人成品；
- running/failed 空结果记录和 legacy 单条不可预览记录；
- 图文页面被拆成多结果、数字人封面被拆成结果、超过两个主操作、绝对路径泄露、provider 泄露和跨项目游标等负例；
- `current_app` 与 `all_results` 查询范围、稳定 cursor 与篡改/跨项目负例。

[`app_result_history_entry_contract_test.py`](../../../tests/app_result_history_entry_contract_test.py) 对 JSON Schema、自定义跨字段语义、显示预算、Feature flag、回滚和零外部动作执行机器校验。

## 5. 视觉现状

只读归档四应用当前结果页，见 [`qa/APP-CENTER-RESULT-LIST-2026-07-30`](qa/APP-CENTER-RESULT-LIST-2026-07-30)：

- 门店文案：已有真实项目和 3 个生成方案；
- 爆款标题：已有真实项目和候选结果；
- 当前图文结果更像交付/技术面板，不像一个可直接预览的完整成品；
- 数字人使用持久化 completed AppRun 结果页，明确显示 final video、cover 和 publish copy 被拆成多行及 6 个步骤；
- 四张基线图的 URL、采集时间、运行环境、尺寸、SHA-256、console 产品错误 `0` 和既有 Ant Design 弃用警告均写入 `manifest.json`；
- 8 个后续业务文件记录 Entry 起始工作区 hash，避免把先前已批准的脏工作区变化错误归因到本阶段。

## 6. 验证结果

| 检查 | 结果 |
| --- | --- |
| Entry 定向测试 | `21 passed` |
| Entry + APP-WORKBENCH Entry + 协调回归 | `49 passed` |
| JSON Schema 自校验 | `passed` |
| JSON parse | `passed` |
| Ruff check | `passed` |
| Ruff format check | `passed` |
| `git diff --check` | `passed` |
| 业务 Repository/API/UI 修改 | `0` |
| 数据库迁移/生产写入 | `0` |
| LLM/TTS/RunningHub/平台动作 | `0` |
| 最终发布点击 | `0` |

## 7. Gate 建议

首轮独立审查为 `P0=0 / P1=6 / P2=3`，未放行。修复已覆盖：

- 精确 Gate fixture 和四应用真实视觉基线；
- non-terminal/failed/legacy 空结果状态；
- `app_id/result_shape/item.kind` 条件 schema 和 `record_id=app_run_id`；
- page schema、稳定 cursor、项目/scope/app 绑定和跨页无重复；
- 移除 24 项静默截断上限，全部实际候选必须返回；
- 文本操作统一为 `copy/select/edit`，不常驻“详情”；
- legacy 不可预览改成列表 HTTP 200 内的 per-record 兼容状态；
- 方案头状态和相对 URL 路径穿越。

第二轮独立审查为 `P0=0 / P1=1 / P2=3`，唯一阻断是相同 AppRun 可能跨页静默遗漏。本轮已将 `record_id=app_run_id` 和 AppRun 唯一性校验前移到分页前的完整 filtered 集合，并新增：

- `limit=1` 重复 Run 跨页负例；
- 单记录 ID 不一致负例；
- 实际篡改 HMAC cursor 负例；
- 相同 `result_available_at` 下 `app_run_id DESC` 的两页稳定排序；
- 方案 DTO/API 命名与机器 schema 对齐。

第三轮独立审查为 `P0=0 / P1=1 / P2=0`，只剩方案两行仍允许文本候选截断。本轮已明确：候选目标数只能在创建 AppRun 前由生成领域限制；AppRun 已实际产出的候选，结果投影必须全部返回，不得截断。

第四轮同一独立审查线程最终确认：

```text
P0=0
P1=0
P2=0
PG-ARH-A=passed_with_boundary
```

协调层据此设置：

```text
current_stage=APP-RESULT-HISTORY-1
current_substage=READ_PROJECTION_AND_API
```

边界是：Entry 只证明需求和契约清晰、机器可验证、可回滚；真实只读投影、API 性能、旧数据读取、桌面交互和媒体预览均属于后续 Gate，不能用本 Entry 证据替代。
