# APP-WORKBENCH-2 项目上下文实现记录

## 结论

`APP-WORKBENCH-2` 已按边界完成，`PG-AW-C=passed_with_boundary`。

本阶段把“选项目”从一个项目名称下拉框推进为可复用、可版本化的经营资料上下文。门店营销文案、爆款标题、抖音图文和数字人口播的新运行都可以绑定明确的 `ContextSnapshot`；旧运行继续固定原快照。

## 已交付

### 服务端

- 新增严格校验的 ContextSnapshot v2 模型；
- v1/v2 同时可读，v1 只做升级预览，显式保存时追加 v2；
- 事实、场景、资产引用使用稳定 ID，并校验重复、冲突、跨项目和缺失；
- ArtifactVersion 引用只能解析同项目产物；
- 资产引用必须精确到 revision；
- repository 指纹包含 schema、payload 和来源引用；
- FastAPI 返回稳定业务错误码；
- SQLite 约束升级为 `schema_version IN (1, 2)`，旧数据库在事务中安全重建并保留备份。

### 桌面端

- 新增共享 `ProjectContextSelector` 和 `ProjectBriefEditor`；
- 提供经营主体、门店/品牌、行业、商品/服务、品类、目标人群、卖点、事实、场景、价格、活动、禁用表达和素材版本等字段；
- 项目草稿按项目写入本机，重启或刷新可恢复；
- 服务端快照已更新时，恢复旧草稿会明确提示版本差异；
- 切换、新建和归档项目会保护未保存修改；
- 项目资料未保存时，生成按钮禁用并显示原因；
- 文案、标题、图文和数字人口播创建新运行时绑定当前快照；
- 快速切换项目使用 request sequence，旧请求结果不会覆盖新项目。

## 真实本地验证

建立测试项目 `project_13a7f2686436443789bb1823848ceb60`，先保存 v1 快照，再通过真实界面显式升级为 v2。确认：

1. v1 快照仍存在且可读；
2. v2 以新记录追加；
3. 页面刷新后恢复本机草稿；
4. 草稿未处理时禁止生成；
5. 放弃草稿后回到服务端当前快照；
6. 新建 AppRun `run_7774c5a4acbb4c25b91c387a7d0305e2` 固定绑定 v2；
7. 验证结束后测试项目已归档。

本阶段没有执行 AppRun provider、LLM、RunningHub、平台上传或最终发布。

## 验证结果

- 后端：54 passed；
- Desktop：14 files / 89 passed；
- Desktop production build：passed；
- Ruff：passed；
- `git diff --check`：passed；
- SQLite foreign key check：empty；
- 1440×900、900×760、390×844：无横向溢出；
- 文案工作台与数字人工作台均只出现一套共享项目选择器和编辑器。

完整证据见 [`qa/APP-WORKBENCH-2-implementation-2026-07-28.json`](qa/APP-WORKBENCH-2-implementation-2026-07-28.json)。

## 保留边界

- 风格库、文案/标题 schema v2、prompt 与真实 Doubao smoke 留给 APP-WORKBENCH-3；
- `PIXELLE_APP_WORKBENCH_V2` 继续默认关闭；
- 不覆盖 v1、历史 AppRun、Artifact 或媒体文件；
- 最终发布仍保持人工点击；
- Windows 实机、产品签字和真实 rollback/WebView SLA 仍属于暂停的 `PROGRAM-ROLLOUT/PG-L`。
