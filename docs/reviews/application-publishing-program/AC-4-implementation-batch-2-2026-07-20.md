# AC-4 抖音图文 implementation batch 2（2026-07-20）

状态：`implementation_pass_with_boundary`（batch 2 已通过独立六维复验；PG-H 未关闭）

## 本批次范围

- 复用既有 `AppLLMPort`/`ConfigAppLLMPort` 增加 `DouyinCarouselPlanner`：只生成受限 `carousel_plan` 页面结构，不创建第二模型配置源。
- Planner 固定使用 goal、来源 ArtifactVersion 内容、page_count、template_id 和已登记 `asset_refs`；模型返回的 asset_ref 必须属于输入集合，页数必须为 3/5/8 且索引连续。
- 未提供 pages 时由 planner 生成分页计划；已提供 pages 时继续走已审阅分页的本地渲染/编辑路径，避免重复调用模型；结构化输出错误最多执行一次受控修复请求。
- 生产 AppRunner 接线复用 `ConfigAppLLMPort`；AssetLibrary resolver 继续只接受 `asset:<id>`。
- CreationWorkspace 为 `builtin.douyin-carousel` 增加来源 ArtifactVersion、页数、登记资产引用输入，并将运行草稿送入统一 AppRun/Artifact 链路。

## 证据

- 后端：`pixelle_video/app_center/carousel.py`、`api/routers/app_center.py`。
- 桌面端：`desktop/src/features/creation/CreationWorkspace.tsx`。
- 测试：planner 成功/非法模型 asset_ref、LLM 请求边界、AppRunner 产物生命周期；CreationWorkspace 图文运行 payload 测试。
- 后端定向（batch 1 回归 + batch 2）：`uv run pytest -q tests/app_center_carousel_renderer_test.py tests/app_center_carousel_entry_contract_test.py tests/app_center_core_test.py tests/app_center_api_test.py tests/coord0_contract_test.py` → **66 passed，12 个既有 Pydantic 弃用警告**。
- 前端：`npm run test -- --run` → **5 files / 23 tests passed**；`npm run build` 通过（保留既有 chunk size warning）。
- 相关路径 Ruff、`git diff --check` 通过。

## 明确边界

- 本批次仍未实现 AI 生图、平台上传、最终发布或第三方授权。
- 当前 planner 只生成页面文案/已有资产绑定；缺少已登记 asset_refs 时 fail-closed，不自动找本地路径、不生成图片。
- PublishPackage V2 `publish_package_ref`、retry 新 ArtifactVersion/旧包失效、flag-off 回归和完整文案/标题→图文→发布中心 E2E 仍留在 PG-H 后续批次。

## 待独立审查

审查线程需验证：模型请求是否只复用既有配置、来源事实和 asset_ref 边界是否完整、结构化模型输出失败是否稳定、UI payload 是否可回读、旧文案/标题/数字人/发布回归是否保持；P2 hardening 继续登记但不得误报 PG-H 完成。

## 独立复审

- [`AC-4-implementation-batch-2-review-2026-07-20.md`](AC-4-implementation-batch-2-review-2026-07-20.md)
- 结论：`implementation_pass_with_boundary`；P0/P1=0。
- P2：`missing_facts` 未持久化/可视化、asset_ref 实体存在性延后到渲染、template_id 未登记校验，以及 Planner 专属失败矩阵可继续补强。
- 允许继续同一 `APP-CAROUSEL` Stage 的下一批；不关闭 PG-H，不进入 AC-5。
