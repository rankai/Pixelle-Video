# ADR-003：TemplateLayoutContract v2 单一布局与渲染权威

- 状态：Accepted（UX-A 证据复审通过，可进入 UX-1）
- 日期：2026-07-18
- 范围：模板编辑器、封面预览、PIL fallback、ASS 字幕和最终合成

## 决策

所有模板 revision 只保存并消费一份版本化 `TemplateLayoutContract`。规范化画布固定为 `canvas.width × canvas.height`，当前注册基础模板为 1080×1920；编辑器、预览和最终渲染都先把 UI 坐标按比例转换到规范化画布，再由 renderer 解析，禁止各处维护独立的 `cover_contract`/`subtitle_contract` 坐标来源。

契约模型与 JSON Schema：

- Python：`TemplateLayoutContract` in `api/schemas/asset_library_ux0.py`；
- JSON Schema：`docs/schemas/template-layout-contract-v2.schema.json`；
- 有效、未知字段、字体缺失和 golden fixture：`tests/fixtures/ux0/template-layout/`。

## 字体身份

字体只能来自 renderer 的注册表，保存稳定 `font_id`、family、weight、style 和 `font_sha256`。运行时解析以 `font_id + SHA-256 + weight` 为身份；缺失字体、未知字段、未注册 `font_token`、画布外布局和空安全区均拒绝保存/发布，不能静默 fallback。

## 预览/渲染 adapter

preview adapter 与 render adapter 读取同一 contract，返回同一 resolved 字体身份、布局框和 warnings。字体、字号、换行策略、安全区和字幕边距不允许由前端二次解释。模板 revision 与 renderer/schema 版本一同写入 `ResourceSnapshot`，旧任务继续使用旧 revision。

## Golden 验收算法

`golden.json` 固定示例文本和关键布局框。验收必须同时满足：

1. resolved `font_id/font_sha256/weight` 完全一致；
2. 标题框、字幕基线和安全区关键坐标的最大绝对误差 ≤ 2px；
3. alpha threshold 0.5 后 preview/render layout mask IoU ≥ 0.98。

## 拒绝与回滚

拒绝发生在保存 draft 或发布 revision 之前，不产生可被生产流选择的半契约模板。关闭 SMB UX 只回到当前 V2/旧页面；模板数据为向前兼容的可空字段，旧 snapshot 不重新解析新 contract。
