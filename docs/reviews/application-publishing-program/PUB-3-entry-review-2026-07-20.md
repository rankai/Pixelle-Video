# PUB-DOUYIN / PUB-3 Entry Review

状态：`entry_passed_with_boundary`

## 前置与目标

- 前置 Gate：`PG-F passed_with_boundary`。
- 当前 Stage：`PUB-DOUYIN`；本文件只负责 Entry 冻结，不代表抖音 Adapter 已实现或真实平台已通过。
- 目标：冻结抖音平台 adapter 的 capability、页面指纹、字段动作边界、异常停手状态和证据要求，为下一批受控实现提供唯一入口。

## 允许范围

- `pixelle_video/services/publish/platforms/**` 的抖音 adapter/base 最小改动；必要的浏览器 runtime 兼容改动。
- `docs/contracts/publishing/**`、抖音脱敏 DOM fixture/manifest、Entry/adapter 测试和 QA 证据。
- 继续复用 PublishPackage V2、PublishRun、AccountProfile、FinalActionGuard 和现有本地模型配置事实源。

## 禁止范围与暂停点

- 不修改 App Center、全局导航、PublishRun 核心事实源、账号 schema 或第二浏览器运行时；不新增平台。
- 不自动点击最终发布，不提供 final-publish API，不把旧 V1 `available` 文案当作平台通过。
- 真实扫码、第三方授权、验证码/挑战、真实上传、平台页面写入和最终人工发布必须暂停并通知用户；Entry 仅使用本地 fixture、脱敏 DOM/事件回读和静态/模拟 runtime。

## Entry 冻结项

1. 平台标识为 `douyin`，adapter/version、creator URL 和页面 fingerprint 必须随证据登记。
2. 脱敏 fixture 覆盖 signed-in、signed-out、captcha、loading、network error、upload entry/progress、processing、editor fields、cover modal/error、waiting-for-human、unknown 共 13 个状态；manifest SHA 与关键 marker 必须可复验。
3. 允许动作仅为 `upload_media`、`fill_title`、`fill_description`、`select_topic`、`save_cover`，每项必须有页面 fingerprint 和语义回读；禁止 `publish`、`confirm_publish`、`submit`、`unknown`、坐标/nth click。
4. 安全停手映射：登录过期/未登录 → `waiting_for_login`；captcha/challenge → `waiting_for_human`；unknown、network error、页面变化、窗口关闭 → `needs_attention`；任何未知 DOM 不得继续写入。
5. 视频/封面进入平台前继续经过 PublishPackage 的可信路径、hash/size reverify；真实 codec/duration/platform capability 是本 Stage 实现与 PG-G 证据，不在 Entry 中虚构通过。
6. 自动化终点只能是 `waiting_for_human`；最终发布动作必须由 FinalActionGuard 拒绝并保留可审计事件。

## Entry 验收与证据

| 验收项 | 当前证据 | 状态 |
| --- | --- | --- |
| fixture manifest、SHA、隐私和 marker | `tests/fixtures/publishing/manifest.json` + `tests/publish_douyin_entry_contract_test.py` | `passed` |
| FinalActionGuard allow/deny matrix | `docs/contracts/publishing/final-action-guard.matrix.json` + contract tests | `passed` |
| adapter platform/version/creator URL registration | existing adapter/runtime + Entry test | `passed_with_boundary` |
| login/challenge/unknown/window-close fail-closed matrix | Entry matrix test/fixture; no live browser | `passed_with_boundary` |
| 字段逐项回读契约（视频、标题、描述、话题、封面） | Entry action matrix; live evidence deferred | `passed_with_boundary` |
| 独立六维审查 | `/root/pg_a_closure_reviewer_v3` | `passed_with_boundary` |

## Entry 放行条件

- Entry tests、fixture integrity、Guard matrix、adapter registration 和失败映射通过；P0/P1=0。
- 明确真实平台动作暂停点，且没有任何 Entry 测试触发扫码、第三方授权、上传或最终发布。
- 本文件已被独立审查标记 `entry_passed_with_boundary`，允许进入 PUB-3 adapter implementation；PG-G 仍需真实逐字段回读和异常停手证据，不能由 Entry 代替。
