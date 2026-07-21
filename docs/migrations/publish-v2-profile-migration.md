# Publish V2 profile migration dry-run

## Scope

COORD-0 只建立 `publish_accounts`、`publish_packages_v2`、`publish_runs_v2`、`publish_step_results` 的 additive schema，并完成只读 profile discovery。既有 V1 `publish_packages`、旧 session、Chromium profile 和 cookie 不迁移、不删除、不覆盖。

## Procedure

1. 在临时 SQLite 数据库执行 `docs/contracts/publishing/publishing-v2.sql` 两次，确认第二次为 no-op。
2. 插入 artifact source 与 legacy session 两种合法 fixture；插入一个 `waiting_for_human` run。
3. 尝试违反 source-kind、human confirmation、evidence redaction 三组约束，必须失败且数据库保持可用。
4. 删除临时数据库；生产数据库、profile、cookie 不触碰。

Profile discovery 使用 `docs/reviews/application-publishing-program/COORD-0-profile-discovery-dry-run.md` 的只读命令，输出候选目录、平台、大小、mtime、锁状态和迁移结论；当前发现的 douyin 候选被锁定，结论为 `defer_locked`，`writes_performed=0`。

## Rollback

只删除临时数据库即可。生产发布 V2 flag 保持关闭；若未来实际迁移失败，停止新 V2 run、保留新表只读、继续使用 V1 adapter，不清理 profile/cookie，不自动发布。
