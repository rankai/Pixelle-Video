# AC-3 用户完成度合成预检批次 14 — 首次文案流

状态：`synthetic_internal_precheck_passed_with_boundary`

独立终审：`/root/pg_a_closure_reviewer_v3`，六维复验通过，P0/P1=0。

本批次用于在进入真实用户可用性测试前，验证 CreationWorkspace 的首个“填写项目 → 保存草稿 → 创建运行 → 执行 → 待审核 → 确认完成”主路径是否能在十类中小门店输入下无辅助说明即可完成。它是内部合成交互预检，不是目标用户研究，也不替代真实 provider、浏览器视觉验收或发布验收。

## 场景与结果

| 场景 | 输入 | 结果 |
| --- | --- | --- |
| 火锅老板 | 周末双人套餐 / 火锅 | passed |
| 美容老板 | 新客到店体验 / 美容 | passed |
| 民宿老板 | 工作日入住 / 民宿 | passed |
| 洗衣老板 | 换季洗护 / 洗衣店 | passed |
| 培训老板 | 试听报名 / 培训 | passed |
| 零售老板 | 新品到店 / 零售 | passed |
| 咖啡老板 | 下午茶到店 / 咖啡 | passed |
| 烘焙老板 | 新品试吃 / 烘焙 | passed |
| 健身老板 | 新客咨询 / 健身 | passed |
| 宠物店老板 | 洗护预约 / 宠物店 | passed |

结果为 10/10：每个场景都完成了保存项目、创建运行草稿、点击执行和确认完成；测试同时断言 API payload 包含目标与产品/服务，且没有调用 helper/explanation API。这里的“无辅助说明”仅指测试路径未调用 helper API，不是目标用户可用性结论。

## 验证命令

- `npm run test -- --run --reporter=dot`：4 个测试文件、19 个测试通过。
- `npm run build`：TypeScript 与 Vite production build 通过。
- 受控 Playwright headless smoke：咖啡店老板场景完成保存项目、创建运行、执行、待审核、确认完成，最终 `completed`；应用中心和未识别的非 GET 请求均由 `**/api/**` catch-all route mock 隔离，未写本地 API；本次 `blocked_unknown_write_count=0`；截图见 [`AC-3-user-completion-playwright-synthetic.png`](qa/AC-3-user-completion-playwright-synthetic.png)，机器证据见 [`AC-3-user-completion-playwright-synthetic.json`](qa/AC-3-user-completion-playwright-synthetic.json)，脚本见 [`ac3_playwright_synthetic.py`](qa/ac3_playwright_synthetic.py)。截图 SHA-256：`dfd9a5bd4271e176055a8e89d70885f0189e698a5b408919e0f259c18c44cc85`。
- 构建保留既有 antd deprecation warnings 和单个大 chunk warning；本批次未扩大其范围。

## 严格边界

- 测试使用 React Testing Library + mocked API/状态，不调用真实 LLM/provider，不写真实 ArtifactVersion，不触发发布。
- 本批次没有目标用户、没有真实用户任务耗时/成功率/求助率，不能把 10/10 解读为用户完成度 Gate 通过。
- 应用内 Browser 连接器在启动时遇到 `Cannot redefine property: process`；本批次改用项目既有 Python Playwright 依赖完成一次受控 headless DOM/截图 smoke，但这仍不是应用内 Browser 连接器验收，也不是目标用户研究。
- PG-D 仍保持未完成；下一步应在不盲试 provider 的前提下安排一次真实目标用户/人工验收，并把真实任务结果、完成时间、求助次数和失败原因写入台账。

严格审查结论：合成预检通过边界，P0/P1=0。审查线程确认 mock 序列与 CreationWorkspace 的三次 `listAppRuns` 状态流匹配，十项参数化场景未见串场。

结论：内部首路径合成预检通过边界；不关闭 PG-D，不进入图文/数字人/发布平台 Stage。
