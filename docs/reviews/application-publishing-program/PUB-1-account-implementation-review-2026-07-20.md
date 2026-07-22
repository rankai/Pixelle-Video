# PUB-1 strict closure review — 2026-07-20

评审人：独立审查线程 `/root/pg_a_closure_reviewer_v3`

结论：`pass_with_boundary`；PUB-1 范围内 P0/P1 = 0。

## 六维复验

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过边界 | 账号模型、SQLite repository、canonical profile、默认/归档/清理、锁/context registry、状态机、API、真实账号页均已落地；未越界到 PublishRun、selector、最终发布或管理后台 |
| 逻辑正确性 | 通过 | 17 项定向后端测试；非法状态跳转、A/B 隔离、重复 probe 复用、过期/身份变化、活动上下文归档拒绝均有断言 |
| 边界与安全 | 通过边界 | clear-profile 在 retained login_required context 下返回 409，profile marker/context/lock 保留，显式 close 后才清理；API 归档冲突映射 409；projection/raw DB 不包含 Cookie、二维码、凭证或 profile path |
| 代码质量 | 通过 | PUB-1 范围 Ruff、`git diff --check` 通过；锁释放与 runtime shutdown 采用 fail-closed；异常边界已收窄 |
| 测试覆盖 | 通过边界 | 后端 17 passed、前端 5 files/21 tests、desktop build passed；全量 Python 472 collected，一次有界运行 434 passed 后出现全局线程停滞，因此 full regression 保持 `needs_attention` |
| 实际运行 | 通过边界 | In-app Browser 只读 smoke 通过真实 FastAPI/Vite 页面、刷新交互、平台 release state 和无静态“可用”断言；未触发登录/清理/归档/发布动作 |

## 修复清单闭环

初审发现：活动登录窗口可被归档，导致账号从正常列表消失而 context/profile lock 仍存活；已修复为 service 层 fail-closed `PublishAccountConflict`，API 映射 409，并补充归档回归测试。

初审建议：补充 retained login context 的 clear-profile 安全证据；已补充，验证 409、marker/context/lock 保留及显式 close 后成功清理。

## 明确后置边界

既有 `PlaywrightPublishContext.is_logged_in()` 的固定 1500ms 等待与宽泛 URL/文本 heuristic 不作为 PUB-1 真实登录验证依据。平台级 `probe_login_state()`（平台身份元素 + 创作者能力元素 + 条件等待 + challenge/unknown 分支）是 PUB-CORE/PUB-DOUYIN 的硬性 Entry 要求。真实 packaged Tauri app-data、平台过期重登和最终 live 发布也不属于本 Gate。

## Gate 决定

PUB-ACCOUNT/PUB-1 可以标记 `completed` / `PG-E passed_with_boundary`；台账不得因此自动启动 PUB-CORE。下一阶段仍必须由用户按协调方案显式开启，并先读取其 Entry 控制卡。
