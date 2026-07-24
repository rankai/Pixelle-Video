# DH-DUAL-1 服务端双模式实现（2026-07-24）

## 状态

`implementation_pass_with_boundary`，独立六维复审已确认 P0/P1=0，`PG-DH-B` 可通过。

当前台账唯一入口：`DH-DUAL-1/PG-DH-B_entry_pending`。

## 本批实现

- 新增 V1/V2 normalizer：自定义文案、已有文案 Artifact、V1 blank project 和 selected-title resume-only 均有明确语义。
- 新增服务端 workflow profile catalog：桌面只提交 `mode + workflow_profile`，内部 workflow revision/key 不接受前端覆盖。
- 新增 trusted media binding 校验：mode/media type、scene media type、asset revision、ready、MIME、图片短边、视频尺寸和时长均 fail-closed。
- 接入现有 `IpBroadcastAppAdapter`：V2 AppRun 使用 `1.1.0`、固定 source revision 和 binding version；旧 V1 仍保持 `1.0.0` seam。
- Registry 支持 `1.0.0`/`1.1.0` input-schema mapping；SQLite seed 扩展支持版本，保持旧 manifest/旧 Run 可读。
- 新增后端/桌面双开关联合门控，desktop-only 不得绕过 backend readiness。
- 扩展业务 payload 禁止字段，阻断 provider URL、token、路径和 RunningHub 标识进入应用事实。
- V2 输入严格拒绝错误字段类型、客户端 workflow/path 注入，并在 provider/retry 入口重新检查联合开关；素材场景状态、profile 归属和 pinned revision 均 fail-closed。

## 验证结果

- DH-DUAL server + Entry + AC-5 adapter/API/Artifact/Registry 聚合：`86 passed`，12 个既有 Pydantic 弃用警告；
- Ruff check：passed；
- Ruff format check：passed；
- Contract/fixture/QA JSON parse：passed；
- `git diff --check`：passed；
- Provider calls：0；browser/platform actions：0；final publish clicks：0。

## 明确边界

- 本批没有调用 RunningHub/TTS，不代表图片或视频 Provider smoke 已通过；
- asset resolver 已建立服务端 AssetLibrary seam，并由 fake trusted resolver 覆盖确定性测试；场景 pinned revision 读取已验证；真实素材库数据与 UI 资产选择留给 DH-DUAL-2；
- video profile 仍为 candidate，真实 live/release gate 留给 DH-QUALITY-2；
- 字幕、封面、最终成片 Artifact 和失败重试闭环留给 DH-QUALITY-1/DH-DUAL-3；
- PG-L Windows 外部闭环、平台上传和最终发布自动点击边界不变。

## 下一步

PG-DH-B 通过后，切换到 `DH-DUAL-2` 桌面双模式与资产选择器实现；本批仍不调用真实 Provider/浏览器/平台。
