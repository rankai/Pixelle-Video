# 数字人口播轻应用与默认声音绑定实施方案

- 日期：2026-07-30
- Change Request：`CR-DH-LITE-VOICE-001`
- 协调 Stage：`DH-LITE-VOICE`
- 上位方案：
  - `docs/superpowers/specs/2026-07-18-application-center-publishing-program-master-plan.md`
  - `docs/superpowers/specs/2026-07-24-digital-human-dual-mode-and-quality-optimization-implementation-plan.md`
  - `docs/superpowers/specs/2026-07-28-application-workbench-experience-optimization-implementation-plan.md`
- 唯一进度事实源：
  - `docs/reviews/2026-07-18-application-center-publishing-program-progress.md`

## 1. 产品定义

数字人口播不是另一套“即刻成片”，而是复用即刻成片成熟能力的轻量快捷入口：

```text
选择要说的内容
→ 选择带默认声音的数字人形象
→ 一次点击生成
→ 检查成片并快速交给发布中心
```

系统内部继续执行：

```text
内容固定 → TTS → 图片驱动或视频口型同步 → 字幕 → 封面 → 后期 → Artifact → 发布交付
```

普通用户不得为了使用轻应用而理解：

- AppRun、ArtifactVersion、稳定资源 ID 或生产流；
- 人物档案与场景的两级数据关系；
- TTS workflow、provider、voice revision 或推理参数；
- 图片和视频工作流兼容矩阵；
- 发布标题、封面标题和话题的内部生成阶段。

## 2. 核心决策

### 2.1 图片和视频只决定画面，不决定声音

- 图片数字人：图片场景 + 解析后的口播声音；
- 视频数字人：视频场景 + 解析后的口播声音，源视频仅作为动作、镜头和背景；
- 同一人物的图片场景和视频场景共享人物默认声音；
- 不从任意视频自动提取、注册或克隆声音；
- 真人克隆声音必须先作为有授权状态的 `VoiceProfile` 登记。

### 2.2 默认绑定归企业资产库所有

默认关系在以下入口维护：

```text
企业资产库 → 数字人 → 数字人详情 → 默认声音
```

数字人应用只显示轻量摘要：

```text
声音：老板自然声  [试听] [更换]
```

- 不操作时使用人物默认声音；
- “更换”仅覆盖本次任务；
- 应用内覆盖不修改企业资产库默认绑定；
- 没有绑定时显示明确的系统推荐声音，不得静默套用男声。

### 2.3 本地单组织与未来多租户

当前桌面版 `AssetLibraryRepository` 是单本地组织事实源，绑定只能引用同一 repository 中的数字人和声音。

未来迁移到 NestJS 多租户控制面时，关系必须增加并强制校验：

- `tenant_id`
- `digital_human_profile_id`
- `voice_profile_id`
- 授权状态
- 访问范围

当前实现不提前建设账户、组织、RBAC 或租户管理 UI，但数据和服务边界不得允许跨 repository 文件路径或客户端伪造声音 revision。

## 3. 数据与领域模型

### 3.1 数字人默认声音

对 `digital_human_profiles` 追加：

```text
default_voice_id TEXT NULL REFERENCES voice_profiles(voice_id)
```

规则：

- 默认声音属于人物 Profile，不属于场景；
- 删除绑定使用显式 `null`；
- 绑定、换绑和解绑都记录新的 `domain_revisions`；
- 声音被归档、媒体缺失或授权明确拒绝时，解析失败关闭；
- 旧数字人 `default_voice_id=null` 保持兼容，不执行静默数据库回填。

### 3.2 AppRun 声音快照

数字人 V2 的服务端规范化快照增加受控 `voice` 对象：

```json
{
  "voice": {
    "profile_id": "voice-...",
    "audio_revision_id": "revision-...",
    "resolution_source": "run_override|digital_human_default|system_default"
  }
}
```

公共客户端只允许表达：

```json
{"voice_profile_id": "voice-..."}
```

服务端负责解析并固定：

- `voice_profile_id`
- `audio_asset_id`
- `audio_revision_id`
- `authorization_status`
- `resolution_source`
- 实际 TTS workflow 类型

客户端不得提交绝对路径、参考音频文件路径、workflow 文件或 Provider 参数。
公共客户端提交嵌套 `voice` 快照也必须被拒绝；该对象只由服务端规范化和恢复链路写入。

### 3.3 声音解析顺序

```text
本次任务明确选择
→ 数字人 Profile 默认声音
→ 系统推荐声音
```

租户默认声音列为未来能力，本地版不伪造该层。

解析规则：

- `run_override` 和 `digital_human_default` 使用固定的 VoiceProfile 音频 revision；
- VoiceProfile 被归档、音频 revision 不存在或授权为 denied/revoked 时失败关闭；
- 没有可用 VoiceProfile 时使用明确的系统 Edge TTS 推荐声音；
- 系统推荐声音必须写入运行快照并在 UI 中显示名称；
- 历史 AppRun 重试继续使用已固定声音 revision，不随资产库更新漂移。

## 4. API

### 4.1 企业资产库

复用：

```text
PATCH /api/v2/domain/digital-humans/{profile_id}
```

新增可选字段：

```json
{"default_voice_id": "voice-..."}
```

解绑：

```json
{"default_voice_id": null}
```

后端必须验证：

- 数字人存在且未归档；
- VoiceProfile 存在且未归档；
- 音频资产和固定 revision 可解析；
- 授权状态不是 denied/revoked；
- 写入和 domain revision 在同一个 SQLite 事务中完成。

数字人读模型返回：

```json
{
  "summary": {
    "default_voice_id": "voice-...",
    "default_voice_name": "老板自然声",
    "default_voice_authorization_status": "authorized"
  }
}
```

### 4.2 数字人生成

应用创建 AppRun 时只提交可选 `voice_profile_id`。

Adapter 在创建阶段固定声音；Provider 执行阶段只解析已固定的 `audio_revision_id`，不能读取 VoiceProfile 的新 current revision。

## 5. 轻应用页面

### 5.1 默认主路径

左侧首屏只保留四块：

1. 当前项目：单行摘要和“更换”；
2. 口播内容：正文预览和“换文案”；
3. 数字人：最终场景卡，卡片同时显示“图片形象/视频形象”和默认声音；
4. 主按钮：`生成口播视频`。

项目、确认文案和最近数字人都存在时，页面直接进入可生成状态。

### 5.2 内容选择

默认策略：

- 优先恢复显式 handoff 或未完成运行；
- 否则使用当前项目最新可用的确认文案；
- 没有文案时展示“自己写”输入；
- `已有文案 / 自己写 / AI 写一版 / 标题带文案` 收进“换文案”面板；
- 主页面显示正文预览，不显示“来源产物”和“固定内容版本”。

版本和变体仍在系统内部固定，只有用户打开“换文案”后才显示可理解的候选正文。

### 5.3 数字人选择

- 主页面取消独立“图片数字人 / 视频数字人”步骤；
- 形象选择器同时展示最终可用场景卡；
- 选中场景后根据真实媒体类型自动决定图片或视频工作流；
- 人物有一个默认场景且用户点击人物卡时，可以一次确认；
- 资产管理页仍保留人物/场景维护能力；
- 普通选择器不得展示 medium、digital_human、资源 ID 或生产流。

### 5.4 声音

选择数字人后显示：

```text
声音：老板自然声 · 随数字人使用
[试听] [更换]
```

更换声音使用现有声音资产选择器：

- 可试听；
- 确认后只覆盖本次任务；
- 提供“恢复人物默认声音”；
- 不暴露克隆采样参数；
- 没有 VoiceProfile 时显示“系统推荐：云健自然声”，而不是隐式使用。

### 5.5 更多设置与结果

- 发布标题、描述、封面、话题、字幕继续默认折叠；
- 右侧空状态改为三项交付预告：视频、封面、发布文案；
- 生成成功后默认播放最终成片；
- 接收后保留“交给发布中心”；
- 最终平台发布按钮仍不自动点击。

## 6. 兼容、迁移与回滚

- SQLite 使用 additive column migration；
- 旧 profile 不回填；
- 旧 V1/V2 AppRun、session 和 Artifact 保持可读可恢复；
- 没有 `voice` 快照的旧 Run 继续按旧 session 声音参数恢复；
- 新 Run 必须固定声音解析结果；
- 关闭现有 `VITE_APP_WORKBENCH_DIGITAL_HUMAN_V2` 回到旧数字人工作区；
- 回滚前端不删除 `default_voice_id`、声音资产、AppRun 或 Artifact；
- 不修改即刻成片声音步骤；
- 不执行外部平台最终发布。

## 7. 实施阶段

### DH-LITE-VOICE-0：方案、契约与基线

- 登记 CR 和唯一入口；
- 冻结字段、错误码、解析顺序和回滚；
- 记录当前页面可视化基线；
- 不调用 TTS、RunningHub 或发布平台。

Gate：`PG-DLV-A`

### DH-LITE-VOICE-1：领域、API 与运行固定

- repository additive migration；
- 默认声音绑定、换绑、解绑与 domain revision；
- VoiceProfile 同库、状态、授权和 revision 校验；
- Adapter 声音解析和 AppRun 固定；
- Provider 按固定 revision 解析参考音频；
- V1/V2 恢复和失败关闭测试。

Gate：`PG-DLV-B`

### DH-LITE-VOICE-2：轻应用 UI

- 轻量内容预览；
- 形象场景一次选择并自动识别图片/视频；
- 人物默认声音摘要；
- 本次试听、更换和恢复默认；
- 更多设置继续折叠；
- 资产库默认声音维护。

Gate：`PG-DLV-C`

### DH-LITE-VOICE-3：验证和收口

- 后端定向与聚合测试；
- Desktop Vitest 和 production build；
- 真实 Browser 桌面及窄屏可视化；
- 图片和视频预生成流程验证；
- 不重复调用已通过的 RunningHub 真实 Provider；只有发现新的媒体契约问题才单独申请受控调用；
- 独立线程六维严格评审；
- 主线程按修复清单整改并交回复验，直到 P0/P1/实质性 P2 为 0。

Gate：`PG-DLV-D`

## 8. 测试矩阵

### 后端

- 无默认声音 → 系统推荐快照；
- Profile 默认声音 → 固定 voice/audio revision；
- 本次覆盖 → 优先于 Profile 默认；
- 清除本次覆盖 → 恢复 Profile 默认；
- 换绑与解绑写入 domain revision；
- 声音归档、音频归档、revision 不匹配、授权拒绝；
- 客户端伪造 revision、绝对路径和 workflow；
- 图片、视频模式使用同一声音解析器；
- 旧 Run 无 voice 字段恢复；
- 重试不漂移到新声音 revision；
- 并发修改默认声音不改变已创建 AppRun。

### 前端

- 资产库绑定、换绑、解绑；
- 数字人选择后自动显示绑定声音；
- 本次更换不修改 Profile 默认；
- 恢复人物默认声音；
- 无绑定时明确显示系统推荐；
- 图片/视频场景自动切换模式；
- 默认主路径不展示技术词；
- 390、900、1280、1440 宽度无溢出、遮挡和滚动陷阱；
- 最终发布点击次数为 0。

## 9. 完成标准

只有同时满足以下条件才可关闭：

- 数字人应用默认主路径最多三个用户决策；
- 图片/视频由所选场景自动决定；
- 企业资产库可维护人物默认声音；
- 应用可试听和本次换声；
- AppRun 固定声音 ID、revision 和解析来源；
- 历史运行不漂移；
- 页面不再默认展示生产术语；
- 后端、前端、构建和真实可视化全部通过；
- 独立六维评审确认目标完整实现并给出证据；
- 最终发布仍由人工点击。
