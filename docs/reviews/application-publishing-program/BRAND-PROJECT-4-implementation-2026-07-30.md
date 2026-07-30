# BRAND-PROJECT-4 四应用固定品牌上下文实施证据

日期：2026-07-30
Stage：`BRAND-PROJECT-4`
Gate：`PG-BP-E_remediation_review_pending`

## 1. 实施结论

Stage4 已完成文案、标题、抖音图文和数字人口播对固定项目品牌上下文的统一消费，当前停在独立复审入口：

- 四应用的新运行均由服务端解析并固定 `ContextSnapshot`，不信任客户端提交的品牌资料或快照内容；
- 项目同步品牌资料前后的运行固定到各自快照，旧运行、旧 ArtifactVersion 和基于旧版本的 typed handoff 不会追随新品牌版本漂移；
- ArtifactVersion 持久化 `source_app_run_id + context_snapshot_id`，ArtifactHandoff 持久化源、目标快照；跨项目或混合快照 handoff 失败关闭；
- 文案和标题提示词只获得各自需要的品牌字段；图文渲染实际使用固定品牌色、品牌名称和固定 Logo revision；
- 数字人口播交付实际读取固定 Logo/BGM revision，生成品牌封面、固定 BGM 文件和带输入/输出哈希的交付回执；
- “仅本项目使用”的地址和片尾覆盖进入生成/交付上下文，回执明确登记 `overridden_fields`；
- 数字人口播 API 响应显式返回 `context_snapshot_id`，前端恢复历史运行时能够完成服务端绑定校验；
- 首轮独立复审 `P0=0/P1=1/P2=3` 已完成修复和自验：新 typed handoff 严格失败关闭、AppRun repository 信任边界不再依赖 API flag、轮播走真实 renderer/AppRunner、数字人本地完成态统一为 1–6 步完成；
- 复验 full split 暴露的两个 App Workbench 图文 V2 测试夹具已迁移为同项目、同快照的 `AppRun → Artifact → ArtifactVersion` 来源链；生产侧对 null provenance 的 fail-closed 规则未放宽；
- 默认 feature flags 未改变；未进入 BRAND-PROJECT-5，未触发平台发布、扫码、授权、上传或 Git 提交。

## 2. 服务端固定快照与应用投影

`ProjectContextResolver.resolve_for_application()` 只从服务端持久化的固定快照解析应用所需字段：

| 应用 | 固定品牌字段 |
| --- | --- |
| 营销文案 | 品牌名称、地址、电话、优惠语、片尾 |
| 爆款标题 | 品牌名称 |
| 抖音图文 | 品牌名称、主/辅品牌色、字体、Logo、片尾、优惠语 |
| 数字人口播 | 品牌名称、地址、电话、主/辅品牌色、字体、字幕、Logo、默认 BGM、片尾、优惠语 |

普通 AppRun 创建时，服务端固定项目 current snapshot；带 typed source
ArtifactVersion 的新运行固定来源版本的精确 snapshot。服务端会覆盖客户端提供的
`project_id`、`app_id`、`app_version` 和 `context_snapshot_id` 等可信字段。
幂等重放保留原运行的快照，不会在重放时解析项目的新 current snapshot。

首轮复审后，这一约束已经下沉到 `AppCenterRepository.create_app_run()`：

- 普通新运行只能使用项目 current snapshot；
- 带完整 typed source provenance 的新运行可继承来源 ArtifactVersion 的精确旧快照；
- 相同幂等请求重放直接返回原运行及原快照，不因项目 current 更新而漂移；
- stale 普通快照、跨项目来源和混合来源在 repository 写入前失败，API 是否打开品牌
  flag 不影响该信任边界。

## 3. 运行、产物和 handoff 血缘

本阶段为 ArtifactVersion 增加：

- `source_app_run_id`
- `context_snapshot_id`

为 ArtifactHandoff 增加：

- `source_context_snapshot_id`
- `target_context_snapshot_id`

迁移对旧数据进行可审计回填，读取兼容旧 null provenance；但新的 typed run 和
handoff 要求来源版本具备完整 provenance。一个 handoff 中出现跨项目或多个
ContextSnapshot 时，以稳定错误码失败关闭，不创建半成品记录。

首轮复审要求的新 handoff 矩阵已锁定：

- typed source provenance 为 null：`PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED`；
- target run provenance 为 null 或与 source 不同：
  `PROJECT_CONTEXT_HANDOFF_MIXED`；
- 跨项目引用：`PROJECT_CONTEXT_CROSS_PROJECT_REF`；
- old→new 或同一次 handoff 混入多个 snapshot：
  `PROJECT_CONTEXT_HANDOFF_MIXED`；
- 所有负例均在 insert 前完成校验，数据库 handoff 计数不变；
- 已存在的 legacy null handoff 继续只读返回，不进行静默 backfill。

公开 `append_artifact_version()` 仍允许保存历史兼容所需的 null provenance
ArtifactVersion；新增回归明确锁定：这类旧产物可以读取，但新 typed AppRun 和
handoff 必须先经过显式映射，否则均以
`PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED` 失败且零写入。

受控 fixture 在同一项目中生成了同步前后两次营销文案运行：

- 旧快照：`context_78cdf764a6014cf4a1d0de46a3161aec`
- 新快照：`context_dca16e6ed6624b85b15292c6977325f3`
- 旧营销运行：`run_5e00001425a2454199bc0af20b1857d9`
- 新营销运行：`run_56e37a2fa04345d2bd689d834e0295e2`
- 基于旧营销 ArtifactVersion 的标题运行：
  `run_5b114e27f2ea40da8a18bd4b7ac5dc25`

同步后重新读取旧 AppRun、旧 ArtifactVersion 和标题 handoff，仍保持旧 snapshot；
新运行固定新 snapshot。项目覆盖项继续保留，没有被品牌同步覆盖。

## 4. 实际渲染与交付

### 抖音图文

图文 renderer 使用固定快照的主色、辅色、品牌名称和精确 Logo revision 进行实际
像素渲染；局部重渲染继续沿用原页面 ArtifactVersion 的品牌上下文，避免重试时读取
项目最新品牌。交付 manifest 只暴露可发布的品牌应用结果，不暴露本地绝对路径。

复审补证 fixture 不再手工写入一个只有 manifest 的 `carousel_package`，而是通过
`DouyinCarouselExecutor → AppRunner → ArtifactVersion` 生成 3 张真实 1080×1440
PNG 和 ZIP。Browser 页面中 3 张预览均 `complete=true`、自然尺寸为
`1080×1440`，首张实际成品、品牌色、品牌名和固定 Logo 在结果区可见。

### 数字人口播

隔离本地 postprocessor 实际完成：

- 读取固定 Logo revision，渲染 540×720、品牌色为
  `#0F766E / #ECFDF5` 的品牌封面；
- 固定 Logo 输入哈希
  `1842be99536ac941b53348ad3d976a580f8c9539f0c4b2c59de9e914f0cca949`；
- 封面输出哈希
  `3d780d727932500b417cff2a2e4b33f816eda6b4f60038f6aedbef7cf7ffed98`；
- 读取并交付固定默认 BGM revision，输入/输出哈希均为
  `2976da01e205a110c9fa41d47659e238a5c6d3c3f3137582f2949853faa201dd`；
- 交付回执登记固定 snapshot、Logo/BGM revision、颜色、项目地址/片尾覆盖和
  `overridden_fields=["ending_card_text","store_address"]`。

生产数字人路径把固定 BGM 文件映射到既有后处理输入；本阶段不把隔离
postprocessor 的品牌封面测试扩大声称为所有第三方数字人 provider 最终视频均已
完成 Logo 合成。

隔离本地交付在人工接收后，session 的 1–6 步全部持久化为 `done`；已完成运行再次
接收保持幂等且不会把任何步骤退回 `ready/pending`。这一点由 Stage4 专测、生成的
`fixture-remediation.json` 和旧完成 fixture 的幂等升级共同验证。

实际交付件位于
[`qa/BRAND-PROJECT-4-visual-2026-07-30/`](qa/BRAND-PROJECT-4-visual-2026-07-30/)。

## 5. 自动化验证

后端和契约聚合：

```text
.venv/bin/pytest -q \
  tests/brand_project_stage4_test.py \
  tests/brand_project_stage2_test.py \
  tests/brand_project_stage1_test.py \
  tests/app_workbench_project_context_test.py \
  tests/brand_project_boundary_entry_contract_test.py \
  tests/app_center_api_test.py \
  tests/app_center_registry_test.py \
  tests/app_center_carousel_renderer_test.py \
  tests/app_center_ip_broadcast_api_test.py \
  tests/digital_human_quality_impl_test.py \
  tests/asset_library_v2_repository_test.py \
  tests/config_llm_profiles_test.py \
  tests/coord0_contract_test.py \
  tests/app_workbench_carousel_v2_test.py
```

结果：`179 passed / 0 failed / 12 existing Pydantic deprecation warnings`。
其中 Stage4 专测 `10 passed`，新增覆盖 repository/API handoff 的 old→new、
null→new、cross-project、mixed-source 零写入矩阵，legacy null 只读兼容，以及
AppRun 普通 current、typed old source、stale reject、幂等重放不漂移和 public
append legacy null→新 typed consumer 显式映射边界。App Workbench 图文 V2 原两项
测试保持原 style/fact 断言，使用可信 context-bound 来源后为 `2 passed`。

按独立复验的相同 split 口径完成全量 Python：

- 非浏览器组：`800 passed / 0 failed / 12 existing warnings`；
- 浏览器/慢测试组 12 文件：`131 passed / 0 failed / 12 existing warnings`；
- 合计：`931 passed / 0 failed`。

复验修复前非浏览器组的 `797 passed / 2 failed` 恰为上述两个旧测试夹具使用无
provenance `selected_title` 所致；修复未改生产代码、未放宽
`PROJECT_CONTEXT_LEGACY_MAPPING_REQUIRED`。

Desktop 定向验证：`8 files / 49 passed / 0 failed`。
Desktop 全量验证：`18 files / 123 passed / 0 failed`。
Desktop production build：通过，`4610 modules transformed`，仅既有
chunk-size warning。

并发 Desktop 全量首次出现一个既有 1 秒 `waitFor` 时序用例超时；该用例单独复跑
通过，随后使用单 worker 复跑全量得到 `18 files / 123 passed`，未通过放宽断言或
修改产品代码掩盖该时序现象。

Sidecar 补充使用独立根目录
`/tmp/pixelle-brand-project-stage4-sidecar-remediation.5kV8vL` 完成两次启动：

- 两次 `/health` 均为 200；
- 第二次带 Desktop token 的 `/api/apps` 为 200；
- 两次关闭后端口均释放。

Ruff check、Ruff format check 和 `git diff --check` 均通过。

更早曾发起一次全量 Python 回归；在 `77%`、`770 passed` 时有 2 个本阶段契约测试
失败，原因是新 Stage owner/gate 枚举未同步。修复后定向契约及上述 179 项聚合均
通过；全量运行随后进入既有长时 Playwright 等待并被人工中止，因此不把该次尝试
记录为“全量通过”。本轮已通过上述同口径 split 完整取代该历史未完成结果。

## 6. 真实页面验证

受控隔离环境：

- API：`http://127.0.0.1:8104`
- Vite：`http://127.0.0.1:1424`
- 数据根：`/tmp/pixelle-brand-project-stage4-visual2`
- 仅在隔离进程打开既有 content、carousel、digital-human Registry flags 和
  brand-project flag；产品默认值未修改；
- fixture 不调用 LLM、TTS、RunningHub、第三方 provider 或发布平台。

Browser plugin 实测四个路由：

1. 营销文案显示“北岸咖啡 · 焕新”、固定品牌资料说明和完成结果；
2. 爆款标题显示同一固定品牌和 5 个完成标题；
3. 抖音图文显示同一固定品牌和完成交付；
4. 数字人口播从固定 `(project, context, run)` 恢复，显示“已完成”、最终视频、
   封面和发布文案。

四个路由均为 `scrollWidth=clientWidth=1905`，无横向溢出。控制台没有业务错误，
只有既有 Ant Design `Alert.message`、`List` 和 `Input.addonAfter` 三条弃用警告。

复审补证在新隔离根
`/tmp/pixelle-brand-project-stage4-remediation` 重新验证图文路由：

- 结果区实际显示 3 张渲染页；每张自然尺寸 `1080×1440`；
- 首张成品截图为
  `douyin-carousel-rendered-page-stage4-remediation.jpg`；
- `scrollWidth=clientWidth=1905`，控制台仅既有 Ant Design `List` 弃用提示。

数字人补图所需的恢复指针在本轮 Browser 会话中不存在；Browser 安全策略明确拒绝
直接写入 `localStorage`，并禁止通过 raw CDP、替代浏览器或间接执行绕过。验证按
策略停止，没有伪造新版截图。数字人 `completed + step 1..6 done` 由持久化
session、repository 幂等接收和自动化测试证明，`digital-human-stage4.png` 仅保留为
首轮页面证据，不再被表述为修复后的 all-done 截图。Browser viewport 已重置，创建
的标签页已关闭。

截图和 SHA-256 见
[`qa/BRAND-PROJECT-4-implementation-2026-07-30.json`](qa/BRAND-PROJECT-4-implementation-2026-07-30.json)。

## 7. Gate 边界

- 状态：`PG-BP-E_remediation_review_pending`
- Stage4 首轮独立复审 P0=0/P1=1/P2=3 已修复并自验，尚待同一独立线程复验；
- 不进入 BRAND-PROJECT-5；
- 默认 flags 保持关闭；
- LLM、TTS、RunningHub、第三方 provider、平台打开、扫码、授权、上传和最终发布点击均为 0；
- 无 Git commit；
- `PROGRAM-ROLLOUT/PG-L_paused_external` 不变。
