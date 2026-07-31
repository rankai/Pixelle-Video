# APP-RESULT-HISTORY-4 启用、回滚与收口实施证据

- Stage：`APP-RESULT-HISTORY-4/ENABLE_AND_CLOSE`
- Gate：`PG-ARH-E`
- 日期：2026-07-30
- 结论：待最终独立六维终审

## 1. on → off → on

后端：

- `PIXELLE_APP_RESULT_HISTORY_V1=true`：返回 schema-valid 历史结果。
- 切换为 `false`：路由 fail-closed，返回 `APP_RESULT_HISTORY_DISABLED`。
- 再切回 `true`：返回内容与首次开启完全一致。
- 全过程 SQLite 逐表快照不变。

桌面：

- build flag 与 Tauri runtime flag 采用“同时为真才开启”，冲突或未知值 fail-closed。
- 同一项目 `APP-WORKBENCH-3 门店咖啡实测`：
  - off：截图可见旧“标题候选”、逐条输入框、“使用这个标题/更多”和“保存修改”，无“生成记录”；
  - on-again：截图可见“生成记录”、1 次生成、本次生成 5 个标题及“已采用”状态。
- off 证据：`evidence/app-result-history-2026-07-30/rollback-off-legacy-result.png`，SHA-256 `82494841ecb11d61c13841e412b12768c0a1bdb6ed9257596601fe8c6a6d445d`
- on-again 证据：`evidence/app-result-history-2026-07-30/rollback-on-again-history.png`，SHA-256 `08329caab76f6b3a47e1e8f282d684378e59ad6a0bc89893f5571f6a907262f3`

## 2. 四应用一致性

| 应用 | 一次运行的记录语义 | 结果展示 |
| --- | --- | --- |
| 门店营销文案 | 一个批次记录块 | 批次内直接显示全部文案 |
| 爆款标题 | 一个批次记录块 | 批次内直接显示全部标题 |
| 抖音图文 | 一个批次记录块 | 一个成品卡，点击预览全部页面 |
| 数字人口播 | 一个批次记录块 | 一个最终视频卡，点击真实播放 |

门店文案真实证据：`evidence/app-result-history-2026-07-30/marketing-copy-history.png`
爆款标题真实证据：`evidence/app-result-history-2026-07-30/title-batch-history.png`
图文/数字人证据见 Stage3 实施报告。

默认范围为“当前应用”；“全部成果”由用户主动切换，因此混合历史不会增加主任务密度。

## 3. 回归与兼容

- Desktop 全量：20 files/148 passed。
- Backend Entry/投影/媒体：39 passed。
- Windows/Tauri/sidecar 静态契约与 Result History 聚合：68 passed。
- Result History 前端/flag 定向：2 files/20 passed。
- Production build：通过。
- Ruff、format、`git diff --check`：通过。
- 最新 10 条/100 runs 本地投影低于 350ms regression budget。
- 空态、读取失败、游标失效、局部媒体失败、跨项目和路径逃逸均有自动化覆盖。
- 真实 Windows 用户设备安装仍属于暂停的上位 `PG-L` checkpoint，不在本 CR 中伪报完成；本 Stage 已验证 Windows sidecar flag 同步静态契约。

## 4. 可视化与产出质量评审

- 1440/1280/900/390、等效 200% 与焦点态通过。
- 文案与标题为可用但需真实发布前编辑的候选；差异度、事实覆盖率仍可增强。
- 旧抖音图文样片内容质量不通过。
- 数字人样片为受控可用，字幕大小、动作丰富度和精确口型仍有改进空间。

完整结论：
[`APP-RESULT-HISTORY-output-quality-review-2026-07-30.md`](APP-RESULT-HISTORY-output-quality-review-2026-07-30.md)。

## 5. 安全边界

- 未调用新的付费 Provider。
- 未执行任何平台真实发布。
- 最终平台发布按钮点击次数为 0。
- 未新增数据库迁移或第二事实表。

## 6. 独立审查修复循环

- 首轮终审发现 1 个 P1：两张回滚截图相同且没有显示结果区，无法支持真实 on→off→on 结论。
- 已在同一项目重新滚动到右侧结果区采集：off 显示旧候选编辑器，on-again 显示生成记录与 5 条候选。
- 两张新证据哈希不同，旧的错误证据已被同路径替换；等待独立线程复验。
