# AC-4 抖音图文 implementation batch 3 独立六维复审（2026-07-20）

状态：`implementation_pass_with_boundary`

评审人：独立严格审查线程 `/root/pg_a_closure_reviewer_v3`（只读审查，未修改代码）。

## 六维结论

1. 需求完整性：本批次范围内完成 `carousel_package` → PublishPackage V2 → `publish_package_ref` handoff；单页 retry 生成新 page/package ArtifactVersion，旧 PublishPackage 与旧 ref 失效；flag-off、错误映射和失败补偿均有证据。
2. 逻辑正确性：PublishPackage 视频/图文媒体形态互斥；来源版本必须属于当前项目；非法/重复 page version fail-closed；retry 失败会回滚新 ArtifactVersion，并对已创建的新 PublishPackage 做失效补偿。
3. 边界情况：flag 关闭返回 `APP_NOT_READY`；混合媒体公共 API 返回 422；旧版本文件和历史 ref 不被覆盖；真实平台动作仍未触发。
4. 代码质量：复用 FastAPI、SQLite、既有 PublishPackage/LLM 事实源；没有引入第二模型配置源、浏览器运行时或平台 selector；Ruff 与 diff check 通过。
5. 测试覆盖：carousel source fixture、模型互斥负例、retry 成功/失效、retry 注入失败补偿、flag-off、Publish API 422、既有 app-center/publish/coordination 回归均覆盖。
6. 实际运行结果（batch 3 关闭时快照）：后端相关聚合 `173 passed`；前端 5 files/23 tests；`npm run build`、Ruff、`git diff --check` 均通过。随后 PG-H 追加 E2E、下载回归和桌面交互断言后，最新累计基线为后端 `175 passed`、前端 5 files/24 tests，详见 `PG-H-entry-and-implementation-2026-07-20.md`。

## 问题清单

- P0：0。
- P1：0。
- P2：补偿回滚后的新渲染文件清理、JSON Schema 同类 media ref 数量约束、并发 retry 输出路径冲突、真实文件保留的更细集成断言；不阻塞本批次。

## Gate 边界

本结论只关闭 AC-4 implementation batch 3，不关闭 PG-H，也不允许进入 AC-5。真实抖音扫码/第三方授权、真实上传、描述/话题/封面 live smoke、最终人工发布和完整图文→发布中心桌面 E2E 仍按台账后续入口或人工暂停点处理。
