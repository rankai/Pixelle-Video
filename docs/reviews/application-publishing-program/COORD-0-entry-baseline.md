# COORD-0 Entry Baseline and Controlled Revision Record

- 日期：2026-07-19
- Program Stage：`COORD-0`
- 当前结论：`in_progress / PG-A evidence review`
- Entry 期间入口事实：`current_stage: COORD-0`；当前实时事实已由 PG-A 交接更新为 `current_stage: APP-SHELL`，以实时台账为准
- 允许范围：AC-0 + PUB-0 的契约、ADR、fixture、基线、迁移 dry-run、回滚设计和审查证据
- 禁止范围：PG-A 前的应用业务 UI、真实 App Executor、发布账号 UI、平台 selector、浏览器自动化、生产数据库和后续 Stage

## 1. Entry 原始 Git 快照（2026-07-19 启动时）

```text
branch: codex/two-day-refactor-batches
HEAD: aee737e docs: add refactor gates and desktop evidence
```

Entry 时已有且保留的受控规划改动范围：

```text
 M docs/reviews/2026-07-18-desktop-auto-publishing-refactor-implementation-plan.md
 M docs/superpowers/specs/2026-07-18-application-center-product-architecture-implementation-plan.md
?? docs/adr/007-fastapi-current-and-saas-hybrid-architecture.md
?? docs/reviews/2026-07-18-application-center-publishing-program-progress.md
?? docs/superpowers/specs/2026-07-18-application-center-publishing-program-master-plan.md
```

Entry 原始规划快照 SHA-256（用于重现入口，不代表后续受控修订）：

| 文件 | Entry SHA-256 |
| --- | --- |
| master plan | `7b051491b32ef99475b8394a860c4e51a4b4f585fcc887411de98ffa155fe12d` |
| application-center plan | `245860968f62cdfc6081a6310f943f4154b999be0b938d00b42baf20a884ce6f` |
| publishing V2 plan | `17e1c5afa41355ba98512adefffa713378ae04fe5549d6078e2d8e8f28158979` |
| ADR-007 | `934f26c186f30430c9de1d01540e9cd03c0fc57ddc8116b6dceadababb62365e` |
| progress ledger | `e4447f612465c43b439d58aaf43bbe9a9728e56ccb5d6b2bb666d54bd0ef354b` |

## 2. COORD-0 受控修订快照（2026-07-19，当前）

修订范围包含五份上位/领域方案的受控文档修订，以及新增 `docs/adr/008-015*`、五份 Publish ADR、`docs/contracts/**`、`docs/migrations/publish-v2-profile-migration.md`、本台账/证据和 `tests/coord0_contract_test.py`；未修改业务代码、`package.json`、lockfile、生产数据库或现有 feature flag 默认值。

| 文件 | 当前 SHA-256 |
| --- | --- |
| master plan | `dda400dce32badf879a5063c7071b2b50df1deae107a25dbe07e3801c038ef45` |
| application-center plan | `7fd72ea91beae346ede617ad5840a09db44bbad95736fd258923cc020ca33747` |
| publishing V2 plan | `f09170a63fdcfd7b0e6ca7d808f635b92f25995a91516ffbffa66e5ea06c2e06` |
| ADR-007 | `934f26c186f30430c9de1d01540e9cd03c0fc57ddc8116b6dceadababb62365e` |
| progress ledger | `894a229cdfd92556f167f14f28e2fe868d24b971466c58feecfaa0f59aca8f65` |

当前受控快照命令输出（新增文件均为本阶段受控 untracked 文件，未覆盖用户改动）：

```text
 M docs/reviews/2026-07-18-desktop-auto-publishing-refactor-implementation-plan.md
 M docs/superpowers/specs/2026-07-18-application-center-product-architecture-implementation-plan.md
?? docs/adr/007-fastapi-current-and-saas-hybrid-architecture.md
?? docs/adr/008-application-center-domain-boundaries.md
?? docs/adr/009-application-center-sqlite-storage.md
?? docs/adr/010-desktop-app-shell-hash-router.md
?? docs/adr/ADR-PlatformAdapterEvidence.md
?? docs/adr/ADR-PublishAccountProfile.md
?? docs/adr/ADR-PublishPackageV2.md
?? docs/adr/ADR-PublishRunStateMachine.md
?? docs/adr/ADR-PublishV2-Boundaries.md
?? docs/contracts/app-center/
?? docs/contracts/coordination/
?? docs/contracts/publishing/
?? docs/migrations/publish-v2-profile-migration.md
?? docs/reviews/2026-07-18-application-center-publishing-program-progress.md
?? docs/reviews/application-publishing-program/
?? docs/superpowers/specs/2026-07-18-application-center-publishing-program-master-plan.md
?? tests/coord0_contract_test.py
```

`git diff --stat`（仅已跟踪文件）：

```text
 docs/reviews/2026-07-18-desktop-auto-publishing-refactor-implementation-plan.md | 27 ++-
 docs/superpowers/specs/2026-07-18-application-center-product-architecture-implementation-plan.md | 232 +++++++++++++++++----
 2 files changed, 210 insertions(+), 49 deletions(-)
```

本次追加修订：2026-07-19，台账同步 16/383、AC-0 input/output/state/error/flag、媒体 generator、迁移版本保护和外部 baseline 状态；因此 ledger SHA 更新为上表 `e7ef481b...`。后续任何受控修订必须追加时间、文件范围和新 SHA，不得改写 Entry 快照。

本次追加修订：2026-07-19，记录抖音登录/上传基线；登录与上传路由已确认，原生文件选择器无法提交测试视频，未上传、未发布，PG-A 继续 `in_progress / blocked_external_manual`；因此 ledger SHA 更新为上表 `8dc9edb1...`。

本次追加修订：2026-07-19，按独立审查意见收窄抖音证据措辞为“上传入口可见、未出现登录提示（认证仅部分可见）”，并登记下一次手动接管必须补时间、意图动作数和截图哈希；因此 ledger SHA 更新为上表 `ea047bbf...`。

本次追加修订：2026-07-19，复用既有 Playwright 持久化 profile 完成一次 `set_input_files()`，有效 MP4 进入抖音视频编辑器；未发布；任务 5 标记 `passed`，九项基线和 PG-A 仍未完成；因此 ledger SHA 更新为上表 `d93b9bdd...`。

本次追加修订：2026-07-19，按独立审查意见将描述/话题措辞收敛为“控件可见但未找到安全可回填语义/selector”，并将任务级 automation_ms 留空、在 notes 记录综合耗时；因此 ledger SHA 更新为上表 `c055387b...`。

本次追加修订：2026-07-19，复用同一既有 Playwright profile 完成一次关闭持久化上下文后重开探针；两次登录探针均为 true，任务 2 标记 passed；任务 1、3、4、8、9 及字段/封面未完成项保持阻断；当前台账 SHA 为 `c417a3a67bfd42431c70e35f58f1b39189904fec0f5fad55ad1db71f0ceb084d`，待独立审查线程复验。

本次追加修订：2026-07-19，补齐任务 2 的重开后脱敏 QA 截图、截图 SHA 和 context-open/close 事件摘要；未增加上传或发布动作；当前台账 SHA 为 `19db26fa66fa458d628c4471373245d5a78f3d88222bad9ed87bb8ca60943883`，待独立审查线程复验。

本次追加修订：2026-07-19，按严格审查意见补齐同一运行中的 `first_context_closed → reopen_context_opened → reopen_context_probe_and_screenshot → reopen_context_closed` 事件闭环，并更新脱敏截图 SHA；未增加上传或发布动作；当前台账 SHA 为 `ac63bd9b82c246b6bed2249d92e378b59c4fbda288f8766a3c58059476b604a2`，待独立审查线程复验。

本次追加修订：2026-07-19，执行一次有明确目的的中途关闭/恢复基线：有效 MP4 进入编辑器后关闭上下文，同一 profile 重开回到上传页，任务 8 记录 failed；未填写字段、未发布；当前台账 SHA 为 `5c314075a31c0f43ce582eec7dec5588a65ff3a9bcd950ae07cfac9b8c1fae5e`，待独立审查线程复验。

本次追加修订：2026-07-19，补采 AC-0 浏览器开发模式页面基线：工作台、口播、资产、发布、任务五页只读导航，记录截图 SHA、点击数、自动化耗时和控制台错误；核心任务录像及 Tauri/sidecar 重启仍缺；当前台账 SHA 为 `bd017629d917d7a6eb7455c685523b7c49707c4028824a819f12991ba62d79ac`，待独立审查线程复验。

本次追加修订：2026-07-19，依据 FastAPI 运行日志补充页面初始化副作用：`recoverAppState()` 自动 POST 创建本地 IP 口播 session；未删除 session 文件，不再声称页面采集完全无副作用；当前台账 SHA 为 `7c386aa28a7cb42618d39242e0d1a9fe98ada44779887f86e6afdbd806a1b7e5`，待独立审查线程复验。

本次追加修订：2026-07-19，将页面初始化自动创建 session 的 legacy 副作用登记为风险 R-012，明确由后续 AC-1/AC-2 处理，COORD-0 不改业务代码；当前台账 SHA 为 `b023499f6bcbbba7af868ece07b4cf3f6da402c5d6dbec4624d80cb0a171da37`，待独立审查线程复验。

本次追加修订：2026-07-19，补充 Tauri/sidecar 重启证据：Tauri CLI 因环境缺少 cargo/rustc 未启动；已构建 sidecar 在仓库根目录和 Tauri debug 等价环境变量下两次 health/停止/端口释放通过；任务 3 保持未完整通过；当前台账 SHA 为 `55bfdb68b8f018ec826bd4ac59fb2031db78d0275a20b7ec9d39fe5148d130f1`，待独立审查线程复验。

本次追加修订：2026-07-19，补采 AC-0 只读核心入口导航录像并通过 `ffprobe` 完整性校验；同步台账中真实生产任务录像仍缺的边界和下一步无效媒体/字段封面 live smoke；当前台账 SHA 为 `cee74cc94ac6d84aebf78b2e24bf81fa1e92cbfb6180e0e92ee5a3060befc0b5`，待独立审查线程复验。

本次追加修订：2026-07-19，补齐一次本地无效媒体拒绝和一次抖音字段/话题/竖封面保存 live smoke；任务 4、6、7、9 更新为通过，但仍保留首次扫码、Tauri 联合重启、横版封面建议和中途恢复边界；当前台账 SHA 为 `0fcea4e41cdb24e56755e3efc8d83eb79d58664b6e9b31c3a067d869da897a26`，待独立审查线程复验。

本次追加修订：2026-07-19，补录口播剪辑文案→配音→出镜→成片→发布五步流程的安全导航录像；未执行自动继续、生成或发布；当前台账 SHA 为 `615c1f235dcba9a7d959de5dc1bd6bfe5d61e75034a1c05fadc62fa07bc413db`，待独立审查线程复验。

本次追加修订：2026-07-19，按严格审查意见闭合字段/封面证据隐私 P1：截图裁掉账号/右侧预览，JSON 中第三方 `sign_token` 替换为 `REDACTED`；脱敏截图 SHA `b5d8567545948c438bd8e90a7b2f32eb7911e6157794ff79b72da9a4ee97c73d`，脱敏 JSON SHA `c56e59c8305d28fe14e31e49cdf130c38e26ea4f9af7d22c6deb5c48b38acf5f`；当前台账 SHA 为 `e695c3556a8588d9350b4188a5b96d5dbc334b3655cd4e2ddd68aa276fea2ce9`，待严格审查线程复验。

本次追加修订：2026-07-19，显式加入 `~/.cargo/bin` 后补齐真实 Tauri 本体/sidecar 两轮启动、health、停止、端口释放和重启后既有抖音 profile 登录探针；任务 3 更新为 passed，首次扫码任务 1 仍保持未声称完成；当前台账 SHA 为 `b4e65239e5f7df908c915c61436b2a8670052d85781019b8efbf0a89473cfd84`，待严格审查线程复验。

本次追加修订：2026-07-19，补录一次真实成片任务录像：预填既有有效音频/数字人视频，在桌面工作台点击“一键成片”，TaskManager 任务完成并生成最终视频、封面、脚本和发布包 JSON；录像停在发布前安全边界，未点击抖音最终发布。该证据标记为 `passed_with_boundary`，明确不等价于全新 LLM/TTS/数字人 provider 生成；当前台账 SHA 为 `651c9bfa202e0c327dd73afb4a71ada5cd79a82fa870928e242ec215caaa5628`，待严格审查线程复验。

本次追加修订：2026-07-19，按严格审查意见将旧 `COORD-0-current-app-baseline.md` 明确标记为历史只读导航快照，增加实时证据指针；补齐完整 Task API payload 归档并完成脱敏检查。当前台账 SHA 为 `25aaee362e09d913b07429a68301b2f1210f2062cf47ada05ab4a80c359da2ef`，严格审查确认新增证据可接受，PG-A 仍保持阻断。

本次追加修订：2026-07-19，修正当前 Gate 结论、当前发布基线和 Entry 风险措辞：真实成片任务明确为 `passed_with_boundary`，剩余阻断限定为首次扫码/新 profile、任务 8 恢复、全新 provider 生成和真实平台发布；严格审查二次复验已完成，PG-A 仍为 `in_progress`。当前台账 SHA 为 `52546666f153e4638dd5db50957f935cf2190bcb484e7c3370ce505ceca4bc85`。

本次追加修订：2026-07-19，删除台账 Gate 结论中的旧自引用 SHA，改为“以本文件当前 SHA 为准”，避免更新台账时产生过期哈希；当前台账 SHA 为 `4ce32aa1a5a65f76c17211fe20ade4156830f143368cf56107a4ed5019493149`。

本次追加修订：2026-07-19，固化首次扫码隔离 QA profile 的人工交接协议（只扫码一次、重开探针、脱敏截图/事件字段）以及任务 8 失败到 PUB-2 的恢复状态机交接用例；未触碰已授权 profile、业务代码或平台 selector；当前台账 SHA 为 `4358d3f6e9a4c6fd273e51cb1b12a8bf0d0e7b2d7cfd60b14fcc058f73cc2d88`，待严格审查线程复验。

本次追加修订：2026-07-19，将 COORD-0 的 `current_stage_status` 明确切换为 `waiting_user`：唯一待用户动作是隔离 QA profile 的首次扫码；`gate_status` 仍为 `PG-A/in_progress`，不放行业务实现；当前台账 SHA 为 `68d3e187a4e10c83c3373a09ea11190f4445f8721ec7563ffb0e01bac3350224`，待严格审查线程复验。

本次追加修订：2026-07-19，修正台账元数据摘要中残留的 `in_progress`，使头部、总览表、Stage 控制卡和元数据行统一为 `waiting_user`；`gate_status` 仍为 `PG-A/in_progress`；当前台账 SHA 为 `d1cb0e158d36631f5b5d50d60771105d433cd2c0f005c4074db5991104658f81`，待严格审查线程复验。

本次追加修订：2026-07-19，完成一次隔离 QA profile 的首次扫码等待尝试：二维码和未登录探针可见，180 秒内未发生用户扫码，临时 profile 清理，未上传/发布/记录敏感数据；结果记为 `blocked_external_manual`，台账保持 `waiting_user`/`PG-A=in_progress`；当前台账 SHA 为 `524ea83fd6225affb3d3828117e75ee87109bc1e3d9b72b1888a940f51f2665a`，待严格审查线程复验。

本次追加修订：2026-07-19，按审查建议为首次扫码超时证据补充等待上限、超时点与清理完成点，区分用户等待时长和临时 profile 清理耗时；未新增浏览器动作；当前台账 SHA 为 `7f6041cf8e49d4718cc77094674805ab3579e786678d30e974024a48e86ba260`，待严格审查线程复验。

本次追加修订：2026-07-19，运行全量 Python 回归：`uv run pytest -q` 结果为 383 passed、12 个既有 Pydantic V2 弃用警告；无新增失败，首次扫码和 PG-A 状态不变；当前台账 SHA 为 `59d4a58e7e98dca76366144c2e4ce3fc76aae8f91dab51ba31b312d98e1a043a`，待严格审查线程复验。

本次追加修订：2026-07-19，用户在全新隔离 QA profile 中完成一次真实首次扫码；登录后与同 profile 重开探针均通过，三张脱敏截图哈希已归档，未上传/发布；任务 1 更新为 passed，台账恢复 `COORD-0/in_progress`，`PG-A` 仍 `in_progress`；当前台账 SHA 为 `4f183d4bb12338a62604d0a619a62a744488d6d359c112b27fb07eb2f3d282a9`，待严格审查线程复验。

本次追加修订：2026-07-19，同步更新 R-011 风险登记，将任务 1 首次扫码标记为已有证据，保留任务 8/全新 provider/横版封面/最终发布的后续风险；当前台账 SHA 为 `5ba343918b2f9cd01682cfd4f925652cbf77004d5a7d5f0aa572fb3e061458f4`，待严格审查线程复验。

本次追加修订：2026-07-19，将首次扫码连接证据单独加入 COORD-0 测试计划，并在 Gate 结论中明确任务 8/全新 provider/最终人工发布仍未完成；当前台账 SHA 为 `9090a55e3cde95a078d5f32882e69eda267cef06aceb04d7f09ef7039a5cdfba`，待严格审查线程复验。

本次追加修订：2026-07-19，修正首次扫码证据 JSON 的归档截图文件名，并补充 JSON SHA `02c6c5b4…`；截图哈希自动校验通过，未改变扫码事实或安全边界；当前台账 SHA 为 `9cb0d53959d1d341d158082879c90f3c9d2a89e5390bb89de008d573d67b8585`，待严格审查线程复验。

本次追加修订：2026-07-19，收敛首次扫码通过后的权威发布 fixture、当前发布基线、历史导航指针和运行证据入口，并修正台账元数据残留的 `waiting_user`；任务 1 维持 passed，`COORD-0/in_progress`、`PG-A/in_progress`；当前台账 SHA 为 `6490bb7291676d9ccf51c83564b5320c2109c0d1b6779defc89a943015568833`，待严格审查线程复验。

本次追加修订：2026-07-19，登记 ADR-011：当前继续使用 Playwright；EgoLite 仅作为 PG-A 后需 Change Request 批准的可选手动适配 spike，不安装依赖、不切换生产默认值；当前台账 SHA 为 `894a229cdfd92556f167f14f28e2fe868d24b971466c58feecfaa0f59aca8f65`，待严格审查线程复验。

本次追加修订：2026-07-19，完成 PG-A evidence closure pass 1：复用既有时间戳补齐九项 click_count/automation_ms/human_wait_ms，新增本地无效媒体预检 JSON、任务 8 失败 handoff 和 13 个脱敏抖音 DOM fixtures；任务 8 失败保留为 current baseline，恢复实现归 PUB-2；未重复扫码、未重复任务 8、未修改业务代码。当前台账 SHA 为 `dfcb791bbd61e344aaf79a2b48fc172c3035549eef54b0640df9ba49bb04a7c9`，待严格审查线程复验。

本次追加修订：2026-07-19，补充 FinalActionGuard/V1 rollback 本地 bounded smoke，明确 `publish`/`confirm_publish`/`unknown` 返回 `FINAL_ACTION_BLOCKED`、临时 profile/material 不产生生产写入；shared contract 标记为 `frozen for COORD-0`；新增 `PG-A-closure-pass-1-2026-07-19.md`，当前台账 SHA 为 `40e728b2c8b2e87ed91c4b9f320fb9005f6f1e4032fae5384679c84972ad0bef`，待严格审查线程复验。

本次追加修订：2026-07-19，按第二轮严格审查完成 evidence 语义收口：基线状态改为 `complete_with_boundary`，契约测试明确 task8 `failed` 是合法 current baseline；DOM fixture 明确为状态/隐私/hash inventory，行为 harness 后置 PUB-3；未增加平台动作或业务代码。当前台账 SHA 为 `404c9ca120d9feb5ab772086efc29f08061c4d0fa31f2d963139cd937fa50909`，待严格审查线程最终复验。

## 3. 工具链与实际运行基线

- Entry 时 `uv run pytest --collect-only -q`：367 项可收集；受控修订后当前为 383 项（新增 16 项 COORD-0 contract tests）；
- COORD-0 契约测试：`uv run pytest -q tests/coord0_contract_test.py`：17 passed；
- 发布/桌面配置/平台能力/安全快速基线：精确命令见 `COORD-0-runtime-evidence.md`；
- `uv run ruff check .`：通过；
- `cd desktop && npm run build`：通过；
- 当前桌面端无 `npm run test`、Vitest 或 Testing Library；按 `frontend-test-tooling-decision.md` 延后至 APP-SHELL（PG-B），`npm run test` 当前为 `not_available`，不伪造 passed；
- `CLAUDE.md` 中“没有 tests 目录/测试套件”是过期说明；实际仓库有 `tests/` 且当前可收集 385 项，Luna 必须以本基线和实时台账为准。

## 4. Entry 与受控修订风险

- 未形成 Git commit；回滚锚点仍为 `aee737e`，恢复时只撤销本次受控文档/测试，不覆盖用户业务改动；
- P0 前端测试工具、旧 UI available 基线、任务 8 中途恢复、全新 LLM/TTS/数字人 provider 生成和真实平台发布仍需后续可执行证据；首次扫码/新 profile、九项 baseline 指标和 DOM fixtures 已收口；AC-0 既有缓存媒体成片任务已补充 `passed_with_boundary` 证据；PG-A 仍等待 closure reviewer 对 shared contract、Guard/rollback 责任边界的最终确认；未确认前不得切换 APP-SHELL；
- 旧 V1 PublishPackage/BrowserRuntime 仅登记为 `legacy compatibility only`，不宣称 V2 已实现。

## 5. Entry 结论（历史）

Entry 通过但带条件：允许执行 COORD-0 的契约、ADR、fixture、迁移 dry-run、回滚设计和审查证据；该结论记录的是 Entry 时点，之后 PG-A 已 `passed_with_boundary`。当前 Stage 不由本历史 Entry 文件控制，以实时台账的 `APP-SHELL / PG-B` 为准。

## 6. CLAUDE.md 测试基线偏差

`CLAUDE.md` 的 Development commands/Testing 章节仍写“没有 tests 目录/测试套件”。实际证据为：`tests/coord0_contract_test.py` 已存在，Entry 收集 367 项；受控修订后当前 `uv run pytest --collect-only -q` 收集 385 项，COORD-0 契约测试 18 passed。COORD-0 不修改该项目说明文件，避免扩大允许文件范围；PG-A 评审以本证据和实时台账为准，后续文档清理另立非业务变更。
