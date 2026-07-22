# ADR-011：浏览器运行时策略与 EgoLite 评估边界

- 状态：`accepted with ADR-012 refinement`
- 日期：2026-07-19
- 范围：应用中心与桌面自动发布 Program；不改变当前 COORD-0 的运行时实现
- 相关契约：`pixelle_video/services/publish/browser_runtime.py`、`ADR-PublishRunStateMachine.md`、`ADR-PlatformAdapterEvidence.md`

## 背景

当前项目已经使用 `PlaywrightBrowserRuntime` 完成可见 Chromium、持久化 profile、抖音字段/封面 smoke、首次扫码证据、截图哈希和发布前安全停住。项目的发布领域通过 `BrowserRuntime` 注入运行时，已有测试、证据文件和回归命令均以 Playwright 为基线。

EgoLite 官方页面描述了一个基于 Chromium 的 agent browser 和 `ego-browser` 连接层，提供 Space、语义 snapshot、`@N` 引用、在页面内组合多个动作，以及继承 Chrome cookies/登录态等能力；官网同时声称其任务速度和 token 消耗优于部分 browser automation 工具。这些是供应方声明，尚未在 Pixelle Video 或抖音场景中独立复现。参考：[EgoLite 官方页面](https://lite.ego.app/)、[官方文档入口](https://lite.ego.app/document/en)。

## 决策

### 当前 Program：保留 Playwright 为规范运行时

1. `PlaywrightBrowserRuntime` 继续作为当前发布链路、契约测试、可复现证据和 CI/本地回归的规范实现。
2. 不直接照搬 `ego-browser` skill，不把 EgoLite 安装、CLI、Space 或其账号迁移机制加入当前 P0 依赖，不修改 `package.json`、lockfile、发布 selector 或 `BrowserRuntime` 生产默认值。
3. 当前已通过的 Playwright 首次扫码和发布基线证据继续有效；不得为了比较 EgoLite 而重复扫码、重复上传或点击最终发布。

### 未来：允许受控的 EgoLite 手动适配 spike

在 PG-A 通过后，或由 Change Request 明确授权，可新增一个仅用于真实平台人工 smoke/探索的 `EgoLiteManualRuntime` 适配器。它必须通过统一的 `BrowserRuntime`/证据边界，不得成为第二套发布事实源。

2026-07-21 对 `oil-oil/video-publisher-skill` 的复核补充了一个更重要的约束：无论底层是 Playwright 还是 Ego Lite，生产执行都必须先满足有状态的 `inspect → upload → wait → mutate → verify` 协议、稳定草稿身份、指纹绑定 checkpoint 和 typed blocker。详见 `docs/adr/012-stateful-publishing-executor-reference-review.md`。因此，Ego Lite 可以在该协议下做受控 runtime spike，但不能用“换浏览器”替代发布执行器的状态化重构。

通过以下门槛前，EgoLite 只能是人工探索工具，不能成为生产发布运行时：

| 门槛 | 必须证明 |
| --- | --- |
| 身份隔离 | 能创建不继承现有 Chrome cookies/账号的干净 Space/profile，并能映射到 `PublishAccount.profile_ref`；Space 隔离不能仅凭供应方描述推断 |
| 并发与锁 | 能与 `PublishRun` 的 account/profile lock、attempt 和 `needs_attention` 状态一致工作 |
| 可复现动作 | 能稳定完成 navigate、snapshot、fill、文件上传、截图和等待人工动作，并输出可哈希的事件 JSON；不能只依赖自然语言成功描述 |
| 恢复语义 | 关闭/重开后能回到同一 run/checkpoint，或明确进入 `needs_attention`；不能静默新建第二次上传 |
| 安全边界 | 到达最终发布时仍由 `FinalActionGuard` 停在 `waiting_for_human`，EgoLite 不能绕过人工确认 |
| 证据与隐私 | 能导出脱敏截图/录像，且不把 cookies、token、密码、二维码原图或账号标识写入仓库 |
| 降级与维护 | EgoLite 不可用时可无损回退 Playwright；版本、安装、许可证、macOS/Windows 支持和本地数据策略可被锁定和审计 |

## 为什么不直接替换

- EgoLite 的语义引用和页面内批量动作可能降低 selector 脆弱性和交互往返，但这属于待验证的效率收益，不能替代当前已有的可重放证据。
- “继承 Chrome 登录态”对日常操作有价值，却与首次扫码要求的干净 profile 相冲突；Space 不能自动等价于新账号或新授权证据。
- 当前项目已有 Playwright 的上传、截图、视频和持久化 profile 证据链。立即替换会引入新的安装、权限、数据迁移和证据格式风险，并让已通过的基线失去可比性。

## 影响与回滚

- 当前无需代码、依赖、配置或数据库变更；现有发布行为和 Gate 不变。
- 若未来 spike 未通过，删除适配器和该 Change Request 即可回退到 `PlaywrightBrowserRuntime`，不影响 PublishPackage、PublishRun 或现有 profile。
- 若未来 spike 通过，仍需单独 ADR/Change Request 批准生产默认值、平台证据策略、数据迁移和回滚，不得由 Luna 在当前 Stage 自行切换。
