# DH-DUAL-3 恢复、失败与真实桌面验收 Entry（2026-07-24）

## 状态

`entry_passed_with_boundary`。本 Entry 冻结重启/失败/人工接收矩阵和安全边界；只新增 contract、fixture 与隔离回归，不执行真实 Provider、浏览器、平台或最终发布。

## 冻结内容

- Provider task 未创建时允许恢复；已创建时必须复用/查询原 task，不能重复创建。
- success 在 Artifact 登记前、needs_review 和进程重启都必须保留可审计状态及输出指纹。
- 余额不足、timeout、无视频、字幕/封面失败和本地文件缺失均 fail closed，不允许人工 accept 或平台动作。
- 资产 revision 变化拒绝执行；模式切换不能复用旧 pending Run。
- Artifact 被篡改时 accept 拒绝；重复 accept 只返回已完成事实；accept 需要四类 V2 Artifact。
- `platform_actions=0`、`final_publish_clicked=false` 固定不变。

## 验证

- recovery contract/fixture：3 passed。
- Entry 未调用 Provider、TTS、浏览器、平台或最终发布；独立六维复审按用户要求延后至 Program 完成。

## 边界

- Entry 不等价真实桌面重启或真实 Provider 恢复通过；这些只在安全条件具备且有明确人工授权时执行。
