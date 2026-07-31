# APP-RESULT-HISTORY-1 独立六维终审

## 结论

- Gate：`PG-ARH-B PASS`
- P0：0
- P1：0
- P2：0
- 审查线程：`/root/app_result_history_stage1_final_review`
- 范围：仅后端只读记录投影与 API。

## 六维验证依据

1. 需求完整性：一个 AppRun 投影为一个记录块；3 条文案、6 条标题及已保存 25 条候选均完整返回；5 页图文聚合为一个成品；video、cover、publish_copy、spoken_script 聚合为一个视频成品。
2. 逻辑正确性：严格按 `result_available_at DESC, app_run_id DESC` keyset；canonical Base64URL、128-bit HMAC、固定错误文案与逐行 SHA-256 revision 共同保证篡改失败关闭和结果集变化显式 stale。
3. 边界情况：固定 23 条多页无重复遗漏；running→completed、相同 MAX 时间戳碰撞均拒绝旧 cursor；创建/完成时间逆序、filter/cursor 错配、旧超长文本和 legacy 记录均有覆盖。
4. 代码质量：投影服务与 repository 分层；无新事实表、migration、历史补写或外部调用；Ruff、format、diff 通过。
5. 测试覆盖：projection 11 passed；projection+Entry 32 passed；应用中心聚合回归 191 passed。
6. 实际运行：FastAPI JSON Schema 与 flag-off 404 通过；SQLite 全表快照读取前后相同；每页固定 5 条 SELECT，三次读取 15 条；100 条记录下审查实测 P95 1.493ms，低于 350ms 预算。

## 审查修复循环

- P1：排序曾偏离冻结契约 → 恢复结果可用时间排序并增加 stale revision。
- P1：非 canonical Base64URL 可解码为同一字节 → 强制 canonical 重编码比较。
- P1：聚合 revision 可发生 MAX 时间戳碰撞 → 改为全部可见行固定顺序 SHA-256，并新增确定性遗漏复现测试。
- P1：cursor 无效文案偏离冻结契约 → 统一为“历史记录位置已失效，请重新加载”并精确断言。

## 边界

本 Gate 不证明桌面文本记录流、媒体文件流、图文/视频真实预览、Feature flag 回滚、真实可视化、Windows 实机或产品签字；这些由后续 `APP-RESULT-HISTORY-2` 至 `4` 验证。
