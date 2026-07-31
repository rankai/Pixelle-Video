# APP-RESULT-HISTORY-1 后端只读投影实施证据

## 结论

- Stage：`APP-RESULT-HISTORY-1 / READ_PROJECTION_AND_API`
- Gate：`PG-ARH-B_passed`
- 当前结论：实现、主线程验证与独立六维审查均完成，P0/P1/P2=`0/0/0`。
- 范围：仅新增 AppRun/Artifact/ArtifactVersion 只读投影、批量查询、稳定 cursor、Pydantic 响应和 GET API；未修改生成、编辑、重试、媒体生产或发布写路径。

## 实现事实

1. `ResultHistoryProjectionService` 将一个 AppRun 投影为一个记录块。
2. 门店营销文案完整保留实际 `variants`；爆款标题完整保留已持久化 `candidates`，不会因当前请求数量上限截断历史事实。
3. 抖音图文以 `carousel_package` 为唯一成品，将 `carousel_page` 聚合为页数和预览引用，不拆成多条记录。
4. 数字人口播以 `video` 为唯一成品，将 `cover`、`publish_copy`、`spoken_script` 聚合为详情能力，不拆成多条记录。
5. `current_app` 默认只读当前应用；`all_results` 显式查看项目全部四应用结果。
6. cursor 严格按冻结契约的 `(result_available_at, app_run_id)` 倒序 keyset 分页；以 128-bit 截断 HMAC 防误改，拒绝非 canonical Base64URL，并同时绑定 project、scope、app、result_shape、status 和当前结果集 revision。revision 对按 `app_run_id` 固定排序的全部可见记录之状态、版本、创建/更新/完成/归档时间做 SHA-256 指纹，避免聚合 token 的时间戳碰撞漏检。翻页期间只要排序或成员事实发生变化，后端明确返回 `APP_RESULT_CURSOR_STALE`，要求刷新，而不是静默重复或遗漏。项目隔离仍由每条 SQL 的 `project_id` 条件执行，cursor 不是授权边界。
7. completed/needs_review 的旧记录若缺少可安全展示的业务事实，仅该记录降级为“这条旧记录暂时无法预览”，页面继续返回 200。
8. 后端 flag `PIXELLE_APP_RESULT_HISTORY_V1` 默认关闭；关闭时新 GET API 返回 404，不影响旧结果区。

## 查询与零写证据

- 最新一页固定为：
  - 项目存在检查 + 结果集 revision + AppRun keyset 查询；
  - 当前页 Artifact 批量查询；
  - 当前 ArtifactVersion 批量查询。
- 完整四结果页面实测为 5 条 SELECT；连续读取三次为 15 条 SELECT，没有随记录数增长的 N+1。
- 连续三次 service 读取及一次真实 FastAPI GET 前后，对 SQLite 所有非系统表逐行快照比较完全一致。
- 未新增数据库表、字段、索引或 migration。

## 业务基数证据

| 应用 | 一次 AppRun 的结果 |
|---|---|
| 门店营销文案 | 1 个记录块，块内 3 条文案 |
| 爆款标题 | 1 个记录块，块内 6 条标题；另验证已保存 25 条时完整返回 25 条 |
| 抖音图文 | 1 个记录块，1 个五页图文成品 |
| 数字人口播 | 1 个记录块，1 个 22.4 秒视频成品，封面/发布文案/口播稿为详情 |

## 验证

- `uv run pytest -q tests/app_result_history_projection_test.py`
  - 结果：`11 passed`
- `uv run pytest -q tests/app_result_history_projection_test.py tests/app_result_history_entry_contract_test.py`
  - 结果：`32 passed`
- `uv run pytest -q tests/app_center_*test.py tests/app_result_history_*test.py tests/brand_project_stage4_test.py`
  - 结果：`191 passed`
- `uv run ruff check ...`
  - 结果：passed
- `uv run ruff format --check ...`
  - 结果：passed
- `git diff --check`
  - 结果：passed
- 本地 100 个 AppRun、读取最新 10 条：
  - `2.159 ms`
  - 预算：`< 350 ms`
- JSON Schema：
  - service 四业务形态通过 block/page schema；
  - FastAPI 实际 JSON 通过 page schema。

## 明确边界

- 本 Stage 尚未把桌面右侧结果区切换到新 API。
- `cover_url / preview_url / poster_url / playback_url` 仅冻结为同源相对 API 引用；真实文件流、图文预览和视频播放在 `APP-RESULT-HISTORY-3` 实现。
- 视频时长优先读取已保存媒体元数据；没有元数据时可由固定口播稿估算，仅用于列表摘要。真实播放器时长在媒体预览阶段复核。
- 列表严格按 `result_available_at DESC, app_run_id DESC` 排序。生成状态或完成时间在两次翻页请求之间发生变化时，旧 cursor 会被判为 stale 并提示刷新；固定快照下验证 23 条记录无重复、无遗漏。
- 没有调用 LLM、TTS、RunningHub 或发布平台；最终发布点击为 0。
- Windows 实机、产品签字和真实 rollback/WebView SLA 仍保留在暂停的 `PROGRAM-ROLLOUT/PG-L` checkpoint。
