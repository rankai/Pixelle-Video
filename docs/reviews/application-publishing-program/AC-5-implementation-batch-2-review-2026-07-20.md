# AC-5 数字人口播 implementation batch 2 独立六维复审（2026-07-20）

状态：`implementation_pass_with_boundary`

评审线程：`/root/pg_a_closure_reviewer_v3`（只读审查，未修改代码）

## 结论

- P0：0
- P1：0（脱敏/路径/artifact key/敏感输入边界已修复并复验）
- 结论：`implementation_pass_with_boundary`
- 允许：继续 AC-5 内下一实施批次；不允许将本批解释为真实数字人、媒体或平台能力通过。

## 六维复验摘要

1. 需求完整性：`/api/app-center/ip-broadcast/runs` create/resume、GET status/reconcile、cancel、retry 路由、schema、错误码和生产 adapter 依赖边界均落地。
2. 逻辑正确性：所有生产创建/执行/重试/完成路径逐请求检查 Registry flag/readiness；status 使用同一 binding/session/AppRun 事实源；跨项目拒绝；幂等 replay 返回同一 run；旧 `/ip-broadcast/sessions/**` 路由未改变。
3. 边界情况：missing binding/session、project mismatch、flag off/not ready、forbidden business field、重复 active、cancel/retry 状态均返回稳定 4xx；非法 retry 状态映射为 `APP_RUN_STATE_INVALID`；敏感 notice message/next_action 进行 secret/path scrub；artifact key 白名单拒绝路径键。
4. 代码质量：路由只做适配与安全投影，复用 AppCenterRepository/IpBroadcastAppAdapter；没有 provider、浏览器、平台 selector、第二配置源或桌面副作用；Ruff/diff clean。
5. 测试覆盖：API 定向 `2 passed`；Stage 相关聚合 `352 passed`、12 个既有弃用警告；覆盖安全响应、重放、跨项目、取消、flag-off、敏感输入与路径/notice 脱敏。
6. 实际运行结果：仅 FastAPI TestClient + 临时 SQLite/session/binding store + local adapter bypass fixture；生产 adapter 仍拒绝 flag/readiness 未就绪；未调用 provider、浏览器、抖音授权/上传或最终发布。

## P2/后续边界

- scrub 规则后续可扩展到更多平台特有绝对路径与裸 token 形态。
- cancel/retry 当前依赖桌面单机 auth boundary，下一阶段可补显式 project/authorization 校验；依赖函数可改为 FastAPI `Depends` 以接入未来账户/组织权限。
- 并发 idempotency、跨进程 binding lock、真实 executor 和最终 ArtifactVersion 继续后置。

## Gate 边界

本结论只关闭 AC-5 implementation batch 2，不关闭 PG-I；下一批仍须按台账实现、测试、证据与独立复审。真实 provider、媒体/可信 file refs、桌面入口和第三方平台动作保持后置。
