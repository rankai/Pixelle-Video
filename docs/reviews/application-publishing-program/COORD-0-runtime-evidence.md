# COORD-0 可复现运行证据

日期：2026-07-19；执行者：主线程；工作区：`codex/two-day-refactor-batches`；所有命令均为只读检查或内存/临时 fixture。

| 命令 | 结果 |
| --- | --- |
| `uv run pytest -q tests/coord0_contract_test.py` | 18 passed（COORD-0 契约/invalid fixture/DOM fixture/SQLite/Guard/profile/rollback/media/app schemas） |
| `uv run pytest --collect-only -q` | 385 collected (Entry snapshot was 367 before adding 18 COORD-0 contract tests) |
| `uv run ruff check .` | All checks passed |
| `cd desktop && npm run build` | passed |
| `uv run pytest -q tests/publish_assistant_test.py tests/desktop_publish_capability_test.py tests/desktop_build_config_test.py tests/desktop_config_check_ui_test.py tests/desktop_security_test.py tests/service_config_logging_test.py` | 35 passed, 12 warnings |
| `uv run python -c 'from api.app import app; ...'` | 119 total routes（112 `/api`）；无 app-center 业务路由；仅旧 2 publish routes |

契约测试覆盖：Draft 2020-12 schema、Manifest registry semantic allowlist、ArtifactVersion 不变量、PublishPackage 双 source 不变量、PublishRun 人工确认、Task redaction/status projection、AppLLMPort model override/secret redaction、FinalActionGuard allow/deny、V1 rollback local smoke、九项基线指标完整性、抖音 DOM fixture 哈希/隐私校验、SQLite migration repeat/failure constraints。

## 抖音授权/上传基线（2026-07-19）

### 首次扫码连接通过

详见 [`qa/COORD-0-first-scan-passed-2026-07-19.json`](./qa/COORD-0-first-scan-passed-2026-07-19.json)。使用全新隔离 QA profile，扫码前 `qr_visible=true`、`signed_out_pre=true`；用户完成一次扫码后 `signed_in_post=true`；关闭并以同一隔离 profile 重开后 `reopen_signed_in=true`。三张脱敏截图 SHA 分别为 `ae9f9ac9c44572fd92b459ca385a3d0a0c7fd3e4b1350b0fa380bbe83ac3fe46`、`508448aea3e903ea24d48e61b11611449085a8e5095086da88032075166dbeb9`、`c003b8e1b96a11f56ed8e0f42fc2949bbd6eebef2d67336d233150d780741682`；未上传、未发布，临时 profile 已清理。任务 1 标记 `passed`；指标口径和其余八项统一见 [`qa/COORD-0-pub-a-nine-task-metrics-2026-07-19.json`](./qa/COORD-0-pub-a-nine-task-metrics-2026-07-19.json)，SHA `5384b7ad73591c892f53b4b9a2c5e6a9726e420fa3747d13dc492c5f773cd63f`。shared contract 已冻结，Guard/rollback local bounded smoke 已归档；PG-A 只等待最终 reviewer recheck。

详见 [`COORD-0-douyin-manual-baseline-2026-07-19.md`](./COORD-0-douyin-manual-baseline-2026-07-19.md)。这是 pass-0 的历史手动探针：上传入口可见且未出现登录提示，但原生文件选择器“打开”持续 disabled，最终未上传、未填写内容、未发布；当前权威九项结果以本节 metrics JSON 与实时台账为准。

### PUB-A 九项指标与 DOM fixtures 收口

- 九项基线指标 JSON：[`qa/COORD-0-pub-a-nine-task-metrics-2026-07-19.json`](./qa/COORD-0-pub-a-nine-task-metrics-2026-07-19.json)，SHA-256 `5384b7ad73591c892f53b4b9a2c5e6a9726e420fa3747d13dc492c5f773cd63f`。
- 任务 8 结构化失败 handoff：[`qa/COORD-0-task8-recovery-handoff-2026-07-19.json`](./qa/COORD-0-task8-recovery-handoff-2026-07-19.json)，SHA-256 `250fbb2746a7104a5b852ec7c87ab9531fc43056ee14d19fd19c2ece1d0057f7`；恢复实现属于 PUB-2，COORD-0 不重试。
- 本地无效媒体预检：[`qa/COORD-0-invalid-media-preflight-2026-07-19.json`](./qa/COORD-0-invalid-media-preflight-2026-07-19.json)，SHA-256 `acf9a800c3d563ea2afc345dd7a524e083774003aae7c45db4648d723be269ab`；无浏览器动作、无平台提交。
- 最小脱敏抖音 DOM fixture inventory：[`tests/fixtures/publishing/manifest.json`](../../../tests/fixtures/publishing/manifest.json)，SHA-256 `1ccfd9212a5e39ca31d7b6e95760d09523244b46add08ab40ea5418aa60f43a2`；13 个状态 fixture 由 `tests/coord0_contract_test.py` 校验文件存在、哈希、关键语义和隐私字段排除；行为 probe harness（进度、延迟、关闭/崩溃）后置 PUB-3。
- FinalActionGuard/V1 rollback 本地 bounded smoke：[`qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json`](./qa/COORD-0-guard-rollback-local-smoke-2026-07-19.json)，SHA-256 `35b11a05a50b39aedf4d6b3e85d9bcabe6a4b2274019762017321ff09aa87406`；临时 profile/material 保留与复制回退通过，`publish`/`confirm_publish`/`unknown` 均 `FINAL_ACTION_BLOCKED`，无平台动作。

### Playwright 持久化 profile 上传复验

详见 [`COORD-0-douyin-playwright-upload-2026-07-19.md`](./COORD-0-douyin-playwright-upload-2026-07-19.md)。这是 pass-0 的历史上传运行：复用既有 profile 后登录探针通过，单次 `set_input_files()` 将有效 MP4 送入编辑器，未发布；任务 5 的当前指标由九项 metrics JSON 统一引用，不能把该历史段落的“未完成”解读为当前九项缺证。

### Playwright 字段/封面综合复验

详见 [`COORD-0-douyin-playwright-fields-2026-07-19.md`](./COORD-0-douyin-playwright-fields-2026-07-19.md)。这是 pass-0 的历史失败运行：一次综合运行中描述/话题 selector 和封面尺寸曾未通过；后续 [`COORD-0-douyin-fields-cover-live-2026-07-19.md`](./COORD-0-douyin-fields-cover-live-2026-07-19.md) 已完成真实标题、简介 contenteditable、话题文本和竖封面保存 smoke，当前结果以后者及 metrics JSON 为准。

### Playwright profile 关闭/重开复验

详见 [`COORD-0-douyin-playwright-reopen-2026-07-19.md`](./COORD-0-douyin-playwright-reopen-2026-07-19.md)。复用同一已有 profile，先关闭首个 Playwright 持久化上下文，再打开同一 profile 的新上下文；两个阶段登录探针均为 `true`，分别耗时 `1722 ms`、`1634 ms`，均位于 `/creator-micro/content/upload`；同一次运行记录了 `first_context_closed → reopen_context_opened → reopen_context_probe_and_screenshot → reopen_context_closed` 的完整事件链，脱敏截图 SHA 为 `034ff131a62730b5297bec5afdc07128f8058620b1f6a3aa8317b7375809809f`。该证据只覆盖现有 profile 的关闭/重开（任务 2），不声称完成首次扫码、桌面应用重启或中途编辑器恢复。

### Playwright 中途关闭/恢复复验

详见 [`COORD-0-douyin-playwright-midclose-recovery-2026-07-19.md`](./COORD-0-douyin-playwright-midclose-recovery-2026-07-19.md)。一次有明确目的的运行中，已知有效 MP4 进入编辑器后关闭上下文；同一 profile 重开后 URL 回到 `/creator-micro/content/upload`，`same_editor_url=false`，未发现可证明草稿恢复的状态，因此任务 8 记录为 `failed`。未填写字段、未上传封面、未点击发布；脱敏截图 SHA 为 `10a8717ef2c9cf684b2f8e2d76248145dfade74a4340c19c7026b91e6fba6be9`。

### AC-0 应用中心/桌面页面 Playwright 基线

详见 [`COORD-0-app-baseline-playwright-2026-07-19.md`](./COORD-0-app-baseline-playwright-2026-07-19.md)。浏览器开发模式已归档 5 张页面截图、工作台/页面入口导航录像、口播五步流程导航录像，以及一次预填既有有效缓存媒体后真实点击“一键成片”的任务录像；控制台错误均为 0，真实任务生成最终视频/封面/脚本/发布包并在发布前安全停手。运行日志同时发现前端初始化自动 `POST /api/ip-broadcast/sessions` 并写本地 session 文件；该次真实任务的完整证据见 [`COORD-0-core-production-task-2026-07-19.md`](./COORD-0-core-production-task-2026-07-19.md)。该证据将 AC-0 的真实成片链路提升为 `passed_with_boundary`，但仍不等价于 Tauri 打包版、全新 LLM/TTS/数字人 provider 生成或真实发布。入口录像 SHA-256：`da573d17e8c579616e8e41553539f887fb8abc51248922ba63f45347568f5d72`；五步流程录像 SHA-256：`8e2c95cc61b1edaa55d8f180c6c1ffe26c1ba58d868884e8bc500f298e374752`；任务录像 SHA-256：`3a1f9a6bca0ad3d11f24a3902087ba8d243e3d9184908ba4777d7403d8d96cf8`。

### Tauri/sidecar 重启复验

详见 [`COORD-0-tauri-sidecar-restart-2026-07-19.md`](./COORD-0-tauri-sidecar-restart-2026-07-19.md)。第一次 CLI 探针因 PATH 未包含 `~/.cargo/bin` 失败；显式加入 Rust PATH 后，Tauri 本体两轮启动/停止通过，sidecar 两轮 `/health`、停止和端口释放通过；重启后既有抖音 profile 只读登录探针为 `true`，无上传/发布。该证据将任务 3 标记为 passed，但不覆盖首次扫码任务 1。

### 核心导航录像校验

`COORD-0-core-navigation.webm`：`ffprobe` 报告 VP8、1440×1000、时长约 7.4 秒；归档 SHA-256 `da573d17e8c579616e8e41553539f887fb8abc51248922ba63f45347568f5d72`。录像只覆盖页面入口导航，不覆盖业务生产任务。

### 无效媒体与字段/封面 live smoke

详见 [`COORD-0-douyin-invalid-media-2026-07-19.md`](./COORD-0-douyin-invalid-media-2026-07-19.md)：隔离 fixture 的坏 MP4 在浏览器前被 ffprobe/仓库媒体探针拒绝，1×1 封面被本地尺寸门槛拒绝；没有向平台提交坏文件。

详见 [`COORD-0-douyin-fields-cover-live-2026-07-19.md`](./COORD-0-douyin-fields-cover-live-2026-07-19.md)：一次性复用已有登录 profile 完成标题、简介 contenteditable、话题文本回填和 1080×1440 竖封面裁切保存；截图中发布按钮可见但未点击，`final_publish_clicked=false`。横版封面仍是平台建议缺口，第三方 console error 原样记录，不归因于应用代码。
