# DH-DUAL-2 独立六维实现复审（2026-07-24）

## 结论

`implementation_pass_with_boundary`。

- P0：0
- P1：0
- 实质性 P2：0
- 非阻断观察项：`AssetPickerDialog` 的视频预览使用 `<video controls>` 嵌套在场景 `<button>` 内；当前可用性与测试均通过，但后续可改为非交互卡片或对控件事件做隔离，以改善 HTML 语义和键盘/鼠标交互。

PG-DH-C 可以收口并切换到 `DH-QUALITY-1`。本结论只覆盖 DH-DUAL-2 的桌面入口、双模式资产选择、V2 payload、恢复与结果交付，不等价于真实视频数字人质量或 Provider Gate 通过。

## 六维复核

### 1. 需求完整性：通过

- 联合后端/桌面开关和 Registry readiness 均 fail-closed；旧 `/ip` 路由与人工发布边界保持。
- `image_talking`/`video_lipsync` 两个模式与 `content_source` 维度分离。
- 选择器按 scene 的真实媒体类型过滤，选择后固定 `source_revision_id`，并回填媒体类型、分辨率、时长和质量。
- 模式切换会清除不兼容资产但保留制作目标/文案；pending/run 恢复 mode、来源、scene、revision 和输入。
- 初次入口唯一主动作是“开始生成”，一次点击先幂等创建 AppRun 再调用 execute；双击不会重复创建 Run。
- needs_review/completed 默认交付 `final_video`、`cover`、`publish_copy`，原始数字人视频仅保留在诊断区域，下载默认使用 `final_video`。

### 2. 逻辑正确性：通过

- V2 normalize、受信 workflow catalog、媒体类型/MIME/尺寸/时长/revision/profile/scene 校验均由服务端重新判定。
- 前端不提交 Provider URL、密钥、文件路径或任意 workflow 标识；服务端拒绝这类字段。
- AppRun 指针在 POST 前持久化，幂等键复用；创建后先写安全指针再执行，执行响应丢失时可通过恢复读取既有 Run。
- 已归档或版本不匹配的来源会安全停手，不覆盖不同项目、session 或 source revision。
- V1 `1.0.0` 恢复和 V2 `1.1.0` 新建路径保持兼容。

### 3. 边界情况：通过（保留边界）

- 默认开关关闭、后端 readiness 失败、无匹配媒体 scene、归档素材、revision 不一致、非法模式和未发布 workflow 均 fail-closed。
- 真实本地 AssetLibrary 当前没有登记视频 scene；视频模式中现有图片资产全部禁用并显示“当前模式只支持视频场景”，没有伪造视频素材。
- 视频 `<video controls>` 和 mixed-profile 过滤由 Vitest fixture 覆盖；`real_video_scene_available=false`，因此本批不宣称真实视频预览或唇形质量完成。
- Provider、浏览器平台、第三方授权、上传和最终发布点击均为 0；最终发布仍必须人工确认。

### 4. 代码质量：通过

- UI 新增模式 Tab、结果面板和 picker 逻辑，构建通过；目标 Python 文件 Ruff 通过，`git diff --check` 通过。
- 受保护 blob URL 的图像、音频、视频和最终视频预览均在卸载时释放；诊断素材不作为默认下载对象。
- 非阻断观察项：视频 controls 嵌套 button 的 HTML 交互语义后续整理。

### 5. 测试覆盖：通过

- Desktop Vitest：11 files / 67 tests passed。
- Server/AssetLibrary/Entry/Adapter/API/Artifact/Registry 聚合：110 passed，12 个既有 Pydantic deprecation warnings。
- `npm run build`（TypeScript + Vite）通过，仅有既有 chunk size warning。
- 目标 Ruff、JSON parse、`git diff --check` 通过。
- 覆盖模式切换、scene 过滤、视频控件 fixture、选中回填、revision/元数据、pending/run 恢复、幂等双击、结果预览和默认下载。

### 6. 实际运行结果：通过（本地边界）

- In-app Browser 本地 FastAPI + Vite 实测应用中心→数字人路由→图片/视频 Tab→资产选择器。
- 图片模式真实 AssetLibrary 选择 `美女` 图片 scene 并确认回填，页面展示图片场景、`revision 已锁定`、`944×1280`、质量“已就绪”。
- 视频模式真实选择器对现有图片 profile 全部禁用并展示媒体类型原因；未使用 Provider 或虚构视频资产。
- 1440×900、1280×800、900×760、390×760 均无横向溢出（实测 `scrollWidth == clientWidth`）。
- 新 one-click 主动作、图片选择器、确认回填和视频模式边界的截图/DOM 已归档并列入 QA JSON。

## 证据索引

- QA：[`qa/DH-DUAL-2-implementation-2026-07-24.json`](qa/DH-DUAL-2-implementation-2026-07-24.json)
- 视觉/交互目录：[`qa/DH-DUAL-2-visual-2026-07-24/`](qa/DH-DUAL-2-visual-2026-07-24/)
- 关键新截图 SHA-256：
  - one-click 页面：`6da301e4b09bc619a1565a61662998e2100f84a5e2418a1c5d2e53b2d2f27906`
  - one-click 图片选择器：`33917a1bb0f7546badb23f444757091cee63f3b84b3093fa205752b319256abd`
  - one-click 视频模式边界：`4fdd67ca5c1b7440c7ab3a94ed57b0c4adf1af6f370faaf9a8abe3f386147c6f`
  - one-click DOM：`5446165bbb768a9ac2d995d7b79c4e8619599a501a3fd28a1748ce6b66a1d958`
- 本地服务端真实数据形状：`/api/v2/library/items?kind=digital_human` 返回 `digital_human` capability 及 profile/scene 元数据。

## 后续边界

下一阶段 `DH-QUALITY-1` 负责完整文案来源与版本选择、字幕 v2、封面标题、最终成片质量和 Artifact 质量；后续质量阶段再登记真实视频 scene 并执行一次有目的的 Provider smoke。不得把本批 fixture、图片场景或本地 UI 证据解释为视频数字人质量通过，也不得开启最终发布自动点击。
