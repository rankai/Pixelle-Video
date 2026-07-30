# APP-WORKBENCH-2 项目上下文 Entry

- Stage：`APP-WORKBENCH-2`
- Gate：`PG-AW-C`
- 日期：2026-07-28
- 结论：`entry_passed_with_boundary`

## 1. 现状

- `ContextSnapshot` 表已经具备 `schema_version`、不可变 payload、fingerprint 和项目当前指针，不需要破坏性迁移。
- repository 目前把所有新快照写死为 v1，API 请求也没有显式版本字段。
- 三个结构化应用已经在创建 `AppRun` 时绑定 `context_snapshot_id`；数字人口播请求类型支持该字段，但桌面端尚未传入。
- `CreationWorkspace` 可以读取当前快照，但只以 JSON 提示展示；项目快速切换没有 stale-response 隔离。
- 项目名称/目标有未保存保护，项目上下文没有编辑器、本地草稿或重启恢复。

## 2. 本阶段最小增量

1. API 请求增加 `schema_version`，v1 默认继续兼容。
2. v2 使用冻结的 `context-snapshot-v2.schema.json` 等价字段校验，并增加事实冲突、跨项目 ArtifactVersion、缺失素材修订的稳定错误。
3. 每次保存只追加新 snapshot 并更新项目当前指针；历史 snapshot、Run 和 Artifact 不覆盖。
4. 新增共享 `ProjectContextSelector` 与 `ProjectBriefEditor`；v1 只显示映射预览，用户显式保存后才产生 v2。
5. 草稿按项目保存在本地；切换前提示，重启后恢复；异步请求用递增序号隔离旧响应。
6. 三个结构化应用和数字人口播的新 Run 均绑定开始生成时明确选中的 snapshot。

## 3. 稳定错误

- `PROJECT_CONTEXT_SCHEMA_UNSUPPORTED`
- `PROJECT_CONTEXT_INVALID`
- `PROJECT_CONTEXT_FACT_CONFLICT`
- `PROJECT_CONTEXT_CROSS_PROJECT_REF`
- `PROJECT_CONTEXT_ASSET_NOT_FOUND`

API 使用 `409` 和 `{code, message}`；不返回 provider、绝对路径、凭据或原始异常。

## 4. 回滚与禁止项

- `PIXELLE_APP_WORKBENCH_V2=false` 仍回到旧容器；ContextSnapshot 数据仍可读取。
- v1 snapshot 继续可读，不自动迁移。
- 不修改 StylePreset、应用 prompt/executor、LLM 配置、RunningHub、发布平台和最终发布确认。
- 不删除或原地更新历史 snapshot、Run、Artifact 和媒体文件。

## 5. Gate 证据要求

- repository/API：v1/v2、不可变追加、旧 Run 固定、五类稳定错误。
- desktop：v1 映射预览、显式保存、草稿/重启恢复、切换保护、stale-response 隔离、四应用 snapshot 绑定。
- 定向 Pytest、Vitest、desktop build、migration dry-run、diff check。
- 六维自审 P0/P1=0 后才允许切换 APP-WORKBENCH-3。
