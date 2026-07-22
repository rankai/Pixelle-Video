# AC-3 real provider handoff E2E — 2026-07-20

状态：`passed_with_boundary`

范围：全新临时 SQLite 项目；复用现有 `local-default` 配置，执行真实文案→标题 handoff→版本保存，不触发桌面发布、抖音或任何外部写操作。

脱敏运行证据：

- project：`project_69f1fe33d9154b4090477816fbc259aa`
- context snapshot：`context_500fa1cdc32f4f249b136a7e70d87757`
- marketing AppRun：真实 `openai_compatible` provider，最终 `completed`；ArtifactVersion=`artifact_version_aa4a027262f04bf5b433d004f48caff5`。
- source artifact：`artifact_type=copywriting`、`schema_version=1`；viral-titles AppRun 通过同项目 source version 解析并复用 context snapshot。
- viral-titles AppRun：真实 `openai_compatible` provider，引用上述同项目文案版本，最终 `completed`；5 个标题候选；ArtifactVersion=`artifact_version_ae427865394943a3aa34e5ea0af25599`。
- handoff：`handoff_7af5d89ef6604994868b85f11d598249`，source version 为文案版本，target run=`run_1eec6bbb2ef9497c9d4dda35bf1424d2`。
- 运行脚本使用临时 SQLite，执行结束只保留脱敏 ID/状态证据，不写入工作区业务数据库。
- marketing provider 使用一次 repair 后通过；title provider 单次结构化返回通过；所有版本均由 AppRunner 保存并可读取。

验证结论：真实 provider、ArtifactVersion 持久化、同项目来源解析、标题输出和 typed handoff 已形成可复核闭环。测试脚本曾有一次把 `current_version_id` 当 Artifact ID 的读取错误，修正为 `get_artifact_version` 后重新执行，未修改产品代码。

边界：仅一组真实门店输入；细粒度编辑控件、六类门店 fixture 的真实质量对比、超时/鉴权/限流现场矩阵和 PG-D 完整 Gate 仍未完成。
