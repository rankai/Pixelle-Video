# COORD-0 app_center.sqlite migration dry-run

## Boundary

在临时内存 SQLite 执行 `docs/contracts/app-center/app-center-v1.sql` 两次；只验证表/约束/幂等，不连接现有 `data` 或生产库。`app_schema_migrations` 记录版本；未来遇到高于当前版本的数据库必须拒写并保持原库不变。

## Evidence command

```bash
uv run pytest -q tests/coord0_contract_test.py -k sqlite_migrations
```

预期：空库创建、重复执行 no-op、遗留库不受修改、source/human/evidence 非法约束拒绝；临时连接关闭即回滚。实际输出记录在 `COORD-0-runtime-evidence.md`。
