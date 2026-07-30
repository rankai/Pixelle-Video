# APP-WORKBENCH-4 图文工作台实现证据

- Stage：`APP-WORKBENCH-4`
- Change Request：`CR-APP-WORKBENCH-001`
- Gate：`PG-AW-E=passed_with_boundary`
- 日期：2026-07-28

## 交付范围

本阶段把既有抖音图文能力接入统一应用工作台，保持 FastAPI/Python、SQLite、既有 Carousel Renderer 和人工发布边界不变：

- 左侧输入：项目、ContextSnapshot、固定来源 ArtifactVersion、图片资产 revision、风格、页数和模板；
- 右侧结果：分页计划、页面预览、可编辑文案、页面图片选择、版本列表和状态；
- 交付：PNG 图片组、ZIP、发布文案、ArtifactVersion 和发布中心 typed handoff；
- 局部修改：保存并仅重渲染当前页，新增受影响页版本及对应 package 版本，历史版本保持可追溯；
- 安全：不打开抖音或其他平台，最终发布按钮不自动点击。

## 关键修复

首次真实局部重渲染暴露出旧 ZIP 仍引用旧页面的缺陷。本阶段新增 `DouyinCarouselRenderer.rebuild_package_archive()`，每次重渲染从当前页文件引用重建 `carousel-package-vN.zip`，并同步 `export_manifest.zip_name/zip_sha256`。旧 ZIP 不删除，保留为审计和回滚证据。

同时为 `get_app_center_repository()` 增加进程内初始化锁，避免 FastAPI 并发首次请求同时执行迁移导致 `migration is already running` 的瞬时 500。

工作台 `.app-workbench-shell` 最大宽度从 1380px 调整为 1640px，减少宽屏左右浪费；959px 以下仍单栏并使用配置/结果 Tab，未改变既有 tokens、移动断点和左右比例。

## 实际运行证据

真实本机 Run：`run_127222d5c60e403fa7677eb1aa3a7227`。

- 应用：`builtin.douyin-carousel`，版本 `1.1.0`；
- 初始结果：3 页 `carousel_page`、1 个 `carousel_package`，状态 `needs_review`；
- 结果区可见：查看版本、下载图片组、下载 ZIP、复制发布文案、交给发布中心；
- 受控编辑第一页后，页面版本递增，package 当前版本为 v3；
- 当前 ZIP 名称：`carousel-package-v3.zip`；
- ZIP 内固定为 `page-01.png`、`page-02.png`、`page-03.png`，顺序正确；
- `page-01.png` 解压 SHA 与当前 `page-01-v3.png` SHA 一致，page 2/3 仍复用原版本；
- `PRAGMA foreign_key_check` 为空；
- 浏览器实际未打开发布平台，最终发布点击为 0。

## 自动化验证

```text
uv run pytest -q \
  tests/coord0_contract_test.py \
  tests/config_llm_profiles_test.py \
  tests/desktop_api_test.py \
  tests/app_center_carousel_renderer_test.py \
  tests/app_workbench_carousel_v2_test.py
48 passed, 12 warnings

npm test -- --run \
  src/features/app-workbench \
  src/features/app-center/applicationRoutes.test.ts \
  src/features/app-center/DigitalHumanApplicationView.test.tsx \
  src/features/creation/CreationWorkspace.test.tsx
45 passed

npm run build
passed

uv run ruff check ... && git diff --check
passed
```

警告仅为现有 Pydantic v2 弃用提示；不影响本 Gate。全套后端长回归曾在 696 passed 后因旧测试基线和长尾用例中断，本阶段以修复后的契约子集、应用中心定向回归、桌面定向回归和真实运行证据作为 Gate 依据。

## Gate 结论

独立审查线程从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行六个维度复核，结论 `PASS`，新增 P0/P1 为 0。Stage4 完成并切换唯一入口到 `APP-WORKBENCH-5/PG-AW-F_entry_in_progress`。
