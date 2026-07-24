# DH-DUAL-2 桌面双模式与素材体验 Entry（2026-07-24）

## 状态

`entry_passed_with_boundary`。本 Entry 已确认可以进入桌面实现；当前唯一工作入口仍为 `DH-DUAL-2 / PG-DH-C`。

## Entry 结论

- 上游 `DH-DUAL-1 / PG-DH-B` 已由独立六维复审确认 `implementation_pass_with_boundary`，P0/P1=0，服务端双模式契约、V1/V2 mapping、联合 feature gate 与 pinned revision seam 已可供桌面消费。
- 本阶段范围冻结为桌面数字人入口、图片/视频模式 Tab、真实 AssetLibrary scene 选择、媒体类型过滤、预览、revision/输入恢复、结果交付区和统一视觉；不改旧 `/ip`，不改默认 flag，不调用 Provider。
- V2 桌面 payload 只允许服务端定义的 `mode`、`portrait_id`、`scene_id`、`asset_revision_id` 和 `workflow_profile`；浏览器路径、Provider URL/token、第三方 workflow 标识仍由服务端拒绝。
- PG-DH-C 的实际放行条件冻结为：Vitest、desktop build、1440×900/1280×800/窄窗口边界、真实桌面视觉与交互证据、独立六维复审 P0/P1=0；真实 Provider 与最终发布不属于本阶段。

## 允许实现清单

1. 在联合 flag 和后端 Registry readiness 同时通过时显示数字人应用；默认关闭时保持旧入口。
2. 图片数字人只确认图片 scene，视频数字人只确认视频 scene，并在模式切换时清理不兼容素材但保留已填文案。
3. 素材选择后锁定 scene 的 `source_revision_id`，展示媒体类型、可用的分辨率/时长/质量信息。
4. pending/run 恢复必须恢复 V2 mode、source input、scene 和 revision；重复点击不创建第二个 Run。
5. needs_review/completed 默认交付 `final_video`、`cover`、`publish_copy`，原始数字人视频只放诊断区域，下载默认指向 `final_video`。

## 明确边界

- 本 Entry 不授权 TTS、RunningHub、任何真实 Provider、平台浏览器、上传或最终发布。
- 本 Entry 不宣称视频唇形 workflow 已达到发布质量；真实成片质量、字幕、短封面与 Artifact 完整性留给 `DH-QUALITY-1/DH-QUALITY-2`。
- `PROGRAM-ROLLOUT / PG-L` 的 Windows 安装、产品签字、第三方授权和最终发布安全边界保持不变。
