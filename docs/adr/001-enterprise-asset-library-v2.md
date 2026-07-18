# ADR-001：企业资产库 V2 的资源边界、迁移与回滚

- 状态：Accepted（阶段 0 / 门禁 A）
- 日期：2026-07-17
- 负责人：Pixelle Video
- 适用范围：企业资产中心、视频生产流选择器、媒体上传与本地任务恢复

## 背景

当前视频、图片、数字人、音色、品牌和模板由不同 JSON manifest、不同 ID 和不同前端组件管理。主资产库没有统一查询、版本、使用关系和回滚基线；生产流还直接消费部分绝对路径。

参考数字人管理交互要求“左侧人物/场景选择 + 右侧即时预览”，而之前的模板问题又要求成片必须锁定模板、字体、字幕和封面位置的实际渲染版本。

## 决策

### 1. 统一资源索引，保留领域模型边界

`LibraryItem` 是面向搜索、筛选、收藏和选择器的统一只读投影，不是万能持久化表。

- `MediaAsset`：图片、视频、音频、字体等文件。
- `BrandKitResource`：品牌颜色、字体、Logo、BGM、发布默认值等复合配置。
- `TemplateDefinition`：模板 schema、renderer 版本、封面/字幕渲染契约。
- `DigitalHumanProfile` / `DigitalHumanScene`：人物档案和场景，场景引用媒体 revision。

所有 UI 资源引用使用 `resourceKind + resourceId`；媒体文件使用 `assetId + revisionId + variantId`。

### 2. 原始媒体不可变，修改通过 revision

原始文件永不因重命名、裁切或模板升级而被覆盖。逻辑媒体资产保留 `currentRevisionId`；“作为新版本”创建新 revision，poster、缩略图、代理和波形是 revision 变体。

渲染启动时生成 `ResourceSnapshot`，锁定资源 ID、revision、hash、变体、模板 revision 和 renderer version。这样旧任务不会因新模板或新文件导致字幕、字体和封面位置漂移。

### 3. SQLite 是本地元数据源，原文件仍留在 data 目录

SQLite 负责事务、索引、FTS5（可用时）、分页、版本、usage、集合和本地媒体任务。原始文件只保存相对路径；v2 API 不返回绝对磁盘路径。FTS5 不可用时回退到普通索引和 `LIKE`，不能阻塞应用启动。

### 4. 上传采用 upload session + 流式临时文件

客户端先创建 upload session，服务端预检类型、大小和磁盘空间；文件以 chunk 写入 `.part` 文件，校验成功后原子 rename 为 revision。上传状态和媒体分析任务写入 SQLite，应用重启时恢复 pending/running 任务并清理无主临时文件。桌面 WebView 第一版使用 `XMLHttpRequest.upload.onprogress`，后续 Tauri 原生上传复用相同 session 协议。

### 5. 迁移不移动原文件，旧接口做兼容适配

迁移前备份 manifest 并记录校验值；迁移以 `resource_kind + legacy_id` 建立稳定映射，图片/视频先形成垂直闭环，其他类型按阶段扩展。旧 service 和旧 API 在兼容窗口内从新 repository 序列化旧格式；session 双写旧路径和新资源引用，读取优先新引用、缺失时回退旧路径。

### 6. usage 有完整生命周期

新增、替换、取消选择和删除 slot 都需要同步维护 usage；对 `session + step + slot + purpose + resource` 加唯一约束，并提供 reconciliation 从 session 状态重建 usage。归档不破坏旧任务；只有未引用的回收站 revision 才允许物理清理。

## 门禁

- 门禁 A：ADR、Pydantic/TypeScript 数据契约、旧 manifest 基线、备份与回滚演练 fixture、`asset_center_v2` 默认关闭 feature flag 完成。
- 门禁 B：图片/视频资产中心 → 共享选择器 → 画面规划或封面 → 成功渲染闭环通过，usage 和 snapshot 对账正确。
- 门禁 C：全量迁移、模板 revision/renderer 快照、关键旧任务、主题与无障碍回归通过后，才默认开启新版并删除旧 UI。

## 不在本 ADR 内的内容

- 云端多租户、权限和远程对象存储。
- 依赖向量数据库的语义搜索。
- AI 人脸/姿态质量判断作为首个垂直闭环的硬门槛。
- 自动点击平台最终发布。

## 后果

正面后果是资源搜索、预览、选择、版本和渲染可以共享稳定契约；负面后果是第一阶段需要维护旧 API 适配、双写和迁移对账。任何跳过 snapshot 或回滚基线的实现都不符合本 ADR。
