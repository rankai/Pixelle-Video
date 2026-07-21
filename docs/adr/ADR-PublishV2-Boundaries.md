# ADR-PublishV2-Boundaries

- 状态：accepted for COORD-0
- 决策：PublishPackage V2、PublishRun、AccountProfile、StepResult 和平台证据属于 publishing 域；应用中心只产生 `publish_package_ref`。
- Generic Task 是投影，不是发布事实；PublishRun 是发布状态唯一事实源。
- V2 浏览器流程只能到 `waiting_for_human`，FinalActionGuard 拒绝最终发布动作。
- 回滚：V2 总开关关闭后回 V1 adapter，保留 V2 数据只读，不删除 profile/cookie。
