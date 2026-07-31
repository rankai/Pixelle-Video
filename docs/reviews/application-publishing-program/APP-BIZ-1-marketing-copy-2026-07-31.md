# APP-BIZ-1 门店营销文案验证记录

日期：2026-07-31

状态：实现完成，等待独立六维复验确认

## 交付边界

- v2 输入从项目快照读取 `project_brief`，保留营销目标、主推商品、受众、卖点和已知事实。
- 输出固定为 3 条可编辑 `full_text`，ArtifactVersion 使用 schema v2；旧 v1 结果继续只读兼容。
- 只做结构、数量、长度和未提供具体事实校验；不做角度、相似度、禁词、风险或派生字数/时长判断。
- 文案复制、编辑、采用和文案→爆款标题 typed handoff 均固定使用结果版本，不热更新来源。

## 自动验证依据

- Python：106 个应用中心、结构化执行、结果历史、输入契约和工作台契约定向测试通过。
- Desktop：CreationWorkspace 与 ProjectGenerationHistory 共 41 个测试通过。
- Desktop `tsc + vite build` 通过；Python compileall 与 `git diff --check` 通过。

## 真实运行依据

- 使用现有 `local-default` 配置在临时 SQLite 项目执行一次 v2 marketing-copy。
- AppRun 状态：`needs_review`；provider：`openai_compatible`；model：`local-default:doubao-seed-2-0-pro-260215`。
- ArtifactVersion schema：2；variants：3；每个 variant 的字段集合均为 `["full_text"]`。
- 人工检查三条文本未出现输入未提供的价格、日期、地址或保证性字段；未触发发布、平台或其他外部动作。

## 独立复验要求

同一只读审查线程需从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖和实际运行结果六个方面复验；若发现问题，主线程修复后继续复验，直到给出 PASS 及逐项依据。
