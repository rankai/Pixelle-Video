# DH-DUAL-3 恢复、失败与人工接收业务实现（2026-07-24）

## 状态

`implementation_pass_with_boundary`。恢复/失败/人工接收矩阵已落地并通过隔离回归；不代表真实 Provider、真实 Tauri/sidecar 或平台发布已经验收。

## 已实现

- V2 执行、重试和本地隔离执行前重新校验 canonical content source、数字人 scene/asset revision、delivery；资产 revision 变化在 Provider/媒体执行前拒绝。
- Provider task 已存在且仍未产出视频时 fail closed；running 重启转为可审计失败，保留 task identity，必须先登记根因 retry plan。
- `needs_review` 重启复用原 Artifact IDs 和指纹，不重复生成；V2 accept 强制 video/cover/publish_copy/spoken_script 四类 generated Artifact。
- Artifact 集合不完整、spoken_script schema 无效、文件/版本绑定异常和指纹篡改均拒绝 accept；重复 accept 只返回已完成事实。
- Provider 失败时持久化 task id、失败状态和观察错误；余额不足/timeout/无视频等路径不触发平台动作。
- 最终发布仍只停留在人工确认边界，`platform_actions=0`、`final_publish_clicked=false`。

## 验证

- DH-DUAL-3 contract/fixture/recovery：6 passed。
- 数字人、质量、应用中心、发布聚合：138 passed，12 个既有 Pydantic 弃用警告。
- Ruff、format、JSON、`git diff --check`：通过。

## 边界

- 未执行真实 RunningHub/TTS、真实桌面关闭重开、真实平台动作或最终发布；这些外部证据仍按原协调台账暂停点处理。
- 本批没有开启默认双模式 flag，也没有改变 PG-L Windows/产品签字/真实 rollback 外部等待。
- 独立六维复审按用户要求延后至 Program 完成。
