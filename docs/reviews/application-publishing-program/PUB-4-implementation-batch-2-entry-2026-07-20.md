# PUB-4 implementation batch 2 Entry（2026-07-20）

状态：`entry_passed_with_boundary`；前置 batch 1 已 `implementation_pass_with_boundary`，PG-J 尚未关闭。

## 本批目标

建立应用产物到统一发布中心的安全 package/run handoff 入口，并提供只读 run timeline 与刷新/离开/重启后的恢复投影。只允许复用既有 PublishPackage/PublishRun/AccountProfile/ArtifactVersion 事实源；不创建真实平台动作。

## 允许范围

- `PublishCenterView` 读取 hash route 中的 `package_id`/`run_id`，调用既有 V2 package、preflight、run、events API。
- package 摘要、preflight 结果、run 状态与事件 timeline 的安全投影；未知/失效/不匹配输入 fail-closed。
- 应用中心 handoff 仅传递 `package_id` 或 `artifact_id`；`run_id` 只允许作为恢复路由引用，不属于应用产物 handoff；不传文件路径、凭证或 session 内容。
- 刷新、离开再返回、桌面进程重启后的同一 package/run 指针恢复测试；旧 V1 fallback 保持可用。
- 定向组件/API 契约测试、desktop build、Ruff、`git diff --check` 和本批证据。

## 禁止范围

- 不创建 PublishRun、不上传、不选择平台、不调用浏览器/抖音/第三方授权、不点击最终发布。
- 不在本批删除旧 `/ip` 的 `PublishWorkspace`；旧重复编排收缩另列 batch 3 Entry。
- 不做破坏性迁移、profile/session 清理、管理员/RBAC/套餐/支付/多租户或第二模型源。
- 不新增第二发布事实源或复制任何 secret/绝对路径。

## 必须验证的负例（机器可读 fixture）

1. 缺失或未知 `package_id`/`run_id` 不显示成功状态。
2. package 与 artifact/account 不匹配时不进入 timeline。
3. invalidated package 不得恢复为新 run。
4. API 错误、事件乱序或重复事件不得伪造 completed/published。
5. handoff 不得包含本地绝对路径、session 内容或凭证字段。
6. flag-off 时不请求 V2 API，旧发布页仍可达。

对应 fixture：`docs/contracts/publishing/fixtures/pub-4-batch-2-entry-fixtures.json`；未知 ref、敏感/未知字段均采用 reject 策略。

## 退出条件

- Entry contract/fixture 与定向测试通过；独立审查线程六维确认 `entry_passed_with_boundary`、P0/P1=0。
- 通过前不修改 batch 2 业务实现；通过后一次只实现本批范围，再交 implementation 复审。
- 本 Entry 不代表 PG-J 完成，也不代表真实平台/provider 或最终发布通过。

## 独立六维复审

审查线程：`/root/pg_a_closure_reviewer_v3`（不修改代码）。

- 需求/契约完整性：通过；应用 handoff 只接收 `package_id`/`artifact_id`，`run_id` 独立作为 recovery route ref。
- 逻辑正确性：通过；preflight/timeline/recovery、失效 package fail-closed、事件单调性与重复/乱序拒绝均已冻结。
- 边界情况：通过；8 个负例 fixture 覆盖缺失/未知 ref、事实不匹配、失效 package、API 读失败、事件顺序、敏感/未知字段和 flag-off。
- 代码质量：通过；fixture/contract 可解析，Ruff 与 `git diff --check` 通过。
- 测试覆盖：通过（有界）；`uv run pytest -q tests/publish_integration_batch_2_entry_contract_test.py` 为 2 passed。
- 实际运行结果：通过（契约/fixture 有界）；未实现业务、未打开浏览器、未执行平台或发布动作。

结论：`entry_passed_with_boundary`，P0=0、P1=0。P2 边界为 batch2 implementation 仍需验证正向 handoff、package/run 一致性和 UI refresh/leave/restart timeline/recovery。
