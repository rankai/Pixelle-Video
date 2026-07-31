# DH-LITE-VOICE 数字人口播轻应用与默认声音绑定实施证据

- 日期：2026-07-30
- Change Request：`CR-DH-LITE-VOICE-001`
- Stage：`DH-LITE-VOICE`
- Gate：`PG-DLV-D`
- 状态：实现、定向测试、生产构建、真实 Browser 复验和独立六维终审全部完成
- 实施方案：[`2026-07-30-digital-human-lite-and-voice-binding-implementation-plan.md`](../../superpowers/specs/2026-07-30-digital-human-lite-and-voice-binding-implementation-plan.md)
- 独立终审：[`DH-LITE-VOICE-final-review-2026-07-30.md`](DH-LITE-VOICE-final-review-2026-07-30.md)

## 1. 已交付

### 1.1 数字人轻应用

- 默认主路径收敛为：选择项目、输入或选择口播内容、选择数字人形象、确认声音、开始生成；
- 取消独立的“图片模式 / 视频模式”用户步骤，选择场景后按真实媒体类型自动决定 `image_talking` 或 `video_lipsync`；
- 口播来源、卖点补充、发布标题、描述、封面、话题和字幕设置默认折叠；
- 旧项目的品牌关联提示压缩为单行提示，不再占用主流程大块空间；
- 形象选择器支持同一入口选择图片场景和视频场景；
- 资产选择器不再向普通用户显示能力标识、稳定资源 ID 或生产流术语；
- 最终平台发布按钮仍不自动点击。

### 1.2 数字人默认声音

- `digital_human_profiles` 增加 additive `default_voice_id`；
- 企业资产库数字人详情可绑定、更换和恢复系统推荐声音；
- 数字人列表投影返回默认声音名称、文件 URL 和授权状态；
- 数字人应用显示人物默认声音，可试听，可只为本次任务更换，也可恢复人物默认；
- 图片和视频形象共用同一套声音解析，不使用源视频声音；
- 未绑定人物声音时明确显示“系统推荐男声”，不再静默处理。

### 1.3 服务端固定与恢复

- 解析顺序固定为：本次覆盖 → 人物默认 → 系统推荐；
- 客户端只提交可选 `voice_profile_id`，不能提交文件路径、音频 revision、workflow 或 Provider 参数；
- 服务端固定 VoiceProfile、音频资产 revision、授权状态和解析来源；
- 参考音频按固定 revision 精确解析，重试或重启不会漂移到新的 current revision；
- Desktop 只保存本次 Run 的声音名称、VoiceProfile ID 和解析来源作为展示快照；它与 `app_run_id + source_revision + context_snapshot` 一起校验后才恢复，不保存音频资产路径或媒体 revision；
- 人物默认、本次覆盖和系统推荐三类历史 Run 都显示创建时固定的声音来源，不按人物当前绑定重新推断；
- 声音或媒体归档、revision 缺失、授权为 denied/revoked 时失败关闭；
- 旧 Run 没有 voice 快照时继续兼容恢复。

## 2. 主要实现文件

- `api/schemas/asset_library_v2.py`
- `pixelle_video/services/assets_v2/repository.py`
- `pixelle_video/app_center/digital_human_input.py`
- `pixelle_video/app_center/ip_broadcast_adapter.py`
- `pixelle_video/services/ip_broadcast_workflow.py`
- `desktop/src/api.ts`
- `desktop/src/features/assets/components/AssetCenterV2.tsx`
- `desktop/src/features/assets/components/AssetPickerDialog.tsx`
- `desktop/src/features/app-center/DigitalHumanApplicationView.tsx`
- `desktop/src/styles.css`
- `tests/digital_human_voice_binding_test.py`
- `desktop/src/features/app-center/DigitalHumanApplicationView.test.tsx`

## 3. 自动化验证

### 3.1 后端

命令：

```bash
uv run pytest -q \
  tests/digital_human_voice_binding_test.py \
  tests/digital_human_dual_mode_server_test.py \
  tests/digital_human_quality_impl_test.py \
  tests/asset_library_v2_repository_test.py \
  tests/asset_library_ux1_test.py
```

结果：`81 passed, 12 warnings`。

覆盖：

- 默认声音绑定、换绑、解绑和投影；
- 系统推荐 fallback；
- VoiceProfile 授权拒绝；
- 本次声音覆盖；
- AppRun 声音快照；
- 人物默认、本次覆盖和系统推荐三类 create → revalidate；
- 人物换绑、声音 current revision 更新、VoiceProfile 更换参考音频资产后，历史 Run 仍使用原固定 `audio_asset_id + audio_revision_id`；
- 公共输入不能伪造服务端 voice snapshot 或选择音频 revision；
- 固定 revision 的 TTS 参考音频解析；
- 图片、视频模式既有服务端回归；
- 资产库既有 API 和迁移回归。

静态检查：

```bash
uv run ruff check \
  api/schemas/asset_library_v2.py \
  pixelle_video/app_center/digital_human_input.py \
  pixelle_video/app_center/ip_broadcast_adapter.py \
  pixelle_video/services/assets_v2/repository.py \
  pixelle_video/services/ip_broadcast_workflow.py \
  tests/digital_human_voice_binding_test.py
git diff --check
```

结果：通过。

### 3.2 Desktop

命令：

```bash
npm test -- --run \
  src/features/app-center/DigitalHumanApplicationView.test.tsx \
  src/features/assets/components/AssetPickerDialog.test.tsx
npm run build
```

结果：

- `2 files / 25 tests passed`；
- TypeScript 和 Vite production build 通过；
- 仅保留项目既有的 bundle chunk size warning。

## 4. 真实 Browser 可视化复验

复验页面：`#/apps/digital-human-video`，桌面视口。

已验证：

- 左右工作台与应用中心主题、容器、字体、按钮和状态样式一致；
- 左侧首屏为轻量操作区，右侧为空态/结果区；
- 主路径没有图片/视频模式 Tab；
- “口播来源”“补充本次卖点”“发布文案与更多设置”默认折叠；
- 旧项目提示已压缩为一行；
- 数字人选择器先选人物再选最终场景，场景标识为可理解的“图片场景 / 视频场景”；
- 选择图片场景后页面回填“图片形象 · 自动生成口播动作”；
- 声音选择器支持真实音频试听、选择和确认；
- 声音选择器不再显示 `适配能力：use` 等技术标签；
- 当前页面本次重新加载后 `error/warning` 日志为 0；
- 未点击开始生成，未调用 RunningHub、TTS Provider 或外部发布平台，最终发布点击次数为 0。

## 5. 保留边界

- 本阶段没有重复执行已通过的付费 RunningHub 真实 Provider 调用；
- 本地数字人资产当前可视化样本只有图片场景，视频场景的 UI 自动识别由代码、前端测试和既有双模式后端回归覆盖；
- Windows 实机安装、产品负责人签字、真实平台 rollback / WebView SLA 仍属于上位 `PROGRAM-ROLLOUT/PG-L`，不由本 Stage 冒充完成；
- 独立六维终审最终结论为 `PASS`，`P0=0`、`P1=0`、`实质性 P2=0`；`PG-DLV-D` 可登记为 `passed`。
