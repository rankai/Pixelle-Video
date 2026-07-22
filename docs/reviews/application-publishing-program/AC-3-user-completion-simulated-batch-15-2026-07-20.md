# AC-3 内部模拟用户批次 15 — 十类门店浏览器任务

状态：`simulated_internal_user_passed_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0；可作为 AC-D 内部模拟任务分支证据。PG-D 完整 Gate 已以 `passed_with_boundary` 通过。

本批次响应用户授权，使用项目现有 Python Playwright 在本地应用中心模拟十类中小门店用户，逐个执行首条文案主流程。每个场景只执行一次；失败即记录，不重试。

## 模拟范围

每个场景完成：

`应用中心 → 门店营销文案 → 填写项目/目标/产品 → 保存草稿 → 创建运行草稿 → 执行 → 待审核 → 确认完成`

所有项目/运行写入由浏览器 `**/api/**` route mock 隔离；未调用真实 LLM/provider，不创建 ArtifactVersion，不触发发布。模拟中的“无需解释”定义为：脚本没有 helper/explanation API、没有人工介入，且 8 个主路径动作均完成。

## 结果

机器证据：[`AC-3-user-completion-playwright-simulated-batch-15.json`](qa/AC-3-user-completion-playwright-simulated-batch-15.json)。

| 指标 | 结果 |
| --- | ---: |
| 场景数 | 10 |
| 最终 `completed` | 10/10 |
| 无解释/无人工介入 | 10/10 |
| 每场景动作数 | 8 |
| 意外控制台错误 | 0 |
| 已知 antd 弃用 warning | 20（每场景 `Space.direction`、`List` 各 1 条） |
| 未识别非 GET 写请求 | 0 |
| 真实 provider 调用 | 否 |
| ArtifactVersion 创建 | 否 |
| 发布触发 | 否 |

最终机器 JSON 的浏览器自动化 wall time（以 JSON 为唯一事实源）为：`hotpot=1538ms`、`beauty=1196ms`、`homestay=1200ms`、`laundry=1119ms`、`training=1189ms`、`retail=1150ms`、`coffee=1117ms`、`bakery=1116ms`、`fitness=1510ms`、`pet=1406ms`。

## 证据与验证

- 脚本：[`ac3_playwright_simulated_batch_15.py`](qa/ac3_playwright_simulated_batch_15.py)。
- 截图：[`AC-3-user-completion-playwright-simulated-batch-15.png`](qa/AC-3-user-completion-playwright-simulated-batch-15.png)，SHA-256：`bcde60f8a44e1ab9fb961a9ae3b6054c0ada67de80b7bf7b3b5a50fa180de38f`。
- 机器 JSON 中记录每场景 UTC 起止时间、动作列表、耗时、最终状态、求助次数、人工介入、失败原因、未知写请求、控制台 warning/error 及脚本/截图 SHA。
- 应用内 Browser 运行时此前启动失败 `Cannot redefine property: process`，本批次按已批准 fallback 使用 Python Playwright；因此不声称通过应用内 Browser 连接器。

## 边界

- 这是内部模拟任务，不是十名真实用户，也不是目标用户访谈；它用于满足 AC-D 中“内部模拟任务”分支的首路径证据。
- 因为 provider、ArtifactVersion 和发布均被 mock/禁止，本批次只证明 UI 主路径和状态机交互，不证明真实内容质量或真实 provider 运行。
- 已知 antd warning 是既有技术债，不属于本批次新增业务错误；后续可单独迁移 `Space.direction` 与 `List` API。
- PG-D 完整 Gate 已由独立严格审查线程确认 `passed_with_boundary`；后续图文、数字人或发布平台 Stage 仍须按进度台账的显式 Entry 启动，不得自动进入。
