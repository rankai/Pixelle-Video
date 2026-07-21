# PUB-CORE / PUB-2 Independent Six-Dimension Review

状态：`implementation_pass_with_boundary`

评审线程：`/root/pg_a_closure_reviewer_v3`

## Verdict

- P0：0
- P1：0
- 结论：`PUB-2 implementation_pass_with_boundary`
- 允许：写入实施证据、更新 PG-F、进入下一 Stage Entry

## 六维复验

1. 需求完整性：覆盖 package/source/fingerprint、媒体预检与 reverify、run/step/event、CAS、幂等、恢复、取消/resume、Generic Task、V2 capability/origin/flag 和 V1 回退；没有引入平台 selector 或最终发布。
2. 逻辑正确性：nested `human_confirmation`、稳定 fingerprint、queued-first、事件 state/version、retry attempt 递增与终态 CAS、同账号/平台串行均已验证。
3. 边界情况：缺失/无效媒体、hash 变化、同根 symlink、旧库 guard/index、失效包、隐藏 path、错误 origin/capability、login required、executor 异常和人工放弃均 fail-closed。
4. 代码质量：发布域 Ruff clean；repository/service 职责分离；Generic Task 不复制 request/result/path/凭证；Profile lock 生命周期有明确释放路径。
5. 测试覆盖：独立审查定向与增量复验通过；主线程汇总 `99 passed`；协调/AppCenter 回归、API capability/origin、V2 disabled、V2 account route/OpenAPI parity、stable account errors、retry/restart/profile lock 均有测试；既有 Pydantic deprecation warnings 未新增为 Gate 阻塞。
6. 实际运行结果：独立命令在临时数据根目录通过；API TestClient 验证 202 run、幂等 replay、事件读取、媒体变更 `MEDIA_HASH_MISMATCH`、未知 run 404；Ruff/diff clean。

## 后续边界（不阻塞 PG-F）

- 真实 ffprobe/codec/duration 与平台媒体能力校验留 PUB-3/PUB-DOUYIN。
- legacy session 受信 resolver 当前按边界返回 422，需后续单独 Entry/适配器设计。
- 底层 Artifact NotFound 的更细稳定错误映射、旧索引历史兼容清理、Pydantic deprecation 属 P2 硬化。
- 无真实平台 selector、登录探针、上传或最终发布结论。

## 增量复验（最终）

- 封面引用与 manifest 强制 0/1 对称，重复封面拒绝为 `MULTIPLE_COVER_ARTIFACTS`。
- from-session snapshot 与 `PublishPackageFromSessionRequest` runtime schema 的 required/properties 已 parity。
- `/api/publish/v2/accounts*` 路由、capability guard、V2 publishing DB 同源 service、`ACCOUNT_NOT_FOUND`/`ACCOUNT_PLATFORM_MISMATCH` 已验证。
- `connect/verify/open` 明确为 HTTP 200 同步 bounded probe projection；代码 operationId、runtime route metadata、OpenAPI snapshot 和方案描述一致。
- 最终结论维持：`PG-F passed_with_boundary`；P0=0、P1=0。P2/边界为 trusted legacy resolver、真实平台/媒体能力和既有 Pydantic warnings。
