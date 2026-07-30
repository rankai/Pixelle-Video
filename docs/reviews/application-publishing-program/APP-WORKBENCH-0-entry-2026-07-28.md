# APP-WORKBENCH-0 Entry 收口

- Stage：`APP-WORKBENCH-0`
- Gate：`PG-AW-A`
- Change Request：`CR-APP-WORKBENCH-001`
- 结论：`passed_with_boundary`
- 日期：2026-07-28

## 1. 本阶段交付

本阶段只冻结应用工作台优化的共同契约和视觉基线，没有修改业务 UI、数据库或真实执行器：

1. `ContentProject` 的长期事实由不可变 `ContextSnapshot v2` 表达，事实、来源、资产 revision 和品牌 revision 均可追溯。
2. 单次执行输入由 `AppRun.input_payload + context_snapshot_id` 固定；运行开始后不允许原地改写。
3. 结果继续使用 `Artifact + immutable ArtifactVersion`；编辑产生新版本，不覆盖历史版本。
4. 跨应用传递使用固定 `source_artifact_version_id` 的 typed handoff；源版本变化只通知，不热更新已创建的目标运行。
5. 风格库使用受信 `style_id + version` Registry。用户粘贴的自定义参考只属于本次运行，不写入项目事实，也不自动保存为个人风格。
6. 四应用输入 schema v2 已冻结：门店营销文案、爆款标题、抖音图文、数字人视频。
7. 结果区状态固定为 `empty/running/failed/needs_review/saved`；没有真实证据时不展示伪进度百分比。
8. 四个工作台 feature flag 默认关闭，未知或冲突配置按关闭处理，旧 UI 保持可回退。

## 2. 数据所有权与安全边界

| 数据 | 唯一所有者 | 本阶段约束 |
| --- | --- | --- |
| 项目长期事实 | `ContentProject + ContextSnapshot` | v1 可读；保存升级时新建 v2，不覆盖旧快照 |
| 单次运行输入 | `AppRun` | 绑定项目和 context snapshot；执行后不可变 |
| 生成结果 | `ArtifactVersion` | 版本追加；失败运行不创建伪 Artifact |
| 跨应用来源 | `ArtifactHandoff` | 固定来源版本；同项目；重试幂等 |
| 风格预设 | 受信 Registry | 前端不接收 prompt rules；版本不可变 |
| 自定义参考 | 单次 `AppRun` | 最多 2000 字；不得导入事实；不得保存成个人风格 |
| 模型凭证 | 既有系统模型配置 | 不进入项目、风格、运行输入、fixture 或前端 |
| 图片/视频资产 | 既有 AssetLibrary | 必须固定 asset revision；拒绝绝对路径输入 |

显式拒绝 `api_key`、`authorization`、`cookie`、`provider`、`base_url`、`model`、`browser_profile` 和 `absolute_path` 等越权字段。fixture 与契约检查未发现真实凭证或用户绝对路径。

## 3. 兼容、迁移和回滚

- APP-WORKBENCH-0 数据库写入：`0`。
- APP-WORKBENCH-0 业务 UI 修改：`0`。
- v1 ContextSnapshot 继续可读；只有用户确认保存时才创建新的 v2 snapshot。
- 已有项目、AppRun、Artifact、历史生成文件和正在执行的 AppRun 不因 UI 回滚被删除或改写。
- `PIXELLE_APP_WORKBENCH_V2` 及三个应用分段 flag 均默认 `false`；任一阶段发现问题可关闭对应 flag 回到原 UI。
- 快速切换项目必须使用 `AbortController` 或 request sequence，旧请求不得回写当前项目。
- 双击生成必须复用活动请求或被拒绝，不能重复创建 Provider task。

## 4. 视觉与结构基线

使用 Codex 内置浏览器保存四应用当前真实页面的 12 张基线：

- 路由：`/apps/marketing-copy`、`/apps/viral-titles`、`/apps/douyin-carousel`、`/apps/digital-human-video`
- 请求视口：1440×900、1280×800、900×760
- 页面 DOM 报告视口与请求一致
- 浏览器嵌入层导出的 JPEG 会扣除滚动条/窗口 inset，实际图片尺寸和 SHA-256 已逐项登记
- 四路由均能识别正确应用；未出现“后端服务未连接”或“应用目录暂时不可用”

基线清单和哈希见 [`qa/APP-WORKBENCH-0-entry-2026-07-28.json`](qa/APP-WORKBENCH-0-entry-2026-07-28.json)。

## 5. 验证结果

- Entry/契约与基线清单测试：`10 passed`
- 应用中心相关聚合回归：`83 passed`
- 既有 Pydantic 弃用警告：`12`，与本阶段无关
- Ruff：`passed`
- JSON：`8 parsed`
- `git diff --check`：`passed`
- 真实 LLM 调用：`0`
- RunningHub 调用：`0`
- 发布平台/浏览器变更动作：`0`
- 最终发布点击：`0`

## 6. Gate 结论与边界

`PG-AW-A=passed_with_boundary`。需求、数据所有权、错误语义、兼容、迁移、回滚、视觉基线和 Entry tests 已形成可执行约束，允许进入 `APP-WORKBENCH-1` 的共享左右工作台壳层实现。

本结论不代表以下内容已经完成：

- 左右工作台业务 UI；
- ContextSnapshot v2 的数据库迁移和编辑器；
- 四应用 v2 executor/prompt；
- 风格库运行时；
- ArtifactVersion 编辑和 handoff UI；
- 真实 LLM、图文渲染、数字人或发布平台验证；
- Windows 用户设备、产品签字、真实 rollback/WebView SLA。
