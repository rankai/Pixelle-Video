# 资产中心 UX-A 证据正式复审

- 日期：2026-07-18
- 评审对象：`docs/reviews/2026-07-18-asset-center-v2-smb-usability-implementation-plan.md`
- 评审范围：UX-0 八项进入 UX-1 的证据门禁
- 评审性质：实现证据复审；不等同于 UX-E 目标用户研究、发布设备签署或默认开关放行

## 结论

**UX-A 证据门禁通过，可进入 UX-1。** 当前版七项任务中保留的批量、数字人场景、模板和恢复错误，是被要求冻结的 current baseline，不是对新版能力的通过声明；新版能力必须继续以 UX-C/UX-D/UX-E 的独立证据为准。

| # | UX-A 要求 | 复审证据 | 结果 |
| ---: | --- | --- | --- |
| 1 | 七种 `AssetViewModel`、picker context、错误码和 action matrix 定版 | `docs/schemas/asset-view-model.schema.json`、`picker-context.schema.json`、`desktop/src/features/assets/model/ux0Contracts.ts`、`docs/contracts/asset-center-ux0-action-matrix.json` | 通过 |
| 2 | TemplateLayoutContract schema、有效/无效/缺字体 fixture、preview/render 映射与 golden 算法 | `docs/adr/003-template-layout-contract-v2.md`、`docs/schemas/template-layout-contract-v2.schema.json`、`tests/fixtures/ux0/template-layout/`、`docs/migrations/template-layout-uxd-gate-2026-07-18.json` | 通过 |
| 3 | VoiceProfile schema、迁移 dry-run、旧 session 对账、回滚设计、BGM 与 voice facet 隔离 | `docs/adr/004-voice-profile.md`、`docs/migrations/voice-profile-dry-run-2026-07-18.json`、`docs/migrations/asset-library-ux0-rollback-2026-07-18.json`、`tests/fixtures/ux0/voice-migration/` | 通过 |
| 4 | deferred upload 状态、finalize schema、三种重复策略、幂等/TTL/兼容用例 | `docs/adr/005-deferred-upload-finalize.md`、`docs/schemas/deferred-upload-*.schema.json`、`tests/fixtures/ux0/deferred-upload/cases.json`、`tests/asset_library_ux1_test.py` | 通过 |
| 5 | 重启后明确重新选择原文件重传，不声称断点续传 | `tests/fixtures/ux0/deferred-upload/cases.json`、`desktop/src/features/assets/components/AssetUploadQueue.tsx` | 通过 |
| 6 | cursor 排序元组、filter hash、index generation、query-consistent facets 和 mutation stale 行为 | `docs/adr/006-stable-cursor-facets.md`、`tests/fixtures/ux0/cursor-pages.json`、`tests/asset_library_ux0_contract_test.py` | 通过 |
| 7 | 当前版七项截图/录像、点击数、耗时和错误基线齐全 | `docs/migrations/asset-center-ux0-current-baseline-2026-07-18/report.json`、同目录 7 张截图与 `raw-video/` | 通过（基线含 3 项 observed error，已如实记录） |
| 8 | SMB UX 开关默认关闭，V2 内核不受影响，迁移不由 UI 开关控制 | `api/config.py`、`desktop/src/featureFlags.ts`、`desktop/src-tauri/src/main.rs`、`tests/asset_library_ux0_contract_test.py`、`docs/migrations/asset-library-ux0-rollback-2026-07-18.json` | 通过 |

## 可复现命令

```bash
uv run python scripts/ux0_gate.py --output docs/migrations/asset-library-ux0-gate-2026-07-18.json
uv run pytest -q tests/asset_library_ux0_contract_test.py tests/asset_library_ux1_test.py
```

门禁脚本会校验本复审记录的 `verdict=pass` 与八项证据条目；它不会修改业务 data root，也不会将目标用户研究标记为已完成。

## 后续边界

UX-A 通过只授权进入 UX-1，不授权默认开启 SMB UX。UX-C 的真实 picker→同槽回填→成片、UX-D 的发布 renderer 数值证据、UX-E 的五人研究、发布设备签署和灰度观察仍必须独立闭合。

```json
{
  "schema_version": "asset-center-uxa-formal-evidence-review-v1",
  "verdict": "pass",
  "evidence_items": 8,
  "target_user_study": false,
  "release_device_signoff": false
}
```
