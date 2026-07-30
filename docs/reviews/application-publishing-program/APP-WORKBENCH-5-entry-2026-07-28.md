# APP-WORKBENCH-5 数字人工作台 Entry

- Stage：`APP-WORKBENCH-5`
- Change Request：`CR-APP-WORKBENCH-001`
- Gate：`PG-AW-F_entry_in_progress`
- 日期：2026-07-28

## Entry 冻结

本阶段只优化数字人应用工作台交互，复用已通过的数字人双模式、质量门和恢复/失败契约：

- 图片模式 `image_talking` 为默认；视频模式 `video_lipsync` 为 stable 但不默认；
- 输入固定项目、ContextSnapshot、内容来源版本、数字人 scene 和 asset revision；
- 允许本次脚本、发布标题、描述、封面标题、话题和字幕开关；不允许输入 Provider、workflow、路径、Cookie 或 key；
- 右侧展示运行状态、进度投影、最终视频预览、封面、发布文案和口播稿四类 Artifact；
- 重启通过本地 pointer/pending idempotency 恢复，不创建第二个 AppRun；失败仅允许受控重试；
- `readable_v2` 字幕预设为唯一受信预设；字幕开关只改变交付字段，不改变 Provider 事实源；
- 最终发布保持人工点击，工作台不得打开第三方平台。

## Entry 检查

已核对以下现有契约与实现，允许进入 Stage5 实现/体验收口：

1. `digital-human-video-input-v2.contract.json`：双模式素材、revision、workflow profile 和禁止字段；
2. `digital-human-quality-entry.contract.json`：标题/封面/字幕/四 Artifact 完整性；
3. `digital-human-dual-mode-recovery.contract.json`：重启、失败、幂等和人工接收；
4. `digital-human-dual-mode-rollout.contract.json`：默认图片、视频非默认、双开关和回滚；
5. `DigitalHumanApplicationView` 已接入共享 `AppWorkbenchShell`，窄屏使用配置/结果 Tab；
6. 结果面板新增四 Artifact 交付状态，输入区新增“更多配置/添加可读字幕”且向后兼容旧 pending payload。

## 明确不做

- 不重写 TTS、RunningHub、后期合成或真实 Provider 质量门；
- 不执行真实第三方发布，不自动点击最终发布；
- 不引入第二套模型、账户或媒体资产事实源；
- 不提前进入 `APP-WORKBENCH-6` 跨应用交付统一化。

## Entry 命令

```text
uv run pytest -q \
  tests/digital_human_dual_mode_entry_contract_test.py \
  tests/digital_human_dual_mode_recovery_contract_test.py \
  tests/digital_human_dual_mode_recovery_test.py \
  tests/digital_human_dual_mode_server_test.py \
  tests/digital_human_quality_entry_contract_test.py \
  tests/digital_human_quality2_entry_contract_test.py \
  tests/digital_human_quality_impl_test.py \
  tests/digital_human_video_quality_gate_test.py \
  tests/app_center_ip_broadcast_artifact_test.py \
  tests/app_center_ip_broadcast_desktop_entry_contract_test.py
84 passed, 7 warnings
```

Entry 通过后，Stage5 只需完成领域 UI/结果交互、定向测试、视觉证据和独立六维复审。
