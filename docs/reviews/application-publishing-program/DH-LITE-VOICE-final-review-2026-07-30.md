# DH-LITE-VOICE 独立六维终审

- 日期：2026-07-30
- Change Request：`CR-DH-LITE-VOICE-001`
- Stage：`DH-LITE-VOICE`
- Gate：`PG-DLV-D`
- 审查角色：独立严格审查线程
- 审查约束：只验证和出具修复清单，不修改代码
- 最终结论：`PASS`
- 严重性：`P0=0`、`P1=0`、`实质性 P2=0`

## 1. 迭代审查记录

### 第一轮

发现并修复：

- 人物默认声音在 Run 重验证时被错误重分类为 `run_override`，会导致固定输入 fingerprint 漂移；
- 修复后保留创建时的 `resolution_source`，人物默认、本次覆盖和系统推荐三类 create → revalidate 均保持一致。

### 第二轮

发现并修复：

- VoiceProfile 后续换绑到新音频资产时，历史 Run 仍可能通过当前 VoiceProfile 间接解析新资产；
- 修复后 session 同时固定 VoiceProfile、原音频资产 ID 和原 revision；Provider 路径只使用已固定的 `audio_asset_id + audio_revision_id`。

### 第三轮

发现并修复：

- Desktop 恢复历史 Run 时，只能恢复本次覆盖声音，人物默认声音会被误显示为系统推荐；
- 修复后指针只保存用于展示的 `voice_profile_id + voice_name + resolution_source`，不保存文件路径或媒体 revision；
- 展示快照只在 `app_run_id + session_id + source_revision + context_snapshot_id` 与服务端 Run 校验通过后恢复；
- 人物默认、本次覆盖、系统推荐三类重启恢复均显示创建时固定的声音；运行中的换声按钮禁用。

## 2. 六维结论

1. 需求完整性：轻应用主路径、图片/视频自动识别、资产库默认声音、本次换声、恢复默认和人工最终发布边界均符合方案。
2. 逻辑正确性：三类声音来源均固定解析来源；VoiceProfile 换绑资产或 revision 后，历史 Run 继续使用原固定音频。
3. 边界情况：公共输入不能伪造服务端声音快照；授权、归档和 revision 缺失失败关闭；pending、retry、restart 和旧 Run 兼容有覆盖。
4. 代码质量：声音解析、固定重验证和 Provider 文件解析职责分离；Desktop 展示快照不包含内部媒体路径或 revision。
5. 测试覆盖：后端聚合 `81 passed, 12 warnings`；Desktop `2 files / 25 passed`；Ruff 与 `git diff --check` 通过。
6. 实际运行与体验：真实 Browser 已验证轻量主路径、折叠设置和无技术字段泄漏；390、900、1280、1440 宽度无水平溢出；production build 通过。

## 3. 放行与边界

`PG-DLV-D` 可登记为 `passed`，`DH-LITE-VOICE` Stage 可以关闭。

保留的非阻塞 P3 建议：

- 未来进入多窗口或多租户并发后，可由 Run 读接口直接返回只读声音展示摘要，替代当前本地单组织下与 Run 身份绑定的 Desktop 展示快照。

本阶段没有执行新的付费 RunningHub 调用、外部平台发布或最终发布按钮自动点击。Windows 实机、产品负责人签字和真实平台 rollback / WebView SLA 继续属于 `PROGRAM-ROLLOUT/PG-L`。
