# PLATFORM-EXPANSION implementation review（2026-07-22）

## 审查范围

独立只读审查线程 `/root/platform_expansion_foundation_reviewer` 对快手、视频号（含 `video_channel` alias）、小红书的平台 profile、factory、统一 `HumanConfirmedPublisher`、Playwright runtime、release gate、失败矩阵、审计事件和桌面发布入口进行六维复核：需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果。

## 修复闭环

- P1：视频号 alias 的 checkpoint 由 V2 以 `video_channel` 写入、adapter 以 `shipinhao` 执行的绑定不一致。已统一 V2 checkpoint、run-service binding 和 adapter 比较使用 `canonical_platform`，并增加 alias checkpoint 回归测试。
- P2：`data-state=editor_ready` 可能早于挑战浮层返回。已将验证码/安全验证 marker 扫描移到 `data-state` 返回前，并增加 `editor_ready + 风险验证` 负例。
- P2：Kuaishou 视频预览判断曾使用宽泛 `video.count()`，且缺少真实 filechooser/封面对话框与断点 blob 回归。已改为平台 preview/identity selector，补齐无关视频负例、继续编辑/chooser 失败分支、fake-Playwright 上传确认和 checkpoint+blob fail-closed 测试。
- P2：小红书上传后异步替换 video input、Tiptap 正文控件和封面编辑器均与初版 selector/时序不同。已增加有界视频预览等待、`div[contenteditable][role=textbox]` 正文 selector、`.upload-cover` → image input → `确定` 流程，以及一次 DOM-detach 重新获取；小红书文本话题、blob 封面和无稳定媒体 ID 均记录显式边界。
- 复验：Kuaishou 修复后等待独立审查线程再次确认；release_state 仍保持 `unverified`。
- 独立复审收口：小红书本轮六维复审确认 P0=0、P1=0、实质性 P2=0；fake runtime 未专门强制 DOM-detach 重取分支属于可选增强，不阻断本批。

## 验证依据

- `uv run pytest -q tests/publish_*_test.py tests/platform_expansion_*_test.py tests/desktop_publish_capability_test.py`：170 passed，12 个既有 Pydantic 弃用警告。
- Desktop Vitest：10 files / 55 tests passed；`npm run build` passed（仅既有 chunk size warning）。
- 三平台 live entry probe：初始探针为快手、小红书进入登录页；视频号被浏览器安全策略阻止。随后用户完成一次快手扫码，项目 Playwright 真实适配器取得 [`PG-M-kuaishou-live-gate-2026-07-22.json`](qa/PG-M-kuaishou-live-gate-2026-07-22.json)：视频一次注入、描述/话题文本回退、封面 UI 确认、关闭/重开零重复上传、最终点击 0；标题不支持、封面仅本地 blob receipt boundary。
- 视频号后续真实扫码已取得登录探针。项目 Playwright 已修复 Wujie Shadow DOM 根节点作用域，并补齐真实描述控件 `div.post-desc-box .input-editor`、图片 input/封面预览读回；一次 bounded 主尝试以 `draft_ready` 完成视频、标题、描述、封面四字段读回，HTTPS 封面回执按 `ui_confirmed_https_receipt` 记为可信，媒体无稳定远端 ID 记录为 `SHIPINHAO_NO_STABLE_REMOTE_MEDIA_ID`。但关闭/重开同一 profile 后平台未持久化未保存草稿，checkpoint 安全停在 `STATE_AMBIGUOUS`，重启后上传调用为 0。修复证据归档为 [`PG-M-shipinhao-live-gate-fix-2026-07-22.json`](qa/PG-M-shipinhao-live-gate-fix-2026-07-22.json)；旧 Wujie 卸载证据仍保留在 [`PG-M-shipinhao-live-gate-2026-07-22.json`](qa/PG-M-shipinhao-live-gate-2026-07-22.json)。
- 小红书用户完成项目 Playwright 登录后，真实主尝试以 `draft_ready` 完成视频、标题、正文、话题和封面五字段各一次读回，最终点击 0；话题为 `HASHTAGS_TEXT_FALLBACK`，封面为 `XIAOHONGSHU_LOCAL_BLOB_PREVIEW_ONLY`，媒体为 `XIAOHONGSHU_NO_STABLE_REMOTE_MEDIA_ID`。同一 profile 关闭/重开后登录仍在但未保存草稿不持久化，checkpoint 以 `STATE_AMBIGUOUS` fail-closed，重启 upload=0。证据归档为 [`PG-M-xiaohongshu-live-gate-2026-07-22.json`](qa/PG-M-xiaohongshu-live-gate-2026-07-22.json)。
- 独立审查线程复验六维：需求/逻辑/边界/代码/测试/实际运行均通过；项目 Playwright headful 主尝试与重启门均有证据，挑战证据保持人工边界，无自动化绕过或最终发布点击。
- 三个平台 `platform_release_state` 仍为 `unverified`；V2 创建真实 run 继续由 release gate 拒绝，UI 仅提供复制素材回退。

## 结论

快手 live gate 可记为 `passed_with_explicit_boundaries`；视频号和小红书均完成主填充，但完整 live gate 都以重启后未保存草稿不持久化为 `blocked_with_explicit_boundary`。独立复审已确认两个平台都保持 `STATE_AMBIGUOUS`、重启后上传调用 0、release state `unverified`，不得把主填充冒充完整 gate。`PLATFORM-EXPANSION` 仍不能标记为整体完成或恢复 Windows；各平台 release state 均保持 `unverified`。最终发布自动点击继续由契约、Guard、checkpoint 和结果计数共同保持关闭（`final_publish_click_count=0`）。
