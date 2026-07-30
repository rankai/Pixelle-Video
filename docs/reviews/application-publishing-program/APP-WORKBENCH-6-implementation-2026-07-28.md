# APP-WORKBENCH-6 实施记录（跨应用交付与版本固定）

日期：2026-07-28
阶段：`APP-WORKBENCH-6`
状态：`completed_with_boundary`；独立六维复审 PASS（P0/P1=0）

## 本批次交付

1. **统一交付动作**
   - 新增共享 `ArtifactActions`、`VersionSwitcher`、`HandoffActions` 组件。
   - 文案、标题、抖音图文和数字人结果统一显示版本切换与明确的交接动作。
   - 版本切换后，后续交接使用当前固定版本，不隐式读取上游最新版本。
2. **应用间交接**
   - 门店营销文案可交接到爆款标题、抖音图文和数字人。
   - 标题候选可交接到抖音图文和数字人，并创建可追溯的 `selected_title` Artifact 版本。
   - 数字人结果可生成发布包并交给发布中心；不自动打开第三方平台、不自动点击最终发布。
3. **幂等与来源边界**
   - 同一标题集合版本与候选索引重复交接复用已有选择版本，不重复创建。
   - 目标应用通过 `source_version_id` 固定来源；数字人工作台检测上游是否产生新版本并提示重新选择。
   - 发布包只接收本次运行已有的视频、封面、发布文案等 Artifact 版本，缺少视频时 fail-closed。
4. **路由与视觉**
   - `source_version_id` 通过应用路由保留并在目标工作台解析。
   - 两栏工作台沿用现有 tokens；工作台使用可用画布并以 8px bleed 收紧左右留白，网格间距保持 16px，移动端断点不变。
   - 标题/图文来源的异步版本扫描在项目切换后执行 active 二次检查，旧请求不得回写新项目。
   - 失效、归档或跨项目来源均 fail-closed；手动重新选择来源后解除阻塞。

## 验证记录

- Desktop：`npm test -- --run` → 16 files / 104 tests passed；新增版本固定交接、无效来源 fail-closed、标题来源更新提示、标题→图文/数字人、数字人→发布中心、行内视频下载和重复点击幂等回归覆盖。
- Desktop：`npm run build` → passed；仅有既有 chunk size warning。
- Backend：本轮核心回归 `uv run pytest -q tests/app_workbench_*_test.py tests/digital_human_quality_impl_test.py tests/digital_human_dual_mode_recovery_test.py tests/app_center_ip_broadcast_artifact_test.py tests/app_center_api_test.py` → 62 tests passed；独立复审关联后端集合复跑 100 passed；保留 12 条既有 Pydantic deprecation warnings。
- Static quality：`git diff --check`、Python compile/json validation → passed。
- In-app browser visual smoke（1280×720）：抖音图文工作台可加载；调整后 shell `x=244..1245`、grid `width=1001`、`overflow=false`，两栏间距 16px，无横向滚动；左右空白较原来各收紧 16px。
- 修复复验 UI：标题版本切换后交接使用所选历史版本；标题候选可分别进入图文/数字人；数字人结果可创建发布包并交给发布中心；这些路径均有桌面回归测试，但本批次未打开第三方平台。

## 明确边界

- 本批次不调用真实大模型、TTS、RunningHub 或第三方平台。
- 发布中心仍由用户人工点击最终发布；本批次最终发布点击计数为 0。
- 版本选择器只切换已存在的 Artifact 版本；不会把新版本自动写回上游。
- 真实平台发布成功、回滚和 WebView SLA 不在本批次宣称完成范围。

## Gate 结论

独立审查线程从需求完整性、逻辑正确性、边界情况、代码质量、测试覆盖、实际运行结果六维复验，结论 `PASS`，P0/P1=0；异步 active 二次检查已补并完成回归。`PG-AW-G=passed_with_boundary`，台账已切换至 APP-WORKBENCH-7 Entry。
