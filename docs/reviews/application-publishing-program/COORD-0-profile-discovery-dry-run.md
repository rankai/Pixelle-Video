# COORD-0 profile discovery / migration dry-run

命令（只读，不打开数据库、不读取 cookie 内容、不移动 profile）：

```bash
for p in data/publish_browser/*; do
  [ -d "$p" ] || continue
  basename "$p"; du -sk "$p"; stat -f '%Sm' -t '%Y-%m-%dT%H:%M:%S%z' "$p"
  find "$p" -maxdepth 1 -name '*.lock' -o -name 'SingletonLock' | head -1
done
```

2026-07-19 脱敏结果：发现 1 个 `relative:data/publish_browser/douyin` 候选，124760 KiB，mtime `2026-07-18T22:40:05+08:00`，检测到 `SingletonLock`，结论 `defer_locked`；`writes_performed=0`。报告见 `docs/contracts/publishing/fixtures/profile-discovery-report-2026-07-19.json`，没有输出 cookie、账号身份或完整路径。

迁移规则：锁释放并由用户确认后才允许 copy→hash 校验→新 profile 登录验证；本阶段不搬迁、不清理、不做 cookie down-migration。

