# APP-WORKBENCH-3 Entry：文案与标题

## Entry 结论

`PG-AW-D_entry=passed_with_boundary`，允许进入本阶段业务实现。

## 冻结范围

### 输入

- 文案使用 `marketing-copy-input.v2`；
- 标题使用 `viral-titles-input.v2`；
- 两者均绑定 `project_id`、`context_snapshot_id`；
- 风格只能二选一：
  - 受信 `style_ref={style_id,version}`；
  - 本次 Run 的 `custom_style_reference`；
- 自定义参考只模仿表达方式，`facts_imported=false`，内容指纹随 Run 固定；
- 文案到标题通过固定 `artifact_version_id` 的 handoff，不热更新。

### 风格

- Registry 随代码发布，`style_id + version` 稳定；
- Prompt rules 和 forbidden patterns 只由服务端受信代码读取；
- 桌面端只读取名称、说明和短样例；
- 风格不得引入项目资料之外的价格、活动、地址、效果、身份或案例。

### 结果与事件

- 文案仍产出 `copywriting` Artifact；
- 标题仍产出 `title_set`，选中后可产生 `selected_title`；
- 编辑追加 ArtifactVersion，不覆盖旧版本；
- 复制、编辑、选择、喜欢、不喜欢和 handoff 只记非敏感 `app_events`；
- 事件不保存完整文案副本、模型配置、密钥或浏览器数据。

## 允许修改

- `pixelle_video/app_center/style_presets.py`；
- `structured_apps.py` 与 `llm_port.py` 的受信风格和输入 v2 兼容；
- repository 的最小 AppEvent 读写；
-必要 FastAPI schema/router；
-文案/标题工作台输入与结果交互；
-对应 tests、fixture、证据和 tokens 复用。

## 明确禁止

- 不实现抖音图文分页、局部重渲染或发布 handoff；
- 不重构数字人媒体状态机；
- 不新增第二套 LLM/provider/key 配置；
- 不把自定义参考写入 ProjectContext；
- 不调用 RunningHub、发布平台或最终发布按钮；
- 真实 Doubao smoke 前必须先通过 fake、回归、build 和六维自审，且同一用例只执行一次有目的调用。

## 回滚

- `PIXELLE_APP_WORKBENCH_TEXT_V2=0` 回到原文案/标题输入；
- 已生成 ArtifactVersion、AppEvent 和 handoff 保留；
- 回滚不取消运行中的 AppRun；
- v1 输入和 v1 Artifact 继续可读；
- 不删除媒体文件或项目资料。

## Entry 依据

- `style-preset.schema.json`；
- `fixtures/style-preset-registry-v1.json`；
- `app-workbench-input-v2.schema.json`；
- `app-workbench-entry.contract.json`；
- `tests/app_workbench_entry_contract_test.py`；
- `APP-WORKBENCH-2/PG-AW-C=passed_with_boundary`。
