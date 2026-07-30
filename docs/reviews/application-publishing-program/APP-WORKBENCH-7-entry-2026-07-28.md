# APP-WORKBENCH-7 Entry：灰度、视觉终审与收口

日期：2026-07-28
阶段：`APP-WORKBENCH-7`
Gate：`PG-AW-H`
来源：`CR-APP-WORKBENCH-001` / 应用工作台体验优化方案 §10.8

## Entry 结论

`PG-AW-G=passed_with_boundary` 已通过，允许进入 APP-WORKBENCH-7。当前只做四应用灰度、可视化验收、恢复/回滚和证据收口；不扩大 Provider 能力、不打开第三方平台、不点击最终发布。

## 本阶段目标

- 对门店营销文案、爆款标题、抖音图文、数字人口播四个工作台完成 1440×900、1280×800、900×760 三个桌面视口的主流程可视化检查，并保留窄窗降级证据；
- 验证 empty、project-selected、input-ready、running、result、editing、handoff、narrow-window 八类状态的页面身份、状态标签、按钮可读性和无错行；
- 验证分应用灰度开关、项目切换/离开后的请求清理、重启恢复投影，以及旧容器回滚不丢失 Artifact/Handoff 事实；
- 复用既有真实 Provider/数字人质量证据，避免因布局终审产生新的付费调用；发布只到发布中心，不执行最终发布。

## Entry 验证

- 前置 Gate：`PG-AW-G=passed_with_boundary`；
- 现有桌面回归：16 files / 104 tests passed；生产 build passed；
- 现有后端核心工作台/应用中心定向回归：62 passed，本轮保留 12 条既有 Pydantic deprecation warnings；
- 已有浏览器 smoke：1280×720 双栏、16px gap、无横向溢出；本阶段扩展为多视口记录；
- 外部边界：Windows 实机、产品负责人签字、真实平台 rollback/WebView SLA 仍由 `PROGRAM-ROLLOUT/PG-L` 管理，不得在本阶段宣称完成。

## 禁止事项

- 不修改数字人图片默认、视频 stable 非默认策略；
- 不调用真实 TTS/RunningHub，除非发现契约回归且先登记受控验证；
- 不打开抖音、快手、视频号、小红书等第三方平台；
- 不自动点击最终发布；
- 不把截图、Hosted Runner 或本机 smoke 当作 Windows 实机验收替代品。

## 放行条件

1. 四应用主流程可视化证据完整，P0/P1=0；
2. 文案、标题、图文和数字人状态/交付动作与 Artifact 事实一致；
3. 窄窗降级不产生横向溢出，disabled/focus/状态不只依赖颜色；
4. 重启恢复不重复创建 Run，回滚 smoke 保留旧容器和数据事实；
5. 独立六维审查 PASS 后，台账回到 `PROGRAM-ROLLOUT/PG-L`。
