# DH-DUAL-0 Entry 独立六维复审（2026-07-24）

## 结论

- Gate：`PG-DH-A`
- 结论：`passed_with_boundary`
- P0：0
- P1：0
- 下一唯一 Stage：`DH-DUAL-1`
- 审查线程：`/root/dh_dual_entry_reviewer`
- 审查方式：只读，不修改代码，不调用 Provider，不执行浏览器或平台动作。

## 六维验证

| 维度 | 结论 | 验证依据 |
| --- | --- | --- |
| 需求完整性 | 通过 | 双模式、内容来源分离、V1/V2、workflow/media、安全、Artifact/质量和回滚边界均已冻结；PG-L 外部边界保持独立 |
| 逻辑正确性 | 通过 | contract/fixture 校验 mode-media-workflow、V1 resume、final preview/raw 角色、Registry mapping、双开关联合门控 |
| 边界情况 | 有界通过 | 已覆盖标题单独运行、媒体错配、视频过短、未 release workflow、revision drift、路径/密钥/provider_url 注入；MIME/geometry/timeout/no-output/mixed-scene 等留给后续实现 Stage |
| 代码质量 | 通过 | DH-DUAL-0 无业务代码改动；Entry 测试 Ruff check/format clean |
| 测试覆盖 | 通过 | Entry 4 passed；Entry/AC-5/Registry 聚合 22 passed；AC-5 API/Adapter/Artifact 47 passed；12 个既有 Pydantic 弃用警告 |
| 实际运行结果 | 通过且有边界 | Entry provider/browser/platform/final click 均为 0；既有 AC-5 image-mode 真实媒体基线可追溯；不宣称 video Provider smoke 或双模式生产闭环 |

## 证据与边界

- 方案 SHA：`30590fb985f9bceacd8b0896c75997486aff33c00fff6d0c73ec66931e40aa1a`。
- Entry QA：[`qa/DH-DUAL-0-entry-2026-07-24.json`](qa/DH-DUAL-0-entry-2026-07-24.json)。
- Contract：[`digital-human-video-input-v2.contract.json`](../../contracts/app-center/digital-human-video-input-v2.contract.json)。
- Fixture：[`digital-human-video-input-v2-fixtures.json`](../../contracts/app-center/fixtures/digital-human-video-input-v2-fixtures.json)。
- 既有 image-mode retry 基线只作为可追溯质量基线，不能替代视频模式真实 smoke。
- 最终发布自动点击保持 0；PG-L Windows 实机安装、产品签字、真实 rollback/WebView 继续 open。

## Gate 决策

关闭 `PG-DH-A` 为 `passed_with_boundary`，允许按台账唯一入口进入 `DH-DUAL-1`。后续 Stage 必须补齐：Registry 1.0→1.1 mapping 的运行时断言、真实双模式 Provider smoke、MIME/geometry/timeout/no-output 失败矩阵和双开关 readiness 集成测试。
