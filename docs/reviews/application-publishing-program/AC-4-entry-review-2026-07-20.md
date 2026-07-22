# AC-4 抖音图文 Entry 评审（2026-07-20）

状态：`entry_in_progress`（只冻结契约，不进入业务实现）

## 前置与目标

- 前置 Gate：`PG-G passed_with_boundary`。
- 目标：验证首个图文应用可以在统一 App Center/Artifact/AppRun 体系内交付 `carousel_plan`、`carousel_page`、`carousel_package`，并能交接到 PublishPackage V2。
- 首期只做抖音图文、固定 3:4、3/5/8 页、有限模板和已有资产引用；不做 AI 生图、高级设计器、多平台模板或真实平台上传。

## Entry 冻结

| 领域 | 冻结内容 |
| --- | --- |
| 应用 | `builtin.douyin-carousel@1.0.0`；flag `douyinCarousel` 默认关闭 |
| 页面 | 允许 3、5、8 页；页索引从 1 连续递增；每页 1080×1440（3:4） |
| 输入 | 经营目标、来源 ArtifactVersion；可选品牌、模板、已有资产和已选标题版本；缺失事实必须显式提示，不得由模型补造 |
| 产物 | plan/page/package 三类 artifact；分页文案可编辑；单页重渲染产生新版本 |
| 渲染 | 单页 PNG、批量 ZIP；文件名 `page-01.png` 等；ZIP 按页序且文件数精确匹配 |
| 失败 | 单页失败可单独重试；成功页不回滚；缺图、缺字体、文本溢出均为可见错误，不静默截断 |
| 交接 | `carousel_package` 固定来源版本，生成 PublishPackage V2 `publish_package_ref`；来源版本变化使旧引用失效 |
| 回滚 | flag 关闭不影响原模板/成片渲染和旧工作台；Entry 不改生产数据库、不触发平台动作 |

## 机器可读证据

- 契约：[`carousel-entry.contract.json`](../../contracts/app-center/carousel-entry.contract.json)。
- Fixture：[`carousel-entry-fixtures.json`](../../contracts/app-center/fixtures/carousel-entry-fixtures.json)。
- Entry 契约测试：`tests/app_center_carousel_entry_contract_test.py`，覆盖 page count/尺寸/索引、plan/page/package required fields 与来源版本、单页失败/重试隔离、PNG/ZIP 顺序与完整性、PublishPackage handoff、flag 默认关闭和 Entry 无 Executor/UI/平台动作。

## 禁止越界与暂停点

- 不实现真实图文 Executor、渲染 UI、真实 PNG/ZIP 生成或发布中心集成；这些属于 AC-4 implementation/PG-H。
- 不调用 AI 生图 provider，不增加第二模型配置源，不修改 PublishRun 核心事实源。
- 不上传到抖音、不点击最终发布；平台 live evidence 仍遵循 PUB-3/PUB-5 边界。

## Entry Gate 判定

Entry 通过条件：契约 Draft 2020-12 可解析；3/5/8 页和连续索引/尺寸/产物/失败/重试/handoff/flag 语义 fixture 全部通过；禁止范围和 AC-E 的完整 Gate 入口清晰；独立六维审查 P0/P1=0。

当前结论：待独立审查；未通过前不得进入 AC-4 implementation。
