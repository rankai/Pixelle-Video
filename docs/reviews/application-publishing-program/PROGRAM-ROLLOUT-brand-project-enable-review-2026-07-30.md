# PROGRAM-ROLLOUT 品牌项目新版正式启用独立复审

- 日期：2026-07-30
- Change Request：`CR-BRAND-PROJECT-ROLLOUT-001`
- 审查线程：`/root/brand_project_stage5_final_reviewer`
- 审查方式：独立只读六维复审，不修改代码或证据
- 结论：`PASS with boundary`
- P0：0
- P1：0
- P2：0

## 六维结论

1. 需求完整性：生产默认启用、standalone FastAPI 默认关闭、显式 `0/false`
   回滚、四应用和窄屏交付均符合方案。
2. 逻辑正确性：Tauri runtime、React 首屏和 FastAPI sidecar 共用同一有效开关，
   已消除前后端 split-brain。
3. 边界情况：unset/true 开启，`0/false` 关闭，非法值失败关闭；旧项目不会自动写入
   或绑定品牌。
4. 代码质量：Rust format、TypeScript build、`git diff --check`、敏感信息及 QA
   数据库检查通过。
5. 测试覆盖：Python 137 passed；Desktop 18 files / 125 passed；Tauri 2 passed；
   production build 4610 modules。
6. 实际运行：1265px 应用中心、四应用与“我的项目”入口通过；375px 旧项目提示和
   数字人来源 Tab 通过；数字人四个来源 Tab 在两种视口均完整可见且无横向溢出；
   普通 UI 未见 Artifact、revision、snapshot、fingerprint、final_video 等技术词；
   8 张截图尺寸和 SHA-256 与 manifest 一致；项目/品牌写入、Provider 调用和最终发布
   点击均为 0。

## 整改闭环

- P1：编译期 WebView 开启、运行时仅关闭 sidecar 的 split-brain，已改为同一
  Tauri runtime 布尔值驱动 React 有效开关和 sidecar 环境。
- P1：数字人“口播来源”四个 Tab 在 1265px/375px 被裁切，已改为自适应 2×2
  grid 并以真实几何和自动化契约锁定。
- P2：数字人普通 UI 的技术词已替换为用户语言。
- 证据型 P2：本批次 1265px/375px 真实截图与哈希 manifest 已归档。

## 保留边界

- Windows 真实设备安装验收未完成；
- 产品负责人签字未完成；
- 真实平台 rollback / WebView SLA 仍 open；
- 最终发布自动点击继续关闭。

范围判断：没有偏离方案范围，可以进入分批提交、推送、PR 合并和 Windows NSIS
安装包构建。
