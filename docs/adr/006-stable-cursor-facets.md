# ADR-006：稳定 Cursor、Filter Hash 与 Query-Consistent Facets

- 状态：Accepted（UX-A 证据复审通过，可进入 UX-1）
- 日期：2026-07-18
- 范围：统一资产列表分页、排序、facets 与 mutation 后恢复

## 决策

游标是服务端签名且不透明的 `CursorEnvelope`，包含 `sort`、规范化 query 的 `filter_hash`、`index_generation` 和最后一条排序元组。客户端不得自行拼接 offset 或 tuple。

排序元组固定如下：

| sort | 元组 | 方向 |
| --- | --- | --- |
| `recent` | `last_used_at, updated_at, kind, resource_id` | 前两项 DESC，`last_used_at` NULLS LAST，后两项 ASC |
| `updated` | `updated_at, kind, resource_id` | `updated_at` DESC，后两项 ASC |
| `name` | `normalized_name, kind, resource_id` | 全部 ASC |

mutation 改变统一索引内容或排序时递增 `index_generation`。下一页若 generation 不一致返回 409 `cursor_stale`；filter/sort 与 cursor 不一致返回 400 `cursor_filter_mismatch`。前端保留当前选择和滚动锚点，只刷新第一页，不能拼接不同 generation。

## Facets

facets 与列表使用同一查询快照和 generation。计算 `kinds/statuses/tags` 时分别忽略自身维度约束，但保留其他约束；因此切换类型不会把其他分类错误显示为 0。结果同时返回 `total/next_cursor/filter_hash/index_generation/facets`。

## 可执行证据

- 参考实现：`pixelle_video/services/asset_library_cursor.py`；
- JSON Schema：`docs/schemas/library-cursor.schema.json`、`docs/schemas/library-page-facets.schema.json`；
- 同 generation 无重复/遗漏、mutation 后 `cursor_stale` 和 facet 自身维度忽略测试：`tests/asset_library_ux0_contract_test.py`；
- 输入 fixture：`tests/fixtures/ux0/cursor-pages.json` 与确定性 1000 条 seed。
