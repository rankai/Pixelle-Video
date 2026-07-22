# ADR-PublishPackageV2

- 状态：accepted for COORD-0
- 决策：新应用使用 `source.kind=artifact_versions`，引用不可变 ArtifactVersion；旧 IPB 在迁移完成前使用 `legacy_session`，此时才允许 session_id。
- V2 package 为发布域 immutable snapshot，包含 package fingerprint、source revision 和 artifact refs；不得嵌套 `publish_package_ref`。
- source 不变量由 JSON Schema、SQL CHECK 和 domain semantic validator 三层验证。
- 回滚：保持旧 V1 package adapter 只读，关闭 V2 flag，不回写应用中心 Artifact。
