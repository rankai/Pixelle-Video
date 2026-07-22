# AC-4 抖音图文 implementation batch 1 独立六维复审（2026-07-20）

评审人：独立严格审查线程 `/root/pg_a_closure_reviewer_v3`  
结论：`implementation_pass_with_boundary`  
P0：0；P1：0；允许继续留在 `APP-CAROUSEL` implementation 并进入下一批；不得关闭 PG-H 或进入 AC-5。

## 六维结果

1. 需求完整性：已覆盖本批次的 3/5/8 页、1080×1440、PNG/ZIP、缺图/缺字体/溢出、单页文件重试隔离、goal/source ArtifactVersion、项目隔离、related ArtifactVersion、失败补偿、AssetLibrary resolver 和 API 接线。
2. 逻辑正确性：成功生命周期产生 `carousel_plan`、3 个 `carousel_page` 与 `carousel_package`；package 的 `source_plan_artifact_version_id`/`page_artifact_version_ids` 均解析为真实 `artifact_version_*`；同输入跨 run_ref ZIP SHA 一致。
3. 边界情况：缺失/跨项目 source、AppRun 直接 `asset_path`、绝对路径和带 `/` 的伪造 asset ref 被拒绝；related/primary 注入失败后 `list_artifacts(project)==[]`，无孤儿 artifact；ArtifactVersion file_refs 不含绝对路径。
4. 代码质量：Ruff clean；`git diff --check` clean；renderer、executor、AppRunner related output、补偿和 AssetLibrary resolver 的职责边界清晰；未调用浏览器、平台或新模型配置源。
5. 测试覆盖：定向 renderer/Entry/core/API/coord0 聚合 **64 passed**；app_center/publish/coord0 交叉回归 **163 passed**；12 个 Pydantic 弃用警告均为既有技术债。
6. 实际运行结果：独立线程在临时 `PIXELLE_VIDEO_ROOT` 完成 AssetLibrary 图片上传，`asset:<id>` resolver 返回已登记 revision 文件；绝对路径/含 `/` 引用返回 `None`；成功/失败 AppRunner lifecycle 与真实本地文件读取结果可回读。

## P2 后续登记（不阻塞本批次）

- `FakeExecutor` 重建 `ExecutorOutput` 时尚未保留 `related_artifacts`。
- malformed page/asset_refs/hashtags 和 invalid `font_size` 仍可能抛原始 `TypeError`/`ValueError`，需统一稳定 `CarouselRenderError`。
- `render_package` 中途失败可能留下未登记临时 PNG；后续增加 run 目录清理/补偿。
- `relative_path` 需统一 POSIX 表达，资源需 pin revision。

## 明确未完成边界

AC-E/PG-H 仍保留：单页重试登记新 ArtifactVersion 与旧 `publish_package_ref` 失效、LLM 分页规划、CreationWorkspace 图文 UI、PublishPackage V2 handoff、flag-off 回归、真实平台上传/最终发布。上述边界不影响本批次实现放行，但禁止将本批次解释为 PG-H 或真实平台完成。
