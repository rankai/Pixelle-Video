# ADR-009 应用中心独立 SQLite

- 状态：accepted for COORD-0
- 决策：应用中心使用独立 `app_center.sqlite`；项目、Artifact、Version、AppRun、Handoff 由其持有。发布、资产、通用任务继续由各自数据库持有。
- 迁移：只允许 additive migration，先临时库 dry-run，再由后续 Stage 申请生产迁移；所有表带 `schema_version`/稳定 ID 语义。
- 一致性：跨库只传稳定引用和幂等键，不做跨库事务；重复消息必须幂等。
- 回滚：删除临时库或关闭 flags，不修改现有生产表。
