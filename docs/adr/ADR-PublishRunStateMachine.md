# ADR-PublishRunStateMachine

- 状态：accepted for COORD-0
- 决策：Run 状态为 queued、running、waiting_for_login、waiting_for_human、needs_attention、succeeded、failed、cancelled；`waiting_for_human`、`waiting_for_login`、`needs_attention` 绝不映射为成功。
- 所有 run 强制 `human_confirmation_required=true`；只有人工确认后才可进入 succeeded。
- 幂等键为 package/account/attempt 组合，重试创建新 attempt，不覆盖旧证据。
- 回滚：停止调度、保持当前状态和证据，禁止自动补偿发布。
