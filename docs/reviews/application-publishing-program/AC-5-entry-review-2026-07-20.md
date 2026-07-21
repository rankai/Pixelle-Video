# AC-5 数字人口播应用化 Entry 独立六维复审（2026-07-20）

状态：`entry_passed_with_boundary`

评审人：独立严格审查线程 `/root/pg_a_closure_reviewer_v3`（只读审查，未修改代码）。

## 六维结论

1. 需求完整性：Entry 已冻结 `IpBroadcastAppAdapter` 目标、空白/文案/标题三来源、旧 session 恢复、session/task/AppRun 映射、video/cover/publish_copy ArtifactVersion、幂等/取消/重试/重启和 `digitalHumanInAppCenter` flag-off。
2. 逻辑正确性：source exactly-one、ArtifactVersion project/type/ID、copywriting variant/title 选择、legacy session 显式认领与跨项目拒绝、waiting 状态非终态、重复 active run 幂等重放均有明确规则。
3. 边界情况：`waiting_for_login`、`waiting_for_human`、`needs_attention`、IP-learning 选题确认不会映射为 completed；绝对路径、symlink 越界、空标题、混合来源、跨项目恢复和无绑定 legacy session 均有负例。
4. 代码/所有权：Entry 仅新增契约/fixture/测试/文档；未新增 `IpBroadcastAppAdapter`、业务 executor，未修改既有 `IpBroadcastWorkflow`、PublishRun、平台 selector、模型配置源或旧 StudioApp 入口。
5. 测试覆盖：既有口播/数字人基线 242 passed；AC-5 Entry contract/fixture 4 passed；聚合 **246 passed**；Ruff、`git diff --check` 通过。
6. 实际运行结果：基线仅执行既有本地 API/workflow/状态/渲染/安全/UI confirmation 与契约 fixture；未触发真实 provider、第三方授权、抖音上传或最终发布。契约证据不等价 adapter 业务已完成。

## 问题清单

- P0：0。
- P1：0。
- P2/实现阶段边界：真实 legacy session 恢复与 project binding 写入、AppRun/Task/Artifact 实际 adapter E2E、真实 provider/媒体产物、桌面新入口、连续灰度一个发布周期均留在 AC-5 implementation/PG-I；Entry fixture 使用脱敏声明数据，不替代运行时证据。

## 放行与禁止

`APP-IPB/AC-5 Entry` 以 `entry_passed_with_boundary` 放行进入同一 Stage 的 implementation。实现阶段必须保持 `digitalHumanInAppCenter` 默认关闭，先接入本地 fake/隔离 workflow 与旧回归；不得跳入 PUB-4、真实抖音动作、管理员/RBAC/套餐/支付或第二模型配置源。
