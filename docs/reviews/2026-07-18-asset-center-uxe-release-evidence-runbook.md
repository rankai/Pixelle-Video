# UX-E 外部证据收口 Runbook

本 runbook 只用于真实 release device、真实目标用户和真实灰度观察。自动化桌面门禁、内部同事演练和合成媒体不能填充外部证据字段。

## 1. 固定环境

在开始招募前冻结以下信息，并写入 `asset-center-uxe-release-evidence-template-2026-07-18.json`：

- release device ID、app version、commit SHA、窗口 `1440×900`、主题 `fresh`；
- 本地服务 revision；
- 固定 1000 条数据集及 SHA-256。数据集必须包含七种类型、相似名称、归档项、重复文件、极端比例图片和缺失预览；
- 开启 `PIXELLE_ASSET_CENTER_SMB_UX=true`，同时保留旧 V2 回滚入口。

建议先运行本地技术门禁确认版本没有漂移：

```text
uv run python scripts/asset_center_uxe_desktop_gate.py --output-dir docs/migrations/asset-center-uxe-desktop-gate-2026-07-18
uv run python scripts/template_layout_gate.py --output docs/migrations/template-layout-uxd-gate-2026-07-18.json
```

## 2. 用户任务与记录

每位参与者独立完成相同起始状态和相同任务说明；观察员只记录，不提示。每项记录开始时间、结束时间、意图动作数、成功/失败、错误码、是否误选、是否重复上传和录像路径。写入 JSON 时，`task_results` 必须包含 `T1`～`T8`，每项至少有 `task_id`、`success`、`elapsed_seconds`、`intent_actions` 和 `error_code`。

| ID | 任务 | 成功条件 |
| --- | --- | --- |
| T1 | 在生产步骤找到指定门店图片并确认使用 | 正确图片写入目标 slot，无误选残留 |
| T2 | 从生产步骤上传一张合规图片并回填 | 上传完成并回到原 slot |
| T3 | 批量上传 10 张商品图片并统一打标签 | 10 项完成，失败项不重传，标签正确 |
| T4 | 添加封面+演示视频数字人并选择场景 | 预览正确场景后明确确认 |
| T5 | 修改品牌 Logo、BGM、地址并应用 | 所有字段保存并进入当前生产任务 |
| T6 | 预览模板字幕/封面位置并用于成片 | 预览、保存和最终选择的模板一致 |
| T7 | 触发上传失败、取消或重启恢复 | 成功项不重传，取消无 usage，重启提示重新选原文件 |
| T8 | 归档后恢复已被任务引用的资产 | 资产恢复，旧 snapshot 仍可回放 |

角色至少为 2 位门店老板、2 位店长/运营、1 位熟练视频运营。每位参与者必须填写 `independent=true`、成功率、中位数、P95、任务明细和录像路径；不能用平均值替代中位数/P95。

## 3. Glyph 与真实 MP4

在同一 release device、同一窗口和同一字体安装/打包状态下，对真实模板成片抽取固定帧。保存：

- 输入模板 revision、renderer/schema 版本和字体 SHA；
- 每个样本的真实 MP4 帧路径；
- 与 golden 的 glyph mask IoU，取所有样本的最小值；
- 只有 `observed_min_iou >= 0.98` 且 `sample_count > 0` 才能通过 validator。

本地 `contract-box IoU=1.0` 或 `glyph_mask_iou=null` 都不能填充该字段。

## 4. 灰度观察与回滚

在真实设备开启 SMB UX 后记录启用时间和观察窗口天数，同时记录任务成功率、搜索无结果率、picker 取消率、上传恢复率、前后跳转次数和成片成功率。至少完成一次关闭 `ASSET_CENTER_SMB_UX` 的回退演练，并证明旧 V2 健康、数据和 snapshot 可读。

观察窗口结束后，由 reviewer 填写签署时间；只有所有外部字段齐全时运行：

```text
uv run python scripts/validate_asset_center_uxe_release_evidence.py \
  --input docs/migrations/asset-center-uxe-release-evidence-template-2026-07-18.json \
  --output docs/migrations/asset-center-uxe-release-evidence-validation-2026-07-18.json
```

validator 返回 `pass` 前，`default_rollout_authorized` 必须保持 `false`。禁止手工把模板状态改成 `pass` 来绕过校验。
