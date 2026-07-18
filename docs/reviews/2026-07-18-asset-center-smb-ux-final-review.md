# Asset Center SMB UX 最终复审记录

- 日期：2026-07-18
- 对象：`docs/reviews/2026-07-18-asset-center-v2-smb-usability-implementation-plan.md`
- 复审范围：UX-0～UX-4 实现、自动化回归、桌面前端预检、回滚与灰度开关

## 结论

实现主链已经完成，UX-0 的技术交付以及 UX-1～UX-4 的本地技术门禁通过；UX-A 八项证据已完成正式证据复审并通过。新版前台开关继续保持默认关闭，待 UX-C/UX-D/UX-E 的目标用户与发布设备证据补齐后再灰度开启；显式开启使用 `PIXELLE_ASSET_CENTER_SMB_UX=true` / `VITE_ASSET_CENTER_SMB_UX=true`，回滚则设为 `false`。

本记录不把自动化预检冒充目标用户验收。严格按方案第 14、15 节，UX-E 最终放行仍需要在固定设备、固定 1000 条数据和真实任务样本上补录至少 2 位老板、2 位店长/运营、1 位熟练运营的中位数/P95、录像和发布设备模板真实 MP4 抽帧证据。故当前结论为：**UX-A 证据门禁通过；UX-C/UX-D/UX-E 本地技术证据通过，但目标用户研究、发布设备签署与完整 glyph mask 对比仍待补，不宣称默认 rollout 已放行。**

## 已交付

| 阶段 | 交付与证据 | 状态 |
| --- | --- | --- |
| UX-0 / UX-A 技术契约 | ADR、schema、fixture、voice migration dry-run、真实数据基线、隔离 rollback smoke、`scripts/ux0_gate.py` manifest、当前版七项桌面基线报告与录像、UX-A 正式证据复审 | UX-0 gate `pass`；UX-A 证据门禁 `pass` |
| UX-1 / UX-B | SQL 统一投影、显式 index generation、signed cursor、query-consistent facets、增量加载、网格/列表、类型化七类 view model、三层详情、图片检查器、集合/批量动作、局部错误与 reduced-motion 基础 | 技术桌面证据通过：真实 Vite/FastAPI 固定 fixture 逐类浏览/预览视频、图片、数字人、音色、音频、模板、品牌；“图片”筛选完成 16 次加载更多、1000 个唯一卡片和 `性能素材 00999` 单条搜索；搜索 facet 的 ambiguous `resource_id` 缺陷已修复并回归；目标设备全量视觉回归待补 |
| UX-2 / UX-C | `AssetUploadQueue` 共享组件、拖放/多文件/本地预览/逐文件状态、唯一文件 `uploaded` 无策略 finalize、三种重复策略/target asset、幂等、SHA 重选校验、重启后重新选择原文件提示、picker context/预览/确认/兼容性；隔离真实 Vite/FastAPI 桌面 E2E 录像 | 技术桌面证据通过：10 文件中第 3/6/9 个失败，7 个成功项未重传；取消 usage=0；重启重选文案可见；三种重复策略均从真实上传队列 UI 选择，资产/版本计数与 API 重复 finalize 均符合幂等；真实 picker 图片/视频同槽回填并产出 1080×1920 MP4，artifact 200、usage/snapshot 通过；数字人场景 picker、VoiceProfile 试听/上传/确认使用也已在同一真实桌面报告闭合；新增服务断开→重试、归档/恢复和 snapshot 保持可解析的真实桌面证据；发布设备录像仍待补 |
| UX-3 / UX-D | Digital Human scene patch/archive/reorder、BrandKit 全字段保存与预览、VoiceProfile 试听/上传/确认使用与 BGM 隔离、TemplateLayoutContract 字体身份校验与服务端实际 PNG preview resolver | 真实桌面 picker 已完成已有音色试听、上传建档、重新选择并确认使用；VoiceProfile ID 解析并记录 usage；真实打包 Noto CJK 字体、ASS/MP4 抽帧 harness、5 类文本/紫珊主题/720×1280 技术门禁通过；完整 glyph mask 与发布设备视觉门禁待补 |
| UX-4 / UX-E | SMB UX 独立灰度开关、行为埋点不含媒体内容、1000/5000 条 SQL cursor benchmark、键盘/读屏/对比度/reduced-motion、紫珊主题四 viewport、透明 PNG/极端比例视觉回归、gray on/off、blob URL 异步卸载竞态保护、文档回滚路径 | 本地技术门禁通过（最小对比度 17.73；透明 fixture 与详情检查器均通过）；目标用户与 release 设备门禁待补 |

## 可复现验证

- `uv run pytest -q tests/asset_library_ux0_contract_test.py tests/asset_library_ux1_test.py tests/asset_library_stage0_test.py`：16 passed。
- `cd desktop && npm run build`：TypeScript、Vite 构建通过。
- `uv run ruff check api/routers/assets_v2.py api/schemas/asset_library_v2.py pixelle_video/services/assets_v2/repository.py tests/asset_library_ux1_test.py`：通过。
- `git diff --check`：通过。
- 透明 PNG 回归：`uv run pytest -q tests/asset_library_v2_repository_test.py -k 'transparency or stream_upload or stage1_database'`，4 passed；透明度字段兼容迁移、revision 投影和上传路径通过。
- `base=$(mktemp -d /Volumes/Data/pixelle-asset-library-tests.XXXXXX) && TMPDIR=/Volumes/Data uv run pytest -q --basetemp="$base" tests/asset_library_v2_repository_test.py tests/asset_library_ux1_test.py`：29 passed、12 warnings；透明度、上传、游标、迁移、领域投影和模板/字体相关回归均通过。
- `uv run pytest -q tests/asset_library*.py tests/desktop_asset_actions_test.py tests/desktop_asset_card_css_test.py tests/desktop_build_config_test.py tests/desktop_theme_test.py tests/ip_broadcast_render_regression_test.py`：69 passed。
- `base=$(mktemp -d /Volumes/Data/pixelle-full-tests.XXXXXX) && TMPDIR=/Volumes/Data uv run pytest -q --basetemp="$base" -k 'not test_artifact_download_allows_project_temp_preview_files'`：365 passed、1 deselected、12 warnings；被排除的 artifact-preview 单测此前在隔离 data root 下单独复跑通过。
- `base=$(mktemp -d /Volumes/Data/pixelle-full-tests-synthetic.XXXXXX) && TMPDIR=/Volumes/Data uv run pytest -q --basetemp="$base" -k 'not test_artifact_download_allows_project_temp_preview_files'`：当前轮修复后 366 passed、1 deselected、12 warnings；`tests/desktop_api_client_test.py` 单独 4 passed。
- `uv run python scripts/assets_ux4_performance.py --output docs/migrations/asset-center-uxe-performance-2026-07-18.json --count 1000 5000`：1000 条 17 页、首屏 6.32ms；5000 条 84 页、首屏 24.43ms；跨页无重复，两组脚本状态均为 `pass`。
- `uv run python scripts/template_layout_gate.py --output docs/migrations/template-layout-uxd-gate-2026-07-18.json`：按生产 ASS 路径、0.5 秒字幕已出现的抽帧验证真实 Noto CJK 打包字体 SHA、ASS force style、5 个文本/主题样例和 720×1280 MP4；缺失字体 fixture 被拒绝，坐标误差 0px、contract-box IoU 1.0。该产物明确 `glyph_mask_iou=null`，不替代发布设备 glyph mask 复核。
- `uv run python scripts/ux0_gate.py --output docs/migrations/asset-library-ux0-gate-2026-07-18.json`：5 份 ADR、9 个 JSON Schema、11 个 fixture entry、baseline、VoiceProfile dry-run、rollback smoke 和当前版七项基线报告均存在且通过。
- `uv run python scripts/ux0_gate.py --output /Users/nickfury/projects/pixelle-video/docs/migrations/asset-library-ux0-gate-2026-07-18.json`：UX-A 正式证据复审 8/8，通过，`ux_a_status=pass`；UX-E 目标用户研究仍单独标记未完成。
- `uv run python scripts/asset_center_ux0_baseline_desktop.py --output-dir docs/migrations/asset-center-ux0-current-baseline-2026-07-18`：当前 V2 内核 / SMB 前台关闭，在 1440×1000 隔离桌面上完成 7/7 任务截图、点击数、耗时、错误记录和录像；报告明确标记为非目标用户研究。
- `uv run python scripts/asset_center_uxb_desktop_gate.py --output-dir docs/migrations/asset-center-uxb-desktop-gate-2026-07-18`：真实 Vite/FastAPI 桌面逐类浏览/预览七类资产；固定 1000 条图片 fixture 完成“图片”筛选、16 次 cursor-backed 加载更多、1000 个唯一卡片和 `性能素材 00999` 单条搜索；报告为 `technical_pass`。
- `uv run python scripts/asset_center_uxc_desktop_e2e.py --output-dir docs/migrations/asset-center-uxc-desktop-e2e-2026-07-18-pass`：隔离 data root 的真实 Vite/FastAPI 桌面面通过；首批 10 个 content 请求中第 3/6/9 个失败，UI 收敛为 7/10 已入库且无成功项重传；取消场景 usage=0；重启后重新选择原文件文案可见；录像与三张截图已归档。
- `uv run python scripts/asset_center_uxc_duplicate_desktop_e2e.py --output-dir docs/migrations/asset-center-uxc-duplicate-desktop-e2e-2026-07-18`：真实 AssetUploadQueue 分别选择“使用已有资产 / 作为新版本 / 创建独立资产”；资产数、revision 数和三次 API finalize 重复调用均通过，报告为 `pass`。
- `uv run python scripts/asset_center_uxc_production_desktop_e2e.py --output-dir docs/migrations/asset-center-uxc-production-desktop-e2e-2026-07-18`：真实桌面 picker 已覆盖已有音色试听、上传建档、确认使用，图片/视频分别写回覆盖槽位，点击“一键成片”后任务 completed；ffprobe `1080,1920`，artifact HTTP 200，usage 及 snapshot 通过，VoiceProfile ID 能解析 audio revision，且 BGM 仅出现在 audio facet、不出现在 voice facet。
- `TMPDIR=/Volumes/Data uv run python scripts/asset_center_uxb_desktop_gate.py --output-dir /Volumes/Data/pixelle-synthetic-owner-uxb-2026-07-18`、`asset_center_uxc_desktop_e2e.py`、`asset_center_uxc_production_desktop_e2e.py`、`asset_center_uxc_duplicate_desktop_e2e.py`：本轮用店主、店长/运营、熟练运营三类 synthetic persona 做收口预检；操作链分别通过，店主 1000 条资产全量可达，店长批量 7/10 入库且取消 usage=0，熟练运营产出 1080×1920 MP4、7 项 usage snapshot 且重复策略幂等。该包明确标记 `synthetic_internal_precheck=true`，不替代真实目标用户研究。
- 合成店长预检首次发现批量上传 5xx 失败行展示后端原始 JSON；已在 `desktop/src/api.ts` 统一 XHR 与 fetch 的业务错误文案，修复后复跑截图只显示“服务器暂时不可用，请稍后重试”，无 `detail`/API 地址泄漏；合成验收包位于 `/Volumes/Data/pixelle-synthetic-persona-acceptance-2026-07-18.md`。
- `TMPDIR=/Volumes/Data uv run python scripts/asset_center_uxc_recovery_rollback_desktop_e2e.py --output-dir docs/migrations/asset-center-uxc-recovery-rollback-desktop-e2e-2026-07-18`：真实桌面注入一次服务断开后通过“重试”恢复；默认错误不显示 API 地址；归档/恢复状态正确，已被 session 引用的 snapshot 在前后均保持可解析。
- `TMPDIR=/Volumes/Data uv run python scripts/validate_asset_center_uxe_release_evidence.py --input docs/migrations/asset-center-uxe-release-evidence-template-2026-07-18.json --output docs/migrations/asset-center-uxe-release-evidence-validation-2026-07-18.json`：当前模板被明确判定为 `pending_external_evidence`，未填满前 `default_rollout_authorized=false`；validator 不生成任何用户、设备、glyph 或灰度数据。
- `uv run python scripts/asset_center_uxe_desktop_gate.py --output-dir docs/migrations/asset-center-uxe-desktop-gate-2026-07-18`：紫/珊瑚两主题、4 个 viewport、键盘/读屏/reduced-motion、最小对比度 17.73、SMB on/off 回滚均为 `technical_pass`。
- 同一 UX-E 门禁的 `visual_fixture_checks` 已明确记录 3 张图片 fixture、透明 PNG 标识、极端比例存在和详情图片检查器打开；媒体 revision 新增透明度元数据并带兼容迁移，透明卡片在紫/珊瑚主题均通过。
- `cd desktop && npm run build`：blob URL 异步请求的卸载竞态保护通过 TypeScript/Vite 构建；资产中心、picker、详情检查器和成片预览均在请求完成晚于卸载时回收新产生的 URL。
- `uv run python scripts/assets_ux4_performance.py --output docs/migrations/asset-center-uxe-performance-2026-07-18.json --count 1000 5000`：1000 页数 17、首屏 6.32ms；5000 页数 84、首屏 24.43ms；两组均 `pass`。
- Playwright fallback（应用内 Browser 运行时返回 `Cannot redefine property: process`，未使用空白截图）：灰度开启后 `http://127.0.0.1:1420` 加载成功；资产页显示七类分类与 14 条当前数据；截图 `/tmp/asset-center-ux4-final.png` 为非空本地预检，已检查卡片、图片详情检查器和上传队列入口。该截图不替代目标用户视觉评审。

## 关键实现位置

- 后端统一列表、VoiceProfile、deferred upload、scene/collection/template：`pixelle_video/services/assets_v2/repository.py`、`api/routers/assets_v2.py`。
- 前端类型化投影、共享上传队列、picker 确认协议：`desktop/src/features/assets/model/assetViewModel.ts`、`desktop/src/features/assets/components/AssetUploadQueue.tsx`、`desktop/src/features/assets/components/AssetPickerDialog.tsx`。
- 灰度开关：`api/config.py`、`desktop/src/featureFlags.ts`、`desktop/src/StudioApp.tsx`。
- 默认错误文案与 API 地址隔离：`desktop/src/api.ts`；服务断开恢复证据：`scripts/asset_center_uxc_recovery_rollback_desktop_e2e.py`。
- 外部 UX-E 证据格式与强制验收：`docs/migrations/asset-center-uxe-release-evidence-template-2026-07-18.json`、`scripts/validate_asset_center_uxe_release_evidence.py`。
- 资产中心拆分后的共享视觉/格式原语：`desktop/src/features/assets/components/AssetCenterPrimitives.tsx`；模板领域编辑器：`desktop/src/features/assets/components/AssetDomainEditors.tsx`。
- 性能与领域专项回归：`scripts/assets_ux4_performance.py`、`tests/asset_library_ux1_test.py`。
- 字体与渲染门禁：`assets/fonts/README.md`、`pixelle_video/services/font_registry.py`、`scripts/template_layout_gate.py`、`docs/migrations/template-layout-uxd-gate-2026-07-18.json`。

## 未闭合的发布门禁

1. UX-C/UX-D/UX-E 发布设备证据：本地真实 Vite/FastAPI 桌面技术闭环已通过，但尚未在实际 release device 上签署；完整 glyph mask IoU 仍需按发布设备抽帧协议复核。
2. UX-E 目标用户研究：按方案招募至少 2 位门店老板、2 位店长/运营、1 位熟练视频运营，记录成功率、中位数/P95、录像和错误码；内部自动化不能替代该研究。
3. 灰度观察窗口：补充真实设备灰度 success/revert 指标后，才可把 `ASSET_CENTER_SMB_UX` 从默认关闭改为默认开启；旧实现继续保留。

上述外部证据的填报格式已冻结在 [`asset-center-uxe-release-evidence-template-2026-07-18.json`](../migrations/asset-center-uxe-release-evidence-template-2026-07-18.json) 与 [`2026-07-18-asset-center-uxe-release-evidence-template.md`](2026-07-18-asset-center-uxe-release-evidence-template.md)；当前模板状态仍为 `pending_external_evidence`。

真实设备与目标用户的执行步骤固定在 [`2026-07-18-asset-center-uxe-release-evidence-runbook.md`](2026-07-18-asset-center-uxe-release-evidence-runbook.md)，完成后必须重新运行 validator。

上述证据补齐前，不删除旧 V2/旧资产实现；关闭 SMB UX 只回退当前 V2 前台，数据库迁移和新字段保持兼容。
