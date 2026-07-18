# ADR-005：Deferred Upload Finalize 与重复文件决策

- 状态：Accepted（UX-A 证据复审通过，可进入 UX-1）
- 日期：2026-07-18
- 范围：统一上传队列、重复文件、TTL、旧客户端兼容和重启恢复

## 状态机

```text
created → uploading → analyzing → uploaded
                                  └→ awaiting_duplicate_decision
                                      ├→ finalized
                                      └→ expired（24h TTL 后清理）
created/uploading/analyzing --restart--> failed(restart_recovery)
```

`uploaded`/`awaiting_duplicate_decision` 是已完成传输的业务状态，不能被 stale-upload 清理当作中断删除。重启后浏览器不能静默重新读取本地文件，因此产品只承诺“恢复队列/重新选择原文件重传”，不使用“断点续传”。真正 offset 续传另立契约。

## API

- `POST /api/v2/uploads` 传 `decision_mode: "deferred"`；
- `PUT /api/v2/uploads/{upload_id}/content` 只做传输、SHA 和媒体预检，不创建正式 asset；
- `POST /api/v2/uploads/{upload_id}/finalize` 按 `FinalizeUploadRequest` 完成入库。

旧客户端不传 `decision_mode` 时继续使用现有自动 finalize 兼容语义；新上传队列一律 deferred。状态、请求和响应 schema：`docs/schemas/deferred-upload-*.schema.json`。

## 三种策略

| 策略 | 结果 |
| --- | --- |
| `reuse_existing` | 删除临时文件，返回已有 asset/revision；上传时名称不覆盖已有资产 |
| `attach_revision` | 需要 `target_asset_id`，媒体类型一致，创建目标资产新 revision，保留版本事件 |
| `create_separate` | 创建独立 asset + revision；生命周期、归档和引用独立 |

策略与状态不匹配必须拒绝。finalize 需要幂等键和结果记录；重复请求返回第一次结果，不能重复创建 asset/revision。TTL 清理只处理过期的 deferred 记录，并留下可审计结果。

## 证据

`tests/fixtures/ux0/deferred-upload/cases.json`、`tests/asset_library_ux0_contract_test.py` 和 `docs/reviews/2026-07-18-asset-center-ux0-evidence.md`。
