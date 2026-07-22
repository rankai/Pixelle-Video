# PROGRAM-ROLLOUT / AC-6 + PUB-7D Entry（2026-07-21）

状态：`entry_passed_with_boundary`。Entry contract/fixture 2 passed，独立 Entry 六维复审 P0/P1=0；PUB-5/PG-K 已 `passed_with_boundary`；本 Entry 是 P0 正式放行前最后一阶段的唯一启动入口。

## 本 Entry 目标

冻结工作台正式启用、遥测/诊断、打包、灰度、性能、隐私和双向回滚的共同验收边界。AC-6 负责把已通过 Gate 的应用中心与发布中心接入工作台；PUB-7D 只对抖音执行灰度门禁，不自动放行快手、视频号或小红书。

## 允许范围

- `desktop/src/StudioApp.tsx`、AppShell、应用中心和发布中心的最终入口/旧入口回退接线；
- 按上位契约冻结 canonical flags：前端 `VITE_APP_CENTER_SHELL`、`VITE_CONTENT_PROJECTS`、`VITE_CONTENT_APPS`、`VITE_DOUYIN_CAROUSEL`、`VITE_APP_CENTER_DIGITAL_HUMAN`、`VITE_APP_CENTER_NEW_NAV`、`VITE_PUBLISH_CENTER_V2`、`VITE_ASSET_CENTER_V2`/`VITE_ASSET_CENTER_SMB_UX`；后端 `PIXELLE_APP_CENTER_CONTENT_APPS`、`PIXELLE_APP_CENTER_DOUYIN_CAROUSEL`、`PIXELLE_APP_CENTER_DIGITAL_HUMAN`、`PIXELLE_ASSET_CENTER_V2`、`PIXELLE_PUBLISH_V2_ENABLED` 和平台 flags。`VITE_DIGITAL_HUMAN_IN_APP_CENTER`、`VITE_PUBLISH_V2_ENABLED` 只能按显式 alias policy 在构建前归一化，未知/冲突组合必须 fail-closed；
- 脱敏本地 telemetry、诊断包预览/导出边界和错误状态文案；
- macOS 当前构建/启动/停止、sidecar health、数据目录和迁移 dry-run；
- 10 次应用/sidecar 重启、10 次连续本地 bounded run、profile lock soak、1/15/60 秒 fixture 性能口径；
- 空路由/死路检查、100 projects/1000 artifacts 有界规模检查；Windows 构建若当前环境无法执行必须明确登记 deferred，不得默认通过；产品负责人 P0 sign-off 必须留证；
- V2→V1 以及 V1→V2 双向 rollback smoke；不删除 V2 数据、profile 或历史 run；
- QA JSON、构建日志、性能摘要、隐私扫描、回滚证据和独立六维复审。

## 禁止范围

- 不执行抖音最终发布，不把 `waiting_for_human` 变成 `published`；
- 不新增快手/视频号/小红书 adapter，不改变这些平台 release state；
- 不引入管理员/RBAC/套餐/支付/远程上下架或第二模型事实源；
- 不删除旧 `/ip`、V1 代码、浏览器 profile、session、PublishRun 数据；
- 不做不可逆迁移、生产云端部署、第三方授权或需要用户扫码的动作；
- 不用本地 fixture 冒充真实平台发布或连续生产灰度。

## 必须冻结的证据

1. P0/P1 gate 状态、平台 release state 和各 feature flag；
2. 本地构建/启动/停止/端口释放与 sidecar 重启后登录/profile/run 复用；
3. 10× app/sidecar restart、10× bounded run、至少 2 次 crash recovery、2 次 profile-lock contention；每周期都有 health、port release、run reconcile、external_actions=0；
4. 1/15/60 秒媒体各至少 10 个样本，记录 p50/p95 及 create-run/account-list/UI-state/media-preflight 等本地阈值，并拆分 local overhead/platform wait；
5. 诊断与 telemetry 仅允许 platform、adapter_version、step、error_code、duration_bucket、app_version；不得含 api key、authorization、cookie、QR、账号 ID/昵称、profile path、signed URL、完整 query、标题、描述、媒体内容或绝对路径；默认 local-only、无上传、无 raw screenshot，导出前有 preview；
6. V2→V1→V2 双向 rollback：旧入口/复制下载可用，历史和 active/waiting run 可读，profile 保留，upload_count_delta=0，external_actions=0；
7. 抖音灰度必须有 `release_state=gray`、cohort/account scope、rollout percentage 和 `PG-L + 产品负责人签字 + 观察窗口` 的 default-on 触发条件；Entry 阶段 default-on 禁止；快手/视频号/小红书 release state 保持 immutable；
8. 至少 1 个版本、1 小时、20 个 bounded run 的稳定观察窗口，定义 P0/P1、重复上传、误点发布、profile 损坏等 rollback trigger，并由产品负责人签署。

## 退出条件

- Entry contract/fixture 和独立 Entry 六维复审通过；
- AC-6/PUB-7D 实现、定向测试、构建、性能/隐私/回滚证据齐全；
- 独立严格复审确认 `implementation_pass_with_boundary`、P0/P1=0；
- 产品正式放行前保留至少一个稳定观察窗口；只有全部满足后才能关闭 PG-L。
- 上游 PG-A…PG-K 全部处于 `passed` 或 `passed_with_boundary`，不能只检查 PG-K 名称。

## 运行暂停点

真实扫码、第三方授权、平台挑战、最终发布、破坏性清理、重大架构变更或外部云服务不可用时暂停并记录，不用重试掩盖边界。
