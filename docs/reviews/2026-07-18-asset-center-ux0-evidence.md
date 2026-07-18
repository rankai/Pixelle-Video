# 资产中心 SMB UX-0 交付与 UX-A 证据清单

- 日期：2026-07-18
- 阶段：UX-0
- 结论：**UX-0 契约、fixture、迁移 dry-run、数据基线、回滚 smoke 和当前版七项基线已交付；UX-A 八项证据已完成正式复审并通过，可进入 UX-1。**
- 评审对象：`docs/reviews/2026-07-18-asset-center-v2-smb-usability-implementation-plan.md`

## 交付物

| UX-0 交付 | 证据 | 自动验证 |
| --- | --- | --- |
| 七种 AssetViewModel、picker context、action matrix、错误码 | `docs/contracts/asset-center-ux0-action-matrix.json`、`api/schemas/asset_library_ux0.py`、`desktop/src/features/assets/model/ux0Contracts.ts` | `test_template_layout_contract...` 等 UX-0 专项测试 |
| TemplateLayoutContract v2、字段映射、golden 算法 | `docs/adr/003-template-layout-contract-v2.md`、`docs/schemas/template-layout-contract-v2.schema.json`、`tests/fixtures/ux0/template-layout/` | 未知字段/字体缺失/布局越界拒绝 |
| VoiceProfile schema、迁移/回滚设计 | `docs/adr/004-voice-profile.md`、`docs/schemas/voice-profile.schema.json` | fixture 2 个旧 profile、2/2 session 引用可解析、BGM 排除；当前 data root dry-run 为 2 个 profile、1/1 session 引用可解析 |
| deferred upload 状态/三策略/idempotency/TTL | `docs/adr/005-deferred-upload-finalize.md`、`docs/schemas/deferred-upload-*.schema.json`、`tests/fixtures/ux0/deferred-upload/cases.json` | policy 与 target 校验、重启文案校验 |
| 稳定 cursor/facets | `docs/adr/006-stable-cursor-facets.md`、`pixelle_video/services/asset_library_cursor.py`、`docs/schemas/library-*.schema.json` | 同 generation 无重复/遗漏；mutation 明确 `cursor_stale` |
| 真实数据基线 | `docs/migrations/asset-library-ux0-baseline-2026-07-18.json` | 4 manifest、7 条 legacy 记录、缺失文件 0 |
| 当前版七项桌面基线 | `docs/migrations/asset-center-ux0-current-baseline-2026-07-18/report.json`、同目录 7 张截图与 `raw-video/` 录像 | 1440×1000、V2 内核 / SMB 前台关闭；7/7 任务均有截图、点击数、耗时、错误记录；非目标用户研究 |
| VoiceProfile migration dry-run | `docs/migrations/voice-profile-dry-run-2026-07-18.json` | `writes_performed=0`、当前 data root 1/1 解析、1 个 BGM 排除 |
| 回滚证据 | `docs/migrations/asset-library-ux0-rollback-2026-07-18.json` | 隔离副本 backup/restore PASS；原 data root 未修改 |
| UX-0 gate manifest | `docs/migrations/asset-library-ux0-gate-2026-07-18.json`、`scripts/ux0_gate.py` | 5 ADR、9 schema、11 fixture entries 与上述 migration artifacts 全部存在，gate `pass` |
| 新 UX 灰度开关 | `PIXELLE_ASSET_CENTER_SMB_UX`、`VITE_ASSET_CENTER_SMB_UX` | 默认 false；V2 内核默认值不变 |

## 状态图

```mermaid
stateDiagram-v2
    [*] --> default
    default --> loading: 查询
    loading --> content: 成功
    loading --> listError: 列表失败
    default --> empty: 无数据
    content --> preview: 单击卡片
    content --> bulk: 批量管理
    content --> upload: 添加资产
    upload --> uploading: 开始上传
    uploading --> duplicate: SHA 重复
    uploading --> uploadError: 单文件失败
    duplicate --> content: 选择策略并 finalize
    preview --> content: 关闭
    bulk --> archived: 确认归档
    archived --> content: 恢复
    listError --> loading: 重试
    uploadError --> uploading: 单项重试
```

## 当前版七项测量基线

测量口径沿用方案第 14.0 节：同一设备、同一数据集、同一任务定义，记录首个有效点击至任务完成的耗时、用户点击数、错误和截图/录像。没有捕获到的值明确记为 `未采集`，不用估算填充。

UX-0 交付物复核命令：

```bash
uv run python scripts/export_asset_ux0_schemas.py --output-dir docs/schemas
uv run python scripts/assets_v2_baseline.py --data-root data --output docs/migrations/asset-library-ux0-baseline-2026-07-18.json
uv run python scripts/voice_profile_migration_dry_run.py --data-root data --session-root data/ip_broadcast_sessions --ordinary-audio-manifest data/voice_references/voice_references.json --output docs/migrations/voice-profile-dry-run-2026-07-18.json
uv run python scripts/assets_v2_rollback_smoke.py --data-root data --output docs/migrations/asset-library-ux0-rollback-2026-07-18.json
uv run python scripts/asset_center_ux0_baseline_desktop.py --output-dir docs/migrations/asset-center-ux0-current-baseline-2026-07-18
uv run python scripts/ux0_gate.py --output docs/migrations/asset-library-ux0-gate-2026-07-18.json
```

最近一次复核结果：`UX-0 gate: pass`；baseline 缺失文件 `0`，dry-run 写入 `0`，当前 session 引用 `1/1` 可解析，rollback manifest backup `4`，原 data root 未修改。

| 任务 | 当前版证据 | 点击数 | 耗时 | 错误/备注 |
| --- | --- | ---: | ---: | --- |
| 找到门店图片并用于画面规划 | `report.json` task 1；`ux0-01-find-image-and-storyboard.png`；raw-video | 9 | 1760 ms | 通过；真实生产画面规划与图片 picker 选择完成 |
| 批量上传 10 张商品图片并打标签 | `report.json` task 2；`ux0-02-batch-upload-10.png`；raw-video | 2 | 54 ms | 记录到旧前台错误：文件选择 input 非 multiple，无法一次选择 10 个文件 |
| 添加带封面/演示视频的数字人并选择场景 | `report.json` task 3；`ux0-03-add-digital-human-scene.png`；raw-video | 3 | 316 ms | 单文件形象保存通过；当前版不具备封面/演示视频双字段和场景选择 |
| 修改品牌 Logo/BGM/地址并套用 | `report.json` task 4；`ux0-04-brand-apply.png`；raw-video | 2 | 78 ms | 地址、电话、团购口令保存通过；Logo、稳定 BGM 选择和明确生产确认缺失 |
| 预览模板字幕/封面位置后用于成片 | `report.json` task 5；`ux0-05-template-preview.png`；raw-video | 1 | 36 ms | 记录到旧前台错误：模板库只有浏览，没有字幕/封面位置编辑或保存预览控件 |
| 上传失败后恢复 | `report.json` task 6；`ux0-06-upload-failure-recovery.png`；raw-video | 4 | 382 ms | 首次合成请求注入 500，重新提交后恢复并入库 |
| 归档后恢复资产 | `report.json` task 7；`ux0-07-archive-restore.png`；raw-video | 3 | 296 ms | 归档动作可执行；当前版没有恢复入口，恢复仍需兼容 API |

当前版真实视觉材料只有阶段 C 已归档的非空截图：

- `docs/reviews/enterprise-asset-library-v2-desktop-qa.jpeg`；
- `docs/reviews/enterprise-asset-library-v2-detail-qa.jpeg`。

本轮专用应用内浏览器连接仍返回 `Cannot redefine property: process`，因此没有把空白截图当作基线。新增基线使用普通 Playwright fallback 驱动真实 Vite/FastAPI 桌面界面，截图均为非空；它覆盖同口径点击数、耗时和录像，但使用隔离合成数据，不是目标用户研究或发布设备签字。

## UX-A 复审结论与边界

UX-A 八项证据已在 [`2026-07-18-asset-center-uxa-formal-evidence-review.md`](2026-07-18-asset-center-uxa-formal-evidence-review.md) 中正式复审并判定通过；`scripts/ux0_gate.py` 已将 `ux_a_status` 记录为 `pass`。当前版七项基线中仍明确记录的旧前台批量、数字人场景、模板和恢复缺口继续作为 current baseline 保留，不被误报成新版验收结果。

该结论只授权进入 UX-1，不授权默认开启 SMB UX；目标用户研究、发布设备签署、完整 glyph mask IoU 和灰度观察窗口仍属于 UX-C/UX-D/UX-E 的后续发布门禁。`VITE_ASSET_CENTER_SMB_UX` 继续默认关闭，旧实现与 V2 内核继续保留。

下一步应完成上述七项基线的正式产品/UX 评审，并冻结 current/new 对照口径；在评审结论写入前不打开 `VITE_ASSET_CENTER_SMB_UX`，不清理 V2/旧实现，也不把迁移 dry-run 误报成已执行迁移。
