# DH-DUAL-0 Entry：数字人双模式与成片质量增强（2026-07-24）

## 状态

`passed_with_boundary`；`PG-DH-A` 已通过，台账唯一入口已切换到 `DH-DUAL-1/PG-DH-B_entry_pending`。

本 Entry 只冻结契约、fixture、基线和执行边界，不包含图片/视频双模式业务实现，不调用 RunningHub，不执行浏览器或平台动作。

## 变更请求与执行入口

- CR：`CR-DH-DUAL-MODE-001`
- 当前台账入口：`DH-DUAL-0/PG-DH-A_entry_pending`
- 原 `PROGRAM-ROLLOUT/PG-L`：`paused_external`；PG-L 仍 open，Windows 实机安装、产品签字和真实 rollback/WebView 边界不变
- 方案：[`2026-07-24-digital-human-dual-mode-and-quality-optimization-implementation-plan.md`](../../superpowers/specs/2026-07-24-digital-human-dual-mode-and-quality-optimization-implementation-plan.md)
- 方案 SHA-256：`30590fb985f9bceacd8b0896c75997486aff33c00fff6d0c73ec66931e40aa1a`

## 本 Entry 交付

1. `digital-human-video-input-v2.contract.json`
   - 分离内容来源与数字人素材模式；
   - 支持 `image_talking` 与 `video_lipsync`；
   - 冻结 V1.0.0 resume/V2 new-run 兼容；
   - 冻结 `final_video` 默认预览、raw video 诊断角色、字幕/封面质量要求；
   - 冻结 workflow profile allowlist、错误码、Provider 次数和最终发布安全边界。
2. `digital-human-video-input-v2-fixtures.json`
   - 图片/视频正向输入；
   - 自动文案已完成 Artifact；
   - 标题单独生成拒绝；
   - image/video media mismatch；
   - 视频过短、未 release workflow、路径/密钥注入、revision drift；
   - V1 blank project 和 selected title resume。
3. `digital_human_dual_mode_entry_contract_test.py`
   - 只读解析并校验上述契约和 fixture，不依赖 Provider。
4. 本 QA JSON
   - 记录 branch、HEAD、方案 SHA、测试、外部动作计数和明确边界。

## 验证结果

- `uv run pytest -q tests/digital_human_dual_mode_entry_contract_test.py`：4 passed；
- 应用中心 Entry/Registry 回归聚合：22 passed，12 个既有 Pydantic 弃用警告；
- 既有 AC-5 API/Adapter/Artifact 回归：47 passed，12 个既有 Pydantic 弃用警告；
- 两份 JSON 解析：passed；
- `git diff --check`：passed；
- `uv run ruff check tests/digital_human_dual_mode_entry_contract_test.py`：passed；
- `uv run ruff format --check tests/digital_human_dual_mode_entry_contract_test.py`：passed；
- 业务代码修改：0；
- Provider 调用：0；
- 浏览器/平台动作：0；
- 最终发布点击：0。

复用的 AC-5 image-mode 真实基线、文件 SHA、ffprobe 摘要和字幕抽帧路径已写入 [`qa/DH-DUAL-0-entry-2026-07-24.json`](qa/DH-DUAL-0-entry-2026-07-24.json)；这些不是本 Entry 新生成的 Provider 证据，也不替代后续视频模式 smoke。

## 未在本 Entry 声称完成

- 图片数字人真实 Provider smoke；
- 视频数字人真实 Provider smoke；
- 字幕、封面、动作、边缘和背景的真实视觉质量；
- 应用中心双模式 UI；
- Adapter/资产 resolver/workflow routing 业务实现；
- Windows PG-L 外部闭环；
- 任意平台上传或最终发布。

## 审查与下一步

独立审查线程 `/root/dh_dual_entry_reviewer` 已只读复验六个维度，确认 P0/P1=0；复审记录见 [`DH-DUAL-0-entry-review-2026-07-24.md`](DH-DUAL-0-entry-review-2026-07-24.md)。台账已切换到 `DH-DUAL-1`，下一步开始服务端双模式实现。
