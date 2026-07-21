# AC-4 抖音图文 implementation batch 1（2026-07-20）

状态：`implementation_pass_with_boundary`（独立六维复验通过；PG-H 未关闭）

## 本批次范围

本批次只在已通过的 AC-4 Entry 契约上实现本地、可回滚的图文渲染基线：

- `DouyinCarouselRenderer`：固定 1080×1440（3:4）PNG，允许 3/5/8 页，已有资产引用，注册字体，中文/英文/数字文本安全溢出错误。
- ZIP 导出：按 `page-01.png` 等页序写入，文件数与页数精确匹配，并保存 SHA-256 文件引用；ArtifactVersion 只保存 `file_key`/受控 `relative_path`，不保存绝对路径。
- 局部重试：单页重试输出 `page-XX-vN.png`，不覆盖已成功页面；版本号必须为正整数。
- `DouyinCarouselExecutor`：校验经营目标和来源 ArtifactVersion，校验来源属于当前项目的文案/标题产物；不解析平台、不打开浏览器、不调用发布动作。
- 资产边界：执行器拒绝 AppRun 直接传入 `asset_path`；生产 API 通过既有 AssetLibrary 的 `asset:<asset_id>` resolver 解析已登记图片，路径解析使用 realpath/注册库边界；单元测试中的直接路径只在显式临时 upload root 内使用。
- Artifact 交接：AppRunner 增加受控的 related artifact 输出，先保存 `carousel_plan` 与 `carousel_page`，再保存 `carousel_package`，用执行器内部引用解析为真实 ArtifactVersion ID。
- 失败补偿：related/primary ArtifactVersion 写入失败时按 source AppRun 清理本次产物，避免留下 draft/ready 孤儿 artifact。
- API 接线：应用中心 runner 登记 `builtin.douyin-carousel`，复用既有 FastAPI/AppRunner/SQLite/资产路径与现有模型配置边界；本批次不增加模型配置源。

## 证据

- 实现：`pixelle_video/app_center/carousel.py`、`pixelle_video/app_center/runner.py`、`api/routers/app_center.py`。
- 测试：`tests/app_center_carousel_renderer_test.py`，覆盖 3/5/8 页、PNG 尺寸、ZIP 顺序/完整性/SHA、缺图/缺字体/溢出/非法页数、局部重试、来源存在性/跨项目隔离、AppRunner review lifecycle 和 plan/page/package ArtifactVersion 交接。
- 定向聚合：`uv run pytest -q tests/app_center_carousel_renderer_test.py tests/app_center_carousel_entry_contract_test.py tests/app_center_core_test.py tests/app_center_api_test.py tests/coord0_contract_test.py` → **64 passed，12 个既有 Pydantic 弃用警告**。
- 交叉回归：`uv run pytest -q tests/app_center_*_test.py tests/publish_*_test.py tests/coord0_contract_test.py` → **163 passed，12 个既有 Pydantic 弃用警告**；独立审查线程另以临时 `PIXELLE_VIDEO_ROOT` AssetLibrary image upload 验证登记 asset resolver。
- 质量检查：相关路径 `uv run ruff check` 通过；`git diff --check` 通过。

## 明确边界

- 本批次未实现 LLM 分页规划、CreationWorkspace 图文编辑 UI、真实图片上传、PublishPackage V2 `publish_package_ref` 生成和发布中心 E2E；这些仍属于 AC-4 后续 implementation/PG-H 批次。
- 当前执行器要求调用方提供已审阅的分页计划；LLM 只允许通过既有 `AppLLMPort`/`ConfigAppLLMPort` 接入，不能在本批次创建第二模型配置源。
- 不调用抖音、不扫码、不做第三方授权、不上传平台、不点击最终发布；不改变 legacy video/template 渲染。
- PG-H 仍保持未开始，不能把本批次本地 renderer/fixture 结果解释为真实平台或完整用户体验通过。

## 回滚

删除/停用 `douyinCarousel` 接线即可回到默认关闭状态；现有 AppRunner、旧 artifact 类型、视频模板和 PublishRun 核心事实源不依赖该执行器。本批次未修改生产数据库或第三方平台状态。

## 待独立审查清单

审查线程需从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六方面复核：

1. related artifact 生成失败时的补偿清理是否覆盖所有失败路径，是否仍会产生孤儿版本；
2. package 对 plan/page ArtifactVersion 的引用是否全部为真实 ID，来源版本和项目隔离是否完整；
3. 资产 resolver、路径 realpath/根目录、字体、长文本、ZIP 读取和文件引用是否有越界或敏感信息泄露；
4. 现有 AppRunner/FakeExecutor/结构化文本应用回归是否保持；
5. LLM 分页规划、UI 编辑、PublishPackage handoff 和 flag-off regression 是否按 PG-H 继续排队。

当前结论：本批次实现与独立六维复验完成，允许进入同一 Stage 的下一批；PG-H 仍未关闭，不进入 AC-5。
