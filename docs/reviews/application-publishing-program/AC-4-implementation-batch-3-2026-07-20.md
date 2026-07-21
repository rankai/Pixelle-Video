# AC-4 抖音图文 implementation batch 3（2026-07-20）

状态：`implementation_in_progress`（batch 3 已启动；PG-H 未关闭）

## 本批次入口与范围

- 只在现有 AppCenter/Artifact/AppRun 与 PublishPackage V2 契约内接入 `carousel_package`，建立可追溯的 `publish_package_ref`，不直接调用平台浏览器。
- 单页重试必须写入新的 `ArtifactVersion`，更新可发布包引用并让旧包失效；旧文件保留为历史版本，不得被静默覆盖。
- 补 `douyinCarousel` flag-off 回归：关闭 flag 后应用不可执行/不可误展示，既有文案、数字人、发布和模板路径保持通过。
- 继续复用 FastAPI、SQLite、既有发布服务和既有模型配置；不新增模型配置源、管理员控制台或第三方平台动作。

## 本批次禁止范围

- 不执行抖音扫码、第三方授权、真实上传、字段回读或最终发布。
- 不实现 PG-H 之外的 AC-5 数字人口播扩展，不改变 PublishRun 核心状态机。
- 不将本批次的本地/fixture 证据称为真实平台或完整 PG-H 通过。

## 计划证据

- PublishPackage handoff 请求/引用与来源 ArtifactVersion 约束测试。
- 单页 retry 的新版本、旧 package 失效、文件保留和失败补偿测试。
- `douyinCarousel` flag-off 与既有应用/发布回归测试。
- 后端、桌面端回归、Ruff、`git diff --check`，再交独立六维审查。

## 已实现内容（等待独立审查）

- `PublishPackageV2` 支持二选一媒体形态：既有单视频 `video_manifest`，或 `carousel_manifests` 图片序列；`carousel_package` 会展开为 package/page ArtifactRef，并固定来源版本集合。
- PublishPackage V2 repository/service 已加入 `carousel_manifests_json`、carousel 文件安全预检/verify、来源版本查询，以及可追溯的 `publish_package_ref` Artifact/ArtifactVersion handoff。
- 单页 retry 接口会创建新的 page ArtifactVersion 与 package ArtifactVersion，重新生成新的 PublishPackage，并让引用旧页版本的旧包与旧 `publish_package_ref` 失效；失效通过追加 ArtifactVersion 记录，旧版本文件与历史引用仍保留。
- `douyinCarousel` flag-off 已覆盖注册表 disabled/readiness 与 retry API `APP_NOT_READY`；既有应用中心、发布核心和协调契约回归未退化。
- OpenAPI、JSON Schema、TypeScript types、SQLite storage contract/SQL 与 carousel source fixture 已同步。

## 验证结果

- 后端 AC/app-center/publish/coordination 聚合（batch 3 关闭时快照）：`173 passed`，12 个既有 Pydantic deprecation warnings。
- 前端（batch 3 关闭时快照）：5 个 Vitest 文件、23 个测试通过；`npm run build` 通过。
- PG-H 追加本地 E2E、flag-off 下载回归和桌面下载/复制交互后，最新累计基线为后端 `175 passed`、前端 5 个文件/24 个测试；最新证据见 `PG-H-entry-and-implementation-2026-07-20.md`。
- `uv run ruff check pixelle_video api tests`：通过。
- `git diff --check`：通过。

## 独立六维复审结论

- 评审线程：`/root/pg_a_closure_reviewer_v3`。
- 结论：`implementation_pass_with_boundary`；P0=0，P1=0。
- 六维依据：PublishPackage handoff 与 source-version 固化、carousel/video 互斥、retry 补偿与旧引用失效、flag-off fail-closed、错误映射、相关回归和实际测试/构建结果均复核通过。
- P2 留项：补偿回滚后新渲染文件的清理策略、JSON Schema 对同类 media ref 数量的进一步收紧、集成层对真实旧输出文件保留的更细断言；不阻塞本批次 Gate。
- 明确边界：本批次不是 PG-H 完整通过；真实抖音扫码/授权、真实上传/字段回读、封面/描述/话题 live smoke、最终人工发布仍未执行。

## 当前边界

- 本批次仍未执行真实抖音扫码、第三方授权、真实上传、字段回读或最终人工发布；不得据此声称 PG-H 或真实平台通过。
- 仍需独立严格审查线程从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六维复验；若有 P0/P1 修复清单，必须回到实现并重跑验证。
