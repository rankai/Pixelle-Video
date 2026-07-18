# 企业资产库 V2 阶段 0 / 门禁 A 验收记录

- 日期：2026-07-17
- 结论：**通过（GO to Stage 1）**
- 范围：ADR、数据契约、迁移基线、manifest 备份/恢复、feature flag、自动化验证
- 约束：本记录只批准阶段 1；不批准提前启用 V2 UI、迁移全部类型或清理旧实现

## 验收项

| 验收项 | 状态 | 证据 |
|---|---|---|
| 资源边界 ADR | 通过 | `docs/adr/001-enterprise-asset-library-v2.md` |
| Python 数据契约 | 通过 | `api/schemas/asset_library_v2.py`，extra 字段默认拒绝 |
| TypeScript 数据契约 | 通过 | `desktop/src/features/assets/model/assetLibraryV2.ts` |
| V2 feature flag | 通过 | `api_config.asset_center_v2_enabled == False`；`VITE_ASSET_CENTER_V2` 默认关闭 |
| 旧数据基线 | 通过 | `docs/migrations/asset-library-stage0-baseline-2026-07-17.json` |
| 迁移采集器 | 通过 | `scripts/assets_v2_baseline.py`、`collect_baseline()` |
| manifest/媒体校验 | 通过 | `backup_manifests()` 校验 manifest SHA-256；基线同时记录每个引用媒体文件 SHA-256 |
| manifest 恢复 | 通过 | `restore_manifests()`，恢复前校验备份索引 |
| 阶段 0 自动化测试 | 通过 | `4 passed` |
| 全量 Python 回归 | 通过 | `307 passed` |
| Python 静态检查 | 通过 | `uv run ruff check ...` |
| 桌面端构建 | 通过 | `npm run build`（tsc + vite build） |

## 真实数据基线

由 `scripts/assets_v2_baseline.py` 在当前 `data/` 执行：

- 视频 manifest：2 条，引用文件缺失 0。
- 图片 manifest：尚不存在，记录为 0；阶段 1 负责建立新图片资产入口。
- 数字人 manifest：2 条，引用文件缺失 0。
- 音色 manifest：2 条，引用文件缺失 0。
- 品牌 manifest：1 条，引用文件缺失 0。
- `missing_files`：0。
- 原始媒体未移动、未修改。

基线中的 manifest SHA-256 和 legacy ID 已写入 `docs/migrations/asset-library-stage0-baseline-2026-07-17.json`。实际备份目录使用临时 rollback 目录，不纳入仓库；后续迁移运行必须重新生成带时间戳的备份目录。

## 阶段 1 授权边界

门禁 A 通过后可以开始：

1. 图片/视频 SQLite repository、revision/variant 表和迁移日志。
2. 图片/视频 upload session、流式 `.part` 文件、哈希、取消和重启恢复。
3. 图片/视频 v2 列表、详情、归档 API。

仍然禁止：

- 默认开启 `asset_center_v2`。
- 删除旧 manifest 或移动原始媒体。
- 并行迁移音色、数字人、品牌、模板。
- 删除旧资产 UI 或旧接口。
- 跳过阶段 2 的“资产管理 → 生产选择 → 成功渲染”门禁 B。

## 下一道门禁

阶段 1 完成后，先验证图片/视频迁移对账、流式上传内存行为、重启恢复和旧接口兼容；然后进入阶段 2 的端到端闭环。只有闭环成功渲染并且 usage/snapshot 对账通过，才能申请门禁 B。
