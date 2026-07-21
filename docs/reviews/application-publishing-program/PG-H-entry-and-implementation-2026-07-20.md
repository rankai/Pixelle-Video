# PG-H 图文产物可交接收口（2026-07-20）

状态：`implementation_ready_for_review`；当前唯一入口为 `APP-CAROUSEL/PG-H`。

## Gate 目标

- 3/5/8 页渲染、PNG/ZIP 导出和顺序/尺寸/命名/完整性矩阵全部通过。
- 标题或文案 ArtifactVersion → carousel AppRun → `carousel_package` → PublishPackage V2 → 发布中心 queued Run 的本地契约 E2E 通过。
- 单页重渲染的新 ArtifactVersion、旧 PublishPackage/`publish_package_ref` 失效和失败补偿有证据。
- `PIXELLE_PUBLISH_V2_ENABLED=0` 时图文 ZIP 下载、发布文案复制仍可用；不能因发布 V2 关闭而删除/阻断应用中心产物。

## 本收口批次实现范围

- 新增图文导出下载接口：仅服务受信 carousel 根目录内的 `carousel_package`/`carousel_page` 文件。
- CreationWorkspace 在查看 carousel package 版本后提供“下载图文包”“复制发布文案”；不依赖 Publish V2 开关。
- 增加标题来源→图文→PublishPackage→发布中心 queued Run 的本地、平台中立 E2E fixture/测试。

## 禁止范围与暂停点

- 不执行抖音扫码、第三方授权、真实上传、真实字段回读或最终人工发布。
- 不进入 AC-5 数字人口播，不改 PublishRun 核心状态机，不引入第二模型配置源。
- 并发 retry 输出路径冲突、失败渲染文件清理和更细 schema cardinality 作为 P2 登记，不伪称本 Gate 已解决。

## Gate 证据入口

- `tests/app_center_carousel_renderer_test.py`：3/5/8、flag-off download、retry/compensation。
- `tests/app_center_carousel_pg_h_test.py`：标题来源→图文→PublishPackage→PublishRun E2E。
- `desktop/src/features/creation/CreationWorkspace.test.tsx`：图文包下载/复制交互。
- 后端 app-center/publish/coordination 聚合、前端 Vitest/build、Ruff、`git diff --check`，再交独立六维复验。

## 当前实现与验证结果（待独立 Gate 复验）

- 本地 PG-H E2E：`tests/app_center_carousel_pg_h_test.py` 通过；标题来源经 AppRunner/假 LLM 规划与 renderer 生成 `carousel_package`，构建并校验 PublishPackage V2，创建 `publish_package_ref`，再创建发布中心 queued Run，并在人工停手状态结束。
- 发布文案来源映射：当桌面端仅提交来源 ArtifactVersion ID 时，执行器从同项目 `selected_title`/`title_set`/`copywriting` 可信版本补齐 title、description、hashtags；显式 payload 字段优先，不新增模型事实源、不编造事实。PG-H E2E 与 trusted-source 单测均断言非空/完整发布文案。
- 图文导出矩阵与失败补偿：`tests/app_center_carousel_renderer_test.py` 覆盖 3/5/8 页、PNG/ZIP、顺序/尺寸/命名/完整性、retry 新版本、旧 PublishPackage 与旧 `publish_package_ref` 的 `invalidated_at`/reason、失败回滚；flag-off 下载回归通过。
- 后端聚合：`uv run pytest -q tests/app_center_*_test.py tests/publish_*_test.py tests/coord0_contract_test.py` — **176 passed**，12 个既有 Pydantic 弃用警告。
- 静态检查：`uv run ruff check pixelle_video api tests` 通过；`git diff --check` 通过。
- 桌面端：`npm test -- --run` — **5 files / 24 tests passed**；`npm run build` 通过（保留既有大 chunk warning）。CreationWorkspace 测试覆盖来源派生 title-only publish copy 的复制成功路径。
- 证据边界：未执行真实抖音扫码、第三方授权、真实上传、字段回读或最终发布；待独立严格审查线程完成六维复验后才能更新 PG-H Gate。
